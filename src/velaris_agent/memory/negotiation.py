"""协商策略生成器 — Negotiation Strategy.

基于冲突分析生成多方妥协方案。核心算法:

- **逆影响力让步公式**: 影响力越低的一方让步越多
  concession_A = (1/influence_A) / total_inverse_influence * total_gap
- **可行性评分**: 1.0 - (total_concession / max_possible_concession)
- **硬约束处理**: OrgPolicy 中的约束维度标记为 non_negotiable,
  约束持有方让步为 0
"""

from __future__ import annotations

from velaris_agent.memory.types import (
    Conflict,
    NegotiationProposal,
    OrgPolicy,
    Stakeholder,
    StakeholderMapModel,
)

# Small epsilon to avoid division by zero when influence is 0 or near-zero.
_EPSILON = 1e-9


class NegotiationStrategy:
    """Generates compromise proposals for conflicting dimensions."""

    def generate(
        self,
        conflicts: list[Conflict],
        map_model: StakeholderMapModel,
        org_policy: OrgPolicy | None = None,
    ) -> list[NegotiationProposal]:
        """Produce one :class:`NegotiationProposal` per conflicting dimension.

        Parameters
        ----------
        conflicts:
            Conflicts detected by :class:`ConflictDetectionEngine`.
        map_model:
            The stakeholder map providing stakeholder details.
        org_policy:
            Optional organisation policy whose ``constraints`` keys mark
            non-negotiable dimensions.

        Returns
        -------
        list[NegotiationProposal]
            One proposal per unique conflicting dimension.
        """
        if not conflicts:
            return []

        # Build a lookup for stakeholders by id.
        stakeholder_by_id: dict[str, Stakeholder] = {
            s.stakeholder_id: s for s in map_model.stakeholders
        }

        # Determine hard-constraint dimensions from OrgPolicy.
        hard_constraint_dims: set[str] = set()
        if org_policy is not None:
            hard_constraint_dims = set(org_policy.constraints.keys())

        # Collect org stakeholder ids so we can identify the constraint holder.
        org_stakeholder_ids: set[str] = {
            s.stakeholder_id
            for s in map_model.stakeholders
            if s.role.value == "org"
        }

        # Group conflicts by dimension — only produce one proposal per dim.
        dim_conflicts: dict[str, list[Conflict]] = {}
        for c in conflicts:
            dim_conflicts.setdefault(c.dimension, []).append(c)

        proposals: list[NegotiationProposal] = []
        for dimension, dim_conflict_list in dim_conflicts.items():
            proposal = self._generate_proposal(
                dimension=dimension,
                dim_conflicts=dim_conflict_list,
                stakeholder_by_id=stakeholder_by_id,
                hard_constraint_dims=hard_constraint_dims,
                org_stakeholder_ids=org_stakeholder_ids,
            )
            proposals.append(proposal)

        return proposals

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_proposal(
        self,
        dimension: str,
        dim_conflicts: list[Conflict],
        stakeholder_by_id: dict[str, Stakeholder],
        hard_constraint_dims: set[str],
        org_stakeholder_ids: set[str],
    ) -> NegotiationProposal:
        """Build a single proposal for *dimension*."""
        is_hard_constraint = dimension in hard_constraint_dims

        # Collect all unique stakeholder ids involved in this dimension.
        involved_ids: set[str] = set()
        for c in dim_conflicts:
            involved_ids.add(c.stakeholder_a_id)
            involved_ids.add(c.stakeholder_b_id)

        # Gather weights and influences for each involved stakeholder.
        weights: dict[str, float] = {}
        influences: dict[str, float] = {}
        for sid in involved_ids:
            s = stakeholder_by_id.get(sid)
            if s is None:
                continue
            dim_obj = next(
                (d for d in s.interest_dimensions if d.dimension == dimension),
                None,
            )
            weights[sid] = dim_obj.weight if dim_obj is not None else 0.0
            influences[sid] = s.influence_weights.get(dimension, 0.0)

        if not weights:
            return NegotiationProposal(
                dimension=dimension,
                compromise_weight=0.0,
                concessions={},
                feasibility=1.0,
                non_negotiable=is_hard_constraint,
            )

        min_weight = min(weights.values())
        max_weight = max(weights.values())
        total_gap = max_weight - min_weight
        midpoint = (min_weight + max_weight) / 2.0

        # --- Hard constraint handling ---
        if is_hard_constraint:
            # Identify the constraint holder (org stakeholder).
            constraint_holder_ids = involved_ids & org_stakeholder_ids
            concessions: dict[str, float] = {}
            for sid in involved_ids:
                if sid in constraint_holder_ids:
                    concessions[sid] = 0.0
                else:
                    # Non-holder concedes the full gap towards the holder's weight.
                    concessions[sid] = total_gap

            # Compromise weight is the constraint holder's weight.
            holder_weights = [
                weights[sid] for sid in constraint_holder_ids if sid in weights
            ]
            compromise_weight = (
                holder_weights[0] if holder_weights else midpoint
            )
            compromise_weight = _clamp(compromise_weight, min_weight, max_weight)

            total_concession = sum(concessions.values())
            feasibility = self._compute_feasibility(
                total_concession, total_gap, len(involved_ids),
            )

            return NegotiationProposal(
                dimension=dimension,
                compromise_weight=compromise_weight,
                concessions=concessions,
                feasibility=feasibility,
                non_negotiable=True,
            )

        # --- Normal (negotiable) case: inverse-influence concession ---
        # For each pair of stakeholders, compute concessions using the
        # inverse-influence formula.  When more than two stakeholders are
        # involved we aggregate pairwise concessions per stakeholder.
        concessions = {sid: 0.0 for sid in involved_ids}

        for conflict in dim_conflicts:
            a_id = conflict.stakeholder_a_id
            b_id = conflict.stakeholder_b_id

            inf_a = max(influences.get(a_id, 0.0), _EPSILON)
            inf_b = max(influences.get(b_id, 0.0), _EPSILON)

            pair_gap = abs(weights.get(a_id, 0.0) - weights.get(b_id, 0.0))

            total_inv = (1.0 / inf_a) + (1.0 / inf_b)
            concession_a = (1.0 / inf_a) / total_inv * pair_gap
            concession_b = (1.0 / inf_b) / total_inv * pair_gap

            # Accumulate the maximum concession seen for each stakeholder
            # across all pairwise conflicts on this dimension.
            concessions[a_id] = max(concessions[a_id], concession_a)
            concessions[b_id] = max(concessions[b_id], concession_b)

        # Compute compromise weight: start from midpoint, adjust by
        # net concession direction.  Higher-influence stakeholders pull
        # the compromise towards their preferred weight.
        if len(involved_ids) == 2:
            ids = list(involved_ids)
            a_id, b_id = ids[0], ids[1]
            w_a, w_b = weights[a_id], weights[b_id]
            inf_a = max(influences.get(a_id, 0.0), _EPSILON)
            inf_b = max(influences.get(b_id, 0.0), _EPSILON)
            total_inv = (1.0 / inf_a) + (1.0 / inf_b)
            # Move from midpoint towards the higher-influence party.
            # concession_a moves A towards midpoint; concession_b moves B.
            shift_a = (1.0 / inf_a) / total_inv * (midpoint - w_a)
            shift_b = (1.0 / inf_b) / total_inv * (midpoint - w_b)
            compromise_weight = midpoint + shift_a + shift_b
        else:
            # Multi-party: weighted average by influence.
            total_inf = sum(
                max(influences.get(sid, 0.0), _EPSILON) for sid in involved_ids
            )
            compromise_weight = sum(
                weights[sid] * max(influences.get(sid, 0.0), _EPSILON)
                / total_inf
                for sid in involved_ids
            )

        compromise_weight = _clamp(compromise_weight, min_weight, max_weight)

        total_concession = sum(concessions.values())
        feasibility = self._compute_feasibility(
            total_concession, total_gap, len(involved_ids),
        )

        return NegotiationProposal(
            dimension=dimension,
            compromise_weight=compromise_weight,
            concessions=concessions,
            feasibility=feasibility,
            non_negotiable=False,
        )

    @staticmethod
    def _compute_feasibility(
        total_concession: float,
        total_gap: float,
        num_parties: int,
    ) -> float:
        """Feasibility = 1.0 - (total_concession / max_possible_concession).

        ``max_possible_concession`` is ``total_gap * num_parties`` (each party
        could theoretically concede the full gap).  Clamped to [0, 1].
        """
        max_possible = total_gap * max(num_parties, 1)
        if max_possible <= _EPSILON:
            return 1.0
        raw = 1.0 - (total_concession / max_possible)
        return _clamp(raw, 0.0, 1.0)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* to [lo, hi]."""
    return max(lo, min(hi, value))
