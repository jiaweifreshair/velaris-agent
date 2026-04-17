"""利益相关方映射图构建器 — Stakeholder Map Builder.

从 StakeholderRegistry 中检索活跃的 Stakeholder，
计算两两对齐矩阵，构建 StakeholderMapModel。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from itertools import combinations

from velaris_agent.memory.stakeholder import StakeholderRegistry
from velaris_agent.memory.types import (
    AlignmentReport,
    PairwiseAlignment,
    Stakeholder,
    StakeholderMapModel,
)


class StakeholderMapBuilder:
    """Builds a StakeholderMapModel for a given scenario."""

    def __init__(self, registry: StakeholderRegistry) -> None:
        self._registry = registry

    def build(self, scenario: str) -> StakeholderMapModel:
        """Retrieve active stakeholders and compute pairwise alignment matrix.

        Edge case: fewer than 2 stakeholders returns a valid map with an
        empty alignment matrix.
        """
        stakeholders = self._registry.list_active(scenario)

        alignment_matrix: list[PairwiseAlignment] = []
        if len(stakeholders) >= 2:
            for a, b in combinations(stakeholders, 2):
                alignment_matrix.append(
                    self.compute_pairwise_alignment(a, b),
                )

        return StakeholderMapModel(
            map_id=str(uuid.uuid4()),
            scenario=scenario,
            stakeholders=stakeholders,
            alignment_matrix=alignment_matrix,
            conflicts=[],
            timestamp=datetime.now(tz=timezone.utc),
        )

    def compute_pairwise_alignment(
        self, a: Stakeholder, b: Stakeholder,
    ) -> PairwiseAlignment:
        """Compute alignment between two stakeholders.

        Algorithm (from design):
          shared_dims = intersection of dimension names
          if no shared_dims → score = 0.5 (neutral)
          else:
            for each shared dim:
              direction_match = 1.0 if same direction else 0.0
              weight_similarity = 1.0 - abs(A.weight - B.weight)
              influence_factor = (A.influence[dim] + B.influence[dim]) / 2
              dim_score = direction_match * 0.6 + weight_similarity * 0.4
              weighted_dim_score = dim_score * influence_factor
            score = sum(weighted_dim_scores) / sum(influence_factors)

          classification:
            score >= 0.7 → "aligned"
            0.3 <= score < 0.7 → "neutral"
            score < 0.3 → "conflicting"
        """
        # Build lookup: dimension name → InterestDimension
        a_dims = {d.dimension: d for d in a.interest_dimensions}
        b_dims = {d.dimension: d for d in b.interest_dimensions}

        shared_dim_names = set(a_dims.keys()) & set(b_dims.keys())

        if not shared_dim_names:
            score = 0.5
        else:
            weighted_dim_scores: list[float] = []
            influence_factors: list[float] = []

            for dim_name in shared_dim_names:
                a_dim = a_dims[dim_name]
                b_dim = b_dims[dim_name]

                direction_match = 1.0 if a_dim.direction == b_dim.direction else 0.0
                weight_similarity = 1.0 - abs(a_dim.weight - b_dim.weight)

                a_influence = a.influence_weights.get(dim_name, 0.0)
                b_influence = b.influence_weights.get(dim_name, 0.0)
                influence_factor = (a_influence + b_influence) / 2.0

                dim_score = direction_match * 0.6 + weight_similarity * 0.4
                weighted_dim_scores.append(dim_score * influence_factor)
                influence_factors.append(influence_factor)

            total_influence = sum(influence_factors)
            if total_influence == 0.0:
                score = 0.5
            else:
                score = sum(weighted_dim_scores) / total_influence

        classification = _classify_score(score)

        return PairwiseAlignment(
            stakeholder_a_id=a.stakeholder_id,
            stakeholder_b_id=b.stakeholder_id,
            score=score,
            classification=classification,
        )

    def export_as_alignment_report(
        self,
        map_model: StakeholderMapModel,
        user_id: str,
        org_id: str,
    ) -> AlignmentReport:
        """Extract a two-party AlignmentReport for backward compatibility.

        Finds the pairwise alignment between the specified user and org
        stakeholders and maps it to the legacy AlignmentReport format.
        """
        # Find the pairwise alignment between user and org
        alignment_score = 0.5  # default neutral
        for pa in map_model.alignment_matrix:
            ids = {pa.stakeholder_a_id, pa.stakeholder_b_id}
            if ids == {user_id, org_id}:
                alignment_score = pa.score
                break

        # Build conflicts list from alignment matrix context
        conflicts: list[dict[str, object]] = []
        synergies: list[str] = []

        # Look up the two stakeholders to extract dimension-level details
        user_sh: Stakeholder | None = None
        org_sh: Stakeholder | None = None
        for s in map_model.stakeholders:
            if s.stakeholder_id == user_id:
                user_sh = s
            elif s.stakeholder_id == org_id:
                org_sh = s

        if user_sh is not None and org_sh is not None:
            user_dims = {d.dimension: d for d in user_sh.interest_dimensions}
            org_dims = {d.dimension: d for d in org_sh.interest_dimensions}
            shared = set(user_dims.keys()) & set(org_dims.keys())

            for dim_name in shared:
                u_dim = user_dims[dim_name]
                o_dim = org_dims[dim_name]
                if u_dim.direction != o_dim.direction:
                    conflicts.append({
                        "dimension": dim_name,
                        "user_weight": u_dim.weight,
                        "org_weight": o_dim.weight,
                        "gap": abs(u_dim.weight - o_dim.weight),
                    })
                elif u_dim.direction == o_dim.direction:
                    gap = abs(u_dim.weight - o_dim.weight)
                    if gap > 0.3:
                        conflicts.append({
                            "dimension": dim_name,
                            "user_weight": u_dim.weight,
                            "org_weight": o_dim.weight,
                            "gap": gap,
                        })
                    else:
                        synergies.append(dim_name)

        return AlignmentReport(
            user_id=user_id,
            org_id=org_id,
            scenario=map_model.scenario,
            alignment_score=alignment_score,
            conflicts=conflicts,
            synergies=synergies,
            negotiation_space={},
            created_at=map_model.timestamp,
        )


def _classify_score(score: float) -> str:
    """Classify an alignment score into aligned/neutral/conflicting."""
    if score >= 0.7:
        return "aligned"
    if score >= 0.3:
        return "neutral"
    return "conflicting"
