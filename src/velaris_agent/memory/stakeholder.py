"""利益相关方注册表 — Stakeholder Registry & Decision Curve Tracker.

负责 Stakeholder 的创建、检索、更新和删除 (CRUD),
以及字段验证、重复检查和引用完整性保护。

存储: 内存 dict, key = (stakeholder_id, scenario)。

DecisionCurveTracker 按 Stakeholder 维度追踪决策曲线,
计算每个 Stakeholder 的决策指标并检测趋势。
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from velaris_agent.memory.types import (
    DecisionActor,
    DecisionCurvePoint,
    DecisionRecord,
    InterestDimension,
    OrgPolicy,
    PreferenceDirection,
    Stakeholder,
    StakeholderMapModel,
    StakeholderRole,
    UserPreferences,
)


class StakeholderRegistry:
    """In-memory registry for Stakeholder entities."""

    def __init__(self) -> None:
        # Primary storage: (stakeholder_id, scenario) → Stakeholder
        self._store: dict[tuple[str, str], Stakeholder] = {}
        # Track which (stakeholder_id, scenario) keys are referenced by active maps
        self._active_maps: set[tuple[str, str]] = set()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(self, stakeholder: Stakeholder) -> str:
        """Validate, check duplicates, persist, and return the stakeholder_id."""
        self._validate_stakeholder(stakeholder)
        self._check_duplicate(stakeholder)
        self._check_relationship_refs(stakeholder)

        # Set timestamps if not provided
        now = datetime.now(tz=timezone.utc)
        updates: dict[str, object] = {}
        if stakeholder.created_at is None:
            updates["created_at"] = now
        if stakeholder.updated_at is None:
            updates["updated_at"] = now
        if updates:
            stakeholder = stakeholder.model_copy(update=updates)

        key = (stakeholder.stakeholder_id, stakeholder.scenario)
        self._store[key] = stakeholder
        return stakeholder.stakeholder_id

    def get(self, stakeholder_id: str, scenario: str) -> Stakeholder | None:
        """Return the Stakeholder or ``None`` if not found."""
        return self._store.get((stakeholder_id, scenario))

    def update(
        self, stakeholder_id: str, scenario: str, **fields: object
    ) -> Stakeholder:
        """Merge *fields* into the existing Stakeholder, bump version."""
        key = (stakeholder_id, scenario)
        existing = self._store.get(key)
        if existing is None:
            msg = (
                f"Stakeholder '{stakeholder_id}' in scenario "
                f"'{scenario}' not found"
            )
            raise KeyError(msg)

        # Increment version and set updated_at
        fields["version"] = existing.version + 1
        fields["updated_at"] = datetime.now(tz=timezone.utc)

        updated = existing.model_copy(update=fields)
        self._store[key] = updated
        return updated

    def remove(self, stakeholder_id: str, scenario: str) -> None:
        """Soft-delete: set ``active=False``.

        Raises ``ValueError`` if the stakeholder is referenced by an active
        ``StakeholderMap`` (tracked via ``_active_maps``).
        """
        key = (stakeholder_id, scenario)
        existing = self._store.get(key)
        if existing is None:
            msg = (
                f"Stakeholder '{stakeholder_id}' in scenario "
                f"'{scenario}' not found"
            )
            raise KeyError(msg)

        self._check_in_use(stakeholder_id, scenario)

        self._store[key] = existing.model_copy(
            update={
                "active": False,
                "updated_at": datetime.now(tz=timezone.utc),
            },
        )

    def list_active(
        self,
        scenario: str,
        role: StakeholderRole | None = None,
    ) -> list[Stakeholder]:
        """Return active stakeholders matching *scenario* and optional *role*."""
        results: list[Stakeholder] = []
        for s in self._store.values():
            if s.scenario != scenario or not s.active:
                continue
            if role is not None and s.role != role:
                continue
            results.append(s)
        return results

    # ------------------------------------------------------------------
    # Active-map tracking helpers
    # ------------------------------------------------------------------

    def mark_in_map(self, stakeholder_id: str, scenario: str) -> None:
        """Record that this stakeholder is part of an active map."""
        self._active_maps.add((stakeholder_id, scenario))

    def unmark_from_map(self, stakeholder_id: str, scenario: str) -> None:
        """Remove the active-map reference for this stakeholder."""
        self._active_maps.discard((stakeholder_id, scenario))

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_stakeholder(self, s: Stakeholder) -> None:
        """Check structural completeness of a Stakeholder."""
        if not s.stakeholder_id:
            raise ValueError("stakeholder_id must be non-empty")
        if not s.display_name:
            raise ValueError("display_name must be non-empty")
        if not s.scenario:
            raise ValueError("scenario must be non-empty")
        if not s.interest_dimensions:
            raise ValueError("interest_dimensions must contain at least one entry")
        if not s.influence_weights:
            raise ValueError("influence_weights must be non-empty")
        # Pydantic already validates individual weight ranges via the
        # field_validator on Stakeholder, but we double-check here for safety.
        for dim, weight in s.influence_weights.items():
            if not (0.0 <= weight <= 1.0):
                msg = (
                    f"influence_weights['{dim}'] = {weight} "
                    f"is outside the allowed range [0.0, 1.0]"
                )
                raise ValueError(msg)

    def _check_duplicate(self, s: Stakeholder) -> None:
        """Raise ``ValueError`` if the same id+scenario already exists."""
        key = (s.stakeholder_id, s.scenario)
        if key in self._store:
            msg = (
                f"Stakeholder '{s.stakeholder_id}' already registered "
                f"in scenario '{s.scenario}'"
            )
            raise ValueError(msg)

    def _check_relationship_refs(self, s: Stakeholder) -> None:
        """If role is *relationship*, require exactly 2 related ids that exist."""
        if s.role != StakeholderRole.RELATIONSHIP:
            return
        if len(s.related_stakeholder_ids) != 2:
            msg = (
                f"Relationship stakeholder '{s.stakeholder_id}' must reference "
                f"exactly 2 related stakeholder IDs, got "
                f"{len(s.related_stakeholder_ids)}"
            )
            raise ValueError(msg)
        for ref_id in s.related_stakeholder_ids:
            if (ref_id, s.scenario) not in self._store:
                msg = (
                    f"Related stakeholder '{ref_id}' not found in "
                    f"scenario '{s.scenario}'"
                )
                raise ValueError(msg)

    def _check_in_use(self, stakeholder_id: str, scenario: str) -> None:
        """Raise ``ValueError`` if the stakeholder is in an active map."""
        if (stakeholder_id, scenario) in self._active_maps:
            msg = (
                f"Cannot remove stakeholder '{stakeholder_id}' in scenario "
                f"'{scenario}': still referenced by an active StakeholderMap"
            )
            raise ValueError(msg)

    # ------------------------------------------------------------------
    # Migration helpers
    # ------------------------------------------------------------------

    def from_user_preferences(self, prefs: UserPreferences) -> Stakeholder:
        """Create a user-type Stakeholder from a :class:`UserPreferences`.

        * ``prefs.weights`` → ``InterestDimension`` list (all
          ``higher_is_better``).
        * ``prefs.confidence`` → uniform influence weight for every
          dimension.
        """
        interest_dimensions = [
            InterestDimension(
                dimension=dim,
                direction=PreferenceDirection.HIGHER_IS_BETTER,
                weight=w,
            )
            for dim, w in prefs.weights.items()
        ]

        influence_weights = {
            dim: prefs.confidence for dim in prefs.weights
        }

        return Stakeholder(
            stakeholder_id=prefs.user_id,
            role=StakeholderRole.USER,
            display_name=prefs.user_id,
            scenario=prefs.scenario,
            interest_dimensions=interest_dimensions,
            influence_weights=influence_weights,
        )

    def from_org_policy(self, policy: OrgPolicy) -> Stakeholder:
        """Create an org-type Stakeholder from an :class:`OrgPolicy`.

        * ``policy.weights`` → ``InterestDimension`` list.  Dimensions
          that appear as keys in ``policy.constraints`` are treated as
          non-negotiable (direction ``lower_is_better``); all others
          default to ``higher_is_better``.
        * Influence weight per dimension is the policy weight itself,
          clamped to [0, 1].
        """
        constraint_dims = set(policy.constraints.keys())

        interest_dimensions = [
            InterestDimension(
                dimension=dim,
                direction=(
                    PreferenceDirection.LOWER_IS_BETTER
                    if dim in constraint_dims
                    else PreferenceDirection.HIGHER_IS_BETTER
                ),
                weight=w,
            )
            for dim, w in policy.weights.items()
        ]

        influence_weights = {
            dim: max(0.0, min(1.0, w)) for dim, w in policy.weights.items()
        }

        return Stakeholder(
            stakeholder_id=policy.org_id,
            role=StakeholderRole.ORG,
            display_name=policy.org_id,
            scenario=policy.scenario,
            interest_dimensions=interest_dimensions,
            influence_weights=influence_weights,
        )


class DecisionCurveTracker:
    """Per-stakeholder decision curve tracking.

    Tracks decision metrics per stakeholder over time, stores curve points
    in-memory keyed by ``(stakeholder_id, scenario)``, and detects
    convergence/divergence trends between stakeholder pairs.
    """

    def __init__(
        self,
        memory: object,  # DecisionMemory — kept as object to avoid circular import
        registry: StakeholderRegistry,
    ) -> None:
        self._memory = memory
        self._registry = registry
        # (stakeholder_id, scenario) → list of DecisionCurvePoint (append-order)
        self._curves: dict[tuple[str, str], list[DecisionCurvePoint]] = {}
        # Track raw weights per stakeholder for weight_stability calculation
        self._weight_history: dict[tuple[str, str], list[float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        record: DecisionRecord,
        map_model: StakeholderMapModel,
    ) -> None:
        """Create/update a :class:`DecisionCurvePoint` for every stakeholder
        in *map_model* based on the completed *record*.
        """
        now = datetime.now(tz=timezone.utc)
        period = now.strftime("%Y-%m-%d")

        for stakeholder in map_model.stakeholders:
            sid = stakeholder.stakeholder_id
            scenario = stakeholder.scenario
            key = (sid, scenario)

            # Accumulate weight history for stability calculation
            weights = list(stakeholder.influence_weights.values())
            avg_weight = sum(weights) / len(weights) if weights else 0.0
            self._weight_history.setdefault(key, []).append(avg_weight)

            # Compute per-stakeholder metrics
            existing_points = self._curves.get(key, [])
            prev_count = existing_points[-1].decision_count if existing_points else 0
            decision_count = prev_count + 1

            acceptance_rate = self._compute_acceptance_rate(existing_points)
            bias_count = self._compute_bias_count(
                stakeholder, map_model,
            )
            weight_stability = self._compute_weight_stability(key)

            # Determine actor type from stakeholder role
            actor = (
                DecisionActor.ORG
                if stakeholder.role == StakeholderRole.ORG
                else DecisionActor.USER
            )

            # Compute alignment score for this stakeholder (average of
            # pairwise alignments involving this stakeholder)
            alignment_score = self._compute_alignment_score(
                sid, map_model,
            )

            point = DecisionCurvePoint(
                period=period,
                actor=actor,
                actor_id=sid,
                scenario=scenario,
                decision_count=decision_count,
                acceptance_rate=acceptance_rate,
                bias_count=bias_count,
                alignment_score=alignment_score,
                weight_stability=weight_stability,
            )

            self._curves.setdefault(key, []).append(point)

    def get_curve(
        self,
        stakeholder_id: str,
        scenario: str,
        window_days: int = 30,
    ) -> list[DecisionCurvePoint]:
        """Return time-ordered curve points within *window_days*."""
        key = (stakeholder_id, scenario)
        points = self._curves.get(key, [])
        if not points:
            return []

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=window_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        filtered = [p for p in points if p.period >= cutoff_str]
        # Sort by period ascending (time-ordered)
        filtered.sort(key=lambda p: p.period)
        return filtered

    def detect_trends(
        self,
        stakeholder_a_id: str,
        stakeholder_b_id: str,
        scenario: str,
    ) -> str:
        """Detect alignment trend between two stakeholders.

        Compares alignment scores across consecutive periods:
        - 3 consecutive increasing → ``"convergence"``
        - 3 consecutive decreasing → ``"divergence"``
        - otherwise → ``"stable"``
        """
        # Collect alignment scores from stakeholder_a's curve that
        # reflect the pairwise relationship
        key_a = (stakeholder_a_id, scenario)
        points_a = self._curves.get(key_a, [])

        if len(points_a) < 3:
            return "stable"

        # Use the last 3 alignment scores
        scores = [
            p.alignment_score
            for p in points_a[-3:]
            if p.alignment_score is not None
        ]

        if len(scores) < 3:
            return "stable"

        # Check for 3 consecutive increasing
        if scores[0] < scores[1] < scores[2]:
            return "convergence"

        # Check for 3 consecutive decreasing
        if scores[0] > scores[1] > scores[2]:
            return "divergence"

        return "stable"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_acceptance_rate(
        existing_points: list[DecisionCurvePoint],
    ) -> float:
        """Simplified acceptance rate: use 0.5 as default."""
        if not existing_points:
            return 0.5
        # Running average: blend previous rate with 0.5 default for new decision
        prev_rate = existing_points[-1].acceptance_rate
        prev_count = existing_points[-1].decision_count
        # Weighted running average
        return (prev_rate * prev_count + 0.5) / (prev_count + 1)

    @staticmethod
    def _compute_bias_count(
        stakeholder: Stakeholder,
        map_model: StakeholderMapModel,
    ) -> int:
        """Count decisions where stakeholder's weight deviated significantly
        from the mean weight across all stakeholders.
        """
        if len(map_model.stakeholders) < 2:
            return 0

        bias_count = 0
        # For each dimension, check if this stakeholder's weight deviates
        # significantly from the mean
        dim_names = set(stakeholder.influence_weights.keys())
        for dim in dim_names:
            my_weight = stakeholder.influence_weights.get(dim, 0.0)
            all_weights = [
                s.influence_weights.get(dim, 0.0)
                for s in map_model.stakeholders
                if dim in s.influence_weights
            ]
            if len(all_weights) < 2:
                continue
            mean_weight = sum(all_weights) / len(all_weights)
            if abs(my_weight - mean_weight) > 0.3:
                bias_count += 1

        return bias_count

    def _compute_weight_stability(
        self,
        key: tuple[str, str],
    ) -> float:
        """Compute weight stability as ``1 - stddev(recent_weights)``,
        clamped to [0, 1].
        """
        history = self._weight_history.get(key, [])
        if len(history) < 2:
            return 1.0  # Not enough data → assume stable

        # Use up to the last 10 weights
        recent = history[-10:]
        mean = sum(recent) / len(recent)
        variance = sum((w - mean) ** 2 for w in recent) / len(recent)
        stddev = math.sqrt(variance)

        stability = 1.0 - stddev
        return max(0.0, min(1.0, stability))

    @staticmethod
    def _compute_alignment_score(
        stakeholder_id: str,
        map_model: StakeholderMapModel,
    ) -> float | None:
        """Average pairwise alignment score involving this stakeholder."""
        relevant = [
            pa
            for pa in map_model.alignment_matrix
            if pa.stakeholder_a_id == stakeholder_id
            or pa.stakeholder_b_id == stakeholder_id
        ]
        if not relevant:
            return None
        return sum(pa.score for pa in relevant) / len(relevant)
