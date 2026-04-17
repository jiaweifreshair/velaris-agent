"""End-to-end integration tests for the Stakeholder Mapping pipeline.

Tests the full flow:
  register stakeholders → build map → detect conflicts → generate negotiation
  → inject into engine → update curve tracker

Also covers backward compatibility and edge cases.

Requirements: 1.1–9.5 (all)
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from velaris_agent.biz.engine import build_capability_plan
from velaris_agent.memory.conflict_engine import ConflictDetectionEngine
from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.memory.negotiation import NegotiationStrategy
from velaris_agent.memory.stakeholder import (
    DecisionCurveTracker,
    StakeholderRegistry,
)
from velaris_agent.memory.stakeholder_map import StakeholderMapBuilder
from velaris_agent.memory.types import (
    AlignmentReport,
    DecisionRecord,
    InterestDimension,
    OrgPolicy,
    PreferenceDirection,
    Stakeholder,
    StakeholderRole,
    UserPreferences,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_stakeholder(
    sid: str = "user-alice",
    scenario: str = "travel",
    *,
    cost_weight: float = 0.8,
    quality_weight: float = 0.4,
    cost_direction: PreferenceDirection = PreferenceDirection.LOWER_IS_BETTER,
    quality_direction: PreferenceDirection = PreferenceDirection.HIGHER_IS_BETTER,
    cost_influence: float = 0.9,
    quality_influence: float = 0.7,
) -> Stakeholder:
    return Stakeholder(
        stakeholder_id=sid,
        role=StakeholderRole.USER,
        display_name=sid,
        scenario=scenario,
        interest_dimensions=[
            InterestDimension(dimension="cost", direction=cost_direction, weight=cost_weight),
            InterestDimension(dimension="quality", direction=quality_direction, weight=quality_weight),
        ],
        influence_weights={"cost": cost_influence, "quality": quality_influence},
    )


def _org_stakeholder(
    sid: str = "org-acme",
    scenario: str = "travel",
    *,
    cost_weight: float = 0.3,
    quality_weight: float = 0.9,
    cost_direction: PreferenceDirection = PreferenceDirection.LOWER_IS_BETTER,
    quality_direction: PreferenceDirection = PreferenceDirection.HIGHER_IS_BETTER,
    cost_influence: float = 0.6,
    quality_influence: float = 0.8,
) -> Stakeholder:
    return Stakeholder(
        stakeholder_id=sid,
        role=StakeholderRole.ORG,
        display_name=sid,
        scenario=scenario,
        interest_dimensions=[
            InterestDimension(dimension="cost", direction=cost_direction, weight=cost_weight),
            InterestDimension(dimension="quality", direction=quality_direction, weight=quality_weight),
        ],
        influence_weights={"cost": cost_influence, "quality": quality_influence},
    )


def _make_decision_record(scenario: str = "travel") -> DecisionRecord:
    return DecisionRecord(
        decision_id="dec-integration-001",
        user_id="user-alice",
        org_id="org-acme",
        scenario=scenario,
        query="find best travel option",
        created_at=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Full pipeline integration test
# ---------------------------------------------------------------------------


class TestFullStakeholderPipeline:
    """Register → build map → detect conflicts → negotiate → engine → curve."""

    def test_full_flow_with_conflicting_stakeholders(self) -> None:
        """End-to-end: two stakeholders with opposing cost preferences."""
        registry = StakeholderRegistry()

        # 1. Register stakeholders — user wants low cost, org wants high quality
        user = _user_stakeholder(cost_weight=0.8, quality_weight=0.3)
        org = _org_stakeholder(
            cost_weight=0.2,
            quality_weight=0.9,
            cost_direction=PreferenceDirection.HIGHER_IS_BETTER,
        )
        registry.register(user)
        registry.register(org)

        # 2. Build map
        builder = StakeholderMapBuilder(registry)
        map_model = builder.build("travel")

        assert len(map_model.stakeholders) == 2
        assert len(map_model.alignment_matrix) == 1
        assert map_model.scenario == "travel"
        assert map_model.timestamp is not None

        # 3. Detect conflicts
        engine = ConflictDetectionEngine()
        conflicts = engine.detect(map_model)

        # There should be a direction conflict on "cost" (lower vs higher)
        cost_conflicts = [c for c in conflicts if c.dimension == "cost"]
        assert len(cost_conflicts) >= 1
        assert cost_conflicts[0].conflict_type == "direction"
        assert 0.0 <= cost_conflicts[0].severity <= 1.0

        # Conflicts sorted by severity descending
        for i in range(len(conflicts) - 1):
            assert conflicts[i].severity >= conflicts[i + 1].severity

        # 4. Generate negotiation proposals
        negotiation = NegotiationStrategy()
        proposals = negotiation.generate(conflicts, map_model)

        assert len(proposals) >= 1
        cost_proposals = [p for p in proposals if p.dimension == "cost"]
        assert len(cost_proposals) == 1
        assert 0.0 <= cost_proposals[0].feasibility <= 1.0
        assert cost_proposals[0].non_negotiable is False

        # 5. Inject into engine via build_capability_plan
        plan = build_capability_plan(
            query="find best travel option",
            scenario="travel",
            stakeholder_map=map_model,
        )

        assert "stakeholder_context" in plan
        ctx = plan["stakeholder_context"]
        assert ctx["scenario"] == "travel"
        assert len(ctx["stakeholder_ids"]) == 2

        # Merged weights should differ from default travel weights
        assert "decision_weights" in plan

        # 6. Update curve tracker
        memory = DecisionMemory.__new__(DecisionMemory)
        tracker = DecisionCurveTracker(memory=memory, registry=registry)
        record = _make_decision_record()
        tracker.update(record, map_model)

        # Each stakeholder should have a curve point
        user_curve = tracker.get_curve("user-alice", "travel")
        org_curve = tracker.get_curve("org-acme", "travel")
        assert len(user_curve) == 1
        assert len(org_curve) == 1
        assert user_curve[0].decision_count >= 1
        assert 0.0 <= user_curve[0].weight_stability <= 1.0

    def test_full_flow_with_aligned_stakeholders(self) -> None:
        """Two stakeholders with same preferences → no conflicts."""
        registry = StakeholderRegistry()

        user = _user_stakeholder(cost_weight=0.7, quality_weight=0.6)
        org = _org_stakeholder(cost_weight=0.7, quality_weight=0.6)
        registry.register(user)
        registry.register(org)

        builder = StakeholderMapBuilder(registry)
        map_model = builder.build("travel")

        assert len(map_model.alignment_matrix) == 1
        alignment = map_model.alignment_matrix[0]
        # Same directions and same weights → high alignment
        assert alignment.score >= 0.7
        assert alignment.classification == "aligned"

        engine = ConflictDetectionEngine()
        conflicts = engine.detect(map_model)
        # No direction conflicts, no weight conflicts (diff <= 0.3)
        assert len(conflicts) == 0

        negotiation = NegotiationStrategy()
        proposals = negotiation.generate(conflicts, map_model)
        assert len(proposals) == 0

    def test_full_flow_with_hard_constraint(self) -> None:
        """Org has a hard constraint on cost → non-negotiable proposal."""
        registry = StakeholderRegistry()

        user = _user_stakeholder(
            cost_weight=0.9,
            cost_direction=PreferenceDirection.HIGHER_IS_BETTER,
        )
        org = _org_stakeholder(cost_weight=0.2)
        registry.register(user)
        registry.register(org)

        builder = StakeholderMapBuilder(registry)
        map_model = builder.build("travel")

        engine = ConflictDetectionEngine()
        conflicts = engine.detect(map_model)
        assert len(conflicts) >= 1

        org_policy = OrgPolicy(
            org_id="org-acme",
            scenario="travel",
            weights={"cost": 0.5},
            constraints={"cost": 5000},
        )
        negotiation = NegotiationStrategy()
        proposals = negotiation.generate(conflicts, map_model, org_policy=org_policy)

        cost_proposals = [p for p in proposals if p.dimension == "cost"]
        assert len(cost_proposals) == 1
        assert cost_proposals[0].non_negotiable is True
        # Org (constraint holder) concession should be 0
        assert cost_proposals[0].concessions.get("org-acme", -1) == 0.0

    def test_full_flow_with_relationship_stakeholder(self) -> None:
        """Register user + org + relationship, build map with all three."""
        registry = StakeholderRegistry()

        user = _user_stakeholder()
        org = _org_stakeholder()
        registry.register(user)
        registry.register(org)

        rel = Stakeholder(
            stakeholder_id="rel-alice-acme",
            role=StakeholderRole.RELATIONSHIP,
            display_name="Alice-Acme Relationship",
            scenario="travel",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.5,
                ),
            ],
            influence_weights={"cost": 0.5},
            related_stakeholder_ids=["user-alice", "org-acme"],
        )
        registry.register(rel)

        builder = StakeholderMapBuilder(registry)
        map_model = builder.build("travel")

        assert len(map_model.stakeholders) == 3
        # 3 stakeholders → C(3,2) = 3 pairwise alignments
        assert len(map_model.alignment_matrix) == 3


# ---------------------------------------------------------------------------
# Backward compatibility tests
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Ensure old code paths still work after the stakeholder upgrade."""

    def test_old_decision_record_without_stakeholder_context(self) -> None:
        """DecisionRecord with empty env_snapshot loads without error (Req 9.5)."""
        record = DecisionRecord(
            decision_id="dec-old-001",
            user_id="u1",
            scenario="travel",
            query="old query",
            env_snapshot={},
            created_at=datetime.now(tz=timezone.utc),
        )
        # Accessing stakeholder_context should return None
        ctx = record.env_snapshot.get("stakeholder_context")
        assert ctx is None

    def test_old_decision_record_with_extra_env_fields(self) -> None:
        """Old records with arbitrary env_snapshot keys still parse."""
        record = DecisionRecord(
            decision_id="dec-old-002",
            user_id="u1",
            scenario="travel",
            query="old query",
            env_snapshot={"market_trend": "up", "season": "peak"},
            created_at=datetime.now(tz=timezone.utc),
        )
        assert record.env_snapshot["market_trend"] == "up"
        assert record.env_snapshot.get("stakeholder_context") is None

    def test_compute_alignment_existing_signature(self, tmp_path: object) -> None:
        """PreferenceLearner.compute_alignment(user_id, org_policy) still works (Req 9.3)."""
        from velaris_agent.memory.preference_learner import PreferenceLearner

        memory = DecisionMemory(base_dir=tmp_path)
        learner = PreferenceLearner(memory)

        policy = OrgPolicy(
            org_id="org-test",
            scenario="travel",
            weights={"price": 0.4, "time": 0.35, "comfort": 0.25},
        )
        report = learner.compute_alignment("user-test", policy)

        assert isinstance(report, AlignmentReport)
        assert report.user_id == "user-test"
        assert report.org_id == "org-test"
        assert report.scenario == "travel"
        assert 0.0 <= report.alignment_score <= 1.0
        assert isinstance(report.conflicts, list)
        assert isinstance(report.synergies, list)
        assert isinstance(report.negotiation_space, dict)

    def test_build_capability_plan_without_stakeholder_map(self) -> None:
        """build_capability_plan with no stakeholder_map preserves old behavior (Req 6.5)."""
        plan_without = build_capability_plan(query="travel to Beijing", scenario="travel")
        plan_none = build_capability_plan(
            query="travel to Beijing", scenario="travel", stakeholder_map=None,
        )

        assert "stakeholder_context" not in plan_without
        assert "stakeholder_context" not in plan_none
        assert plan_without["decision_weights"] == plan_none["decision_weights"]

    def test_export_as_alignment_report(self) -> None:
        """StakeholderMapBuilder.export_as_alignment_report produces valid AlignmentReport (Req 9.4)."""
        registry = StakeholderRegistry()
        registry.register(_user_stakeholder())
        registry.register(_org_stakeholder())

        builder = StakeholderMapBuilder(registry)
        map_model = builder.build("travel")

        report = builder.export_as_alignment_report(
            map_model, user_id="user-alice", org_id="org-acme",
        )

        assert isinstance(report, AlignmentReport)
        assert report.user_id == "user-alice"
        assert report.org_id == "org-acme"
        assert report.scenario == "travel"
        assert 0.0 <= report.alignment_score <= 1.0
        assert isinstance(report.conflicts, list)
        assert isinstance(report.synergies, list)

    def test_migration_from_user_preferences(self) -> None:
        """from_user_preferences produces a valid registerable Stakeholder (Req 9.1)."""
        registry = StakeholderRegistry()
        prefs = UserPreferences(
            user_id="migrated-user",
            scenario="career",
            weights={"growth": 0.8, "income": 0.6},
            confidence=0.7,
        )
        stakeholder = registry.from_user_preferences(prefs)

        assert stakeholder.role == StakeholderRole.USER
        assert stakeholder.stakeholder_id == "migrated-user"
        dim_names = {d.dimension for d in stakeholder.interest_dimensions}
        assert dim_names == {"growth", "income"}
        assert stakeholder.influence_weights["growth"] == 0.7
        assert stakeholder.influence_weights["income"] == 0.7

        # Should be registerable
        sid = registry.register(stakeholder)
        assert sid == "migrated-user"

    def test_migration_from_org_policy(self) -> None:
        """from_org_policy produces a valid registerable Stakeholder (Req 9.2)."""
        registry = StakeholderRegistry()
        policy = OrgPolicy(
            org_id="migrated-org",
            scenario="career",
            weights={"compliance": 0.5, "cost": 0.3},
            constraints={"cost": 10000},
        )
        stakeholder = registry.from_org_policy(policy)

        assert stakeholder.role == StakeholderRole.ORG
        dim_map = {d.dimension: d.direction for d in stakeholder.interest_dimensions}
        assert dim_map["cost"] == PreferenceDirection.LOWER_IS_BETTER
        assert dim_map["compliance"] == PreferenceDirection.HIGHER_IS_BETTER

        sid = registry.register(stakeholder)
        assert sid == "migrated-org"


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: 0 stakeholders, 1 stakeholder, missing refs."""

    def test_zero_stakeholders(self) -> None:
        """Build map with 0 stakeholders → valid empty map."""
        registry = StakeholderRegistry()
        builder = StakeholderMapBuilder(registry)
        map_model = builder.build("empty-scenario")

        assert len(map_model.stakeholders) == 0
        assert len(map_model.alignment_matrix) == 0
        assert map_model.scenario == "empty-scenario"

        # Conflict detection on empty map
        engine = ConflictDetectionEngine()
        conflicts = engine.detect(map_model)
        assert conflicts == []

        # Negotiation on empty conflicts
        negotiation = NegotiationStrategy()
        proposals = negotiation.generate(conflicts, map_model)
        assert proposals == []

        # Engine with empty map
        plan = build_capability_plan(
            query="test", scenario="travel", stakeholder_map=map_model,
        )
        assert "stakeholder_context" in plan

    def test_one_stakeholder(self) -> None:
        """Build map with 1 stakeholder → valid map, empty alignment matrix."""
        registry = StakeholderRegistry()
        registry.register(_user_stakeholder())

        builder = StakeholderMapBuilder(registry)
        map_model = builder.build("travel")

        assert len(map_model.stakeholders) == 1
        assert len(map_model.alignment_matrix) == 0

        engine = ConflictDetectionEngine()
        conflicts = engine.detect(map_model)
        assert conflicts == []

    def test_relationship_with_missing_refs_raises(self) -> None:
        """Relationship stakeholder referencing non-existent IDs raises ValueError."""
        registry = StakeholderRegistry()
        rel = Stakeholder(
            stakeholder_id="rel-ghost",
            role=StakeholderRole.RELATIONSHIP,
            display_name="Ghost Relationship",
            scenario="travel",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.5,
                ),
            ],
            influence_weights={"cost": 0.5},
            related_stakeholder_ids=["ghost-a", "ghost-b"],
        )
        with pytest.raises(ValueError, match="not found"):
            registry.register(rel)

    def test_relationship_with_wrong_ref_count_raises(self) -> None:
        """Relationship stakeholder with != 2 refs raises ValueError."""
        registry = StakeholderRegistry()
        rel = Stakeholder(
            stakeholder_id="rel-bad",
            role=StakeholderRole.RELATIONSHIP,
            display_name="Bad Relationship",
            scenario="travel",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.5,
                ),
            ],
            influence_weights={"cost": 0.5},
            related_stakeholder_ids=["only-one"],
        )
        with pytest.raises(ValueError, match="exactly 2"):
            registry.register(rel)

    def test_curve_tracker_trend_detection(self) -> None:
        """Trend detection with multiple updates."""
        registry = StakeholderRegistry()
        registry.register(_user_stakeholder())
        registry.register(_org_stakeholder())

        builder = StakeholderMapBuilder(registry)
        memory = DecisionMemory.__new__(DecisionMemory)
        tracker = DecisionCurveTracker(memory=memory, registry=registry)

        # Simulate 3 decisions to enable trend detection
        for i in range(3):
            map_model = builder.build("travel")
            record = DecisionRecord(
                decision_id=f"dec-trend-{i:03d}",
                user_id="user-alice",
                scenario="travel",
                query=f"query {i}",
                created_at=datetime.now(tz=timezone.utc),
            )
            tracker.update(record, map_model)

        # Should have 3 curve points per stakeholder
        user_curve = tracker.get_curve("user-alice", "travel")
        assert len(user_curve) == 3

        # Trend detection should return a valid string
        trend = tracker.detect_trends("user-alice", "org-acme", "travel")
        assert trend in {"convergence", "divergence", "stable"}

    def test_high_severity_conflict_produces_warning_in_plan(self) -> None:
        """Conflicts with severity > 0.5 produce warnings in the plan (Req 6.4)."""
        registry = StakeholderRegistry()

        # Create stakeholders with opposing directions and high influence
        # to ensure severity > 0.5
        user = _user_stakeholder(
            cost_weight=0.9,
            cost_influence=0.9,
            quality_influence=0.9,
        )
        org = _org_stakeholder(
            cost_weight=0.9,
            cost_direction=PreferenceDirection.HIGHER_IS_BETTER,
            cost_influence=0.9,
            quality_influence=0.9,
        )
        registry.register(user)
        registry.register(org)

        builder = StakeholderMapBuilder(registry)
        map_model = builder.build("travel")

        plan = build_capability_plan(
            query="travel query",
            scenario="travel",
            stakeholder_map=map_model,
        )

        # The plan should contain a warning about unresolved conflicts
        assert "explanation" in plan
        assert "conflict" in plan["explanation"].lower() or "⚠" in plan["explanation"]

    def test_serialization_round_trip_of_stakeholder_map(self) -> None:
        """StakeholderMapModel serializes and deserializes correctly (Req 8.1-8.3)."""
        from velaris_agent.memory.types import StakeholderMapModel

        registry = StakeholderRegistry()
        registry.register(_user_stakeholder())
        registry.register(_org_stakeholder())

        builder = StakeholderMapBuilder(registry)
        map_model = builder.build("travel")

        # Serialize → deserialize → serialize should be identical
        json_str = map_model.model_dump_json()
        restored = StakeholderMapModel.model_validate_json(json_str)
        json_str_2 = restored.model_dump_json()

        assert json_str == json_str_2
