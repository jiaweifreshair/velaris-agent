"""利益冲突检测引擎 — Conflict Detection Engine.

分析 StakeholderMapModel 中多个 Stakeholder 之间在同一决策维度上的利益冲突。

两种冲突类型:
- Direction conflict: 两个 Stakeholder 在同一维度上偏好方向相反
- Weight conflict: 两个 Stakeholder 在同一维度上方向相同但权重差异 > 0.3
"""

from __future__ import annotations

from itertools import combinations

from velaris_agent.memory.types import (
    Conflict,
    PreferenceDirection,
    Stakeholder,
    StakeholderMapModel,
)


class ConflictDetectionEngine:
    """Detects dimension-level and weight-level conflicts in a stakeholder map."""

    def detect(self, map_model: StakeholderMapModel) -> list[Conflict]:
        """Identify all conflicts among stakeholders in *map_model*.

        Returns conflicts sorted by severity descending.
        Returns an empty list when no conflicts are found.
        """
        conflicts: list[Conflict] = []

        stakeholders = map_model.stakeholders
        if len(stakeholders) < 2:
            return conflicts

        for a, b in combinations(stakeholders, 2):
            conflicts.extend(self._detect_pair_conflicts(a, b))

        # Sort by severity descending
        conflicts.sort(key=lambda c: c.severity, reverse=True)
        return conflicts

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_pair_conflicts(
        self, a: Stakeholder, b: Stakeholder,
    ) -> list[Conflict]:
        """Detect direction and weight conflicts between two stakeholders."""
        results: list[Conflict] = []

        a_dims = {d.dimension: d for d in a.interest_dimensions}
        b_dims = {d.dimension: d for d in b.interest_dimensions}
        shared = set(a_dims.keys()) & set(b_dims.keys())

        for dim_name in shared:
            a_dim = a_dims[dim_name]
            b_dim = b_dims[dim_name]

            a_influence = a.influence_weights.get(dim_name, 0.0)
            b_influence = b.influence_weights.get(dim_name, 0.0)

            if a_dim.direction != b_dim.direction:
                # Direction conflict: opposite PreferenceDirection
                severity = _clamp(a_influence * b_influence)
                results.append(Conflict(
                    stakeholder_a_id=a.stakeholder_id,
                    stakeholder_b_id=b.stakeholder_id,
                    dimension=dim_name,
                    conflict_type="direction",
                    severity=severity,
                    details={
                        "direction_a": a_dim.direction.value,
                        "direction_b": b_dim.direction.value,
                        "influence_a": a_influence,
                        "influence_b": b_influence,
                    },
                ))
            else:
                # Same direction — check for weight conflict
                weight_diff = abs(a_dim.weight - b_dim.weight)
                if weight_diff > 0.3:
                    severity = _clamp(
                        a_influence * b_influence * weight_diff,
                    )
                    results.append(Conflict(
                        stakeholder_a_id=a.stakeholder_id,
                        stakeholder_b_id=b.stakeholder_id,
                        dimension=dim_name,
                        conflict_type="weight",
                        severity=severity,
                        details={
                            "direction": a_dim.direction.value,
                            "weight_a": a_dim.weight,
                            "weight_b": b_dim.weight,
                            "weight_diff": weight_diff,
                            "influence_a": a_influence,
                            "influence_b": b_influence,
                        },
                    ))

        return results


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* to [lo, hi]."""
    return max(lo, min(hi, value))
