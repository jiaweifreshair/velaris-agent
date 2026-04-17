"""Tests for stakeholder integration in build_capability_plan()."""

from __future__ import annotations

from datetime import UTC, datetime

from velaris_agent.biz.engine import build_capability_plan
from velaris_agent.memory.types import (
    Conflict,
    InterestDimension,
    PairwiseAlignment,
    PreferenceDirection,
    Stakeholder,
    StakeholderMapModel,
    StakeholderRole,
)


def _make_stakeholder_map(
    *,
    scenario: str = "travel",
    stakeholders: list[Stakeholder] | None = None,
    conflicts: list[Conflict] | None = None,
    alignment_matrix: list[PairwiseAlignment] | None = None,
) -> StakeholderMapModel:
    """Build a minimal StakeholderMapModel for testing."""
    return StakeholderMapModel(
        map_id="test-map",
        scenario=scenario,
        stakeholders=stakeholders or [],
        alignment_matrix=alignment_matrix or [],
        conflicts=conflicts or [],
        timestamp=datetime.now(UTC),
    )


def _user_stakeholder() -> Stakeholder:
    return Stakeholder(
        stakeholder_id="user-1",
        role=StakeholderRole.USER,
        display_name="Test User",
        scenario="travel",
        interest_dimensions=[
            InterestDimension(
                dimension="price",
                direction=PreferenceDirection.LOWER_IS_BETTER,
                weight=0.8,
            ),
            InterestDimension(
                dimension="comfort",
                direction=PreferenceDirection.HIGHER_IS_BETTER,
                weight=0.6,
            ),
        ],
        influence_weights={"price": 0.9, "comfort": 0.7},
    )


def _org_stakeholder() -> Stakeholder:
    return Stakeholder(
        stakeholder_id="org-1",
        role=StakeholderRole.ORG,
        display_name="Test Org",
        scenario="travel",
        interest_dimensions=[
            InterestDimension(
                dimension="price",
                direction=PreferenceDirection.LOWER_IS_BETTER,
                weight=0.3,
            ),
            InterestDimension(
                dimension="comfort",
                direction=PreferenceDirection.HIGHER_IS_BETTER,
                weight=0.9,
            ),
        ],
        influence_weights={"price": 0.5, "comfort": 0.8},
    )


# --- Tests: backward compatibility (stakeholder_map=None) ---


def test_no_stakeholder_map_preserves_existing_behavior():
    """Req 6.5: When stakeholder_map is None, output is identical to old behavior."""
    plan_without = build_capability_plan(
        query="下周去上海出差",
        scenario="travel",
    )
    plan_with_none = build_capability_plan(
        query="下周去上海出差",
        scenario="travel",
        stakeholder_map=None,
    )
    assert plan_without == plan_with_none
    assert "stakeholder_context" not in plan_without


# --- Tests: stakeholder context injection ---


def test_stakeholder_map_injects_context():
    """Req 6.1, 6.3: When stakeholder_map is provided, plan includes stakeholder_context."""
    smap = _make_stakeholder_map(
        stakeholders=[_user_stakeholder(), _org_stakeholder()],
    )
    plan = build_capability_plan(
        query="下周去上海出差",
        scenario="travel",
        stakeholder_map=smap,
    )
    assert "stakeholder_context" in plan
    ctx = plan["stakeholder_context"]
    assert ctx["scenario"] == "travel"
    assert set(ctx["stakeholder_ids"]) == {"user-1", "org-1"}


# --- Tests: weight merging ---


def test_stakeholder_weights_merged_into_decision_weights():
    """Req 6.2: Stakeholder influence weights are averaged with scenario weights."""
    smap = _make_stakeholder_map(
        stakeholders=[_user_stakeholder(), _org_stakeholder()],
    )
    plan_base = build_capability_plan(query="下周去上海出差", scenario="travel")
    plan_merged = build_capability_plan(
        query="下周去上海出差",
        scenario="travel",
        stakeholder_map=smap,
    )
    # price: scenario=0.4, stakeholders mean=(0.9+0.5)/2=0.7, merged=(0.4+0.7)/2=0.55
    assert plan_merged["decision_weights"]["price"] != plan_base["decision_weights"]["price"]
    assert abs(plan_merged["decision_weights"]["price"] - 0.55) < 1e-9

    # comfort: scenario=0.25, stakeholders mean=(0.7+0.8)/2=0.75, merged=(0.25+0.75)/2=0.5
    assert abs(plan_merged["decision_weights"]["comfort"] - 0.5) < 1e-9

    # time: no stakeholder influence → unchanged at 0.35
    assert plan_merged["decision_weights"]["time"] == plan_base["decision_weights"]["time"]


# --- Tests: high-severity conflict warnings ---


def test_high_severity_conflicts_produce_warnings():
    """Req 6.4: Conflicts with severity > 0.5 produce warning in explanation."""
    user = Stakeholder(
        stakeholder_id="user-w",
        role=StakeholderRole.USER,
        display_name="User",
        scenario="travel",
        interest_dimensions=[
            InterestDimension(
                dimension="price",
                direction=PreferenceDirection.LOWER_IS_BETTER,
                weight=0.8,
            ),
        ],
        influence_weights={"price": 0.9},
    )
    org = Stakeholder(
        stakeholder_id="org-w",
        role=StakeholderRole.ORG,
        display_name="Org",
        scenario="travel",
        interest_dimensions=[
            InterestDimension(
                dimension="price",
                direction=PreferenceDirection.HIGHER_IS_BETTER,
                weight=0.8,
            ),
        ],
        influence_weights={"price": 0.9},
    )
    smap = _make_stakeholder_map(stakeholders=[user, org])
    plan = build_capability_plan(
        query="下周去上海出差",
        scenario="travel",
        stakeholder_map=smap,
    )
    assert "explanation" in plan
    assert "price" in plan["explanation"]
    assert "⚠" in plan["explanation"]


def test_low_severity_conflicts_no_warnings():
    """When all conflicts have severity <= 0.5, no explanation is added."""
    user = Stakeholder(
        stakeholder_id="user-low",
        role=StakeholderRole.USER,
        display_name="User",
        scenario="travel",
        interest_dimensions=[
            InterestDimension(
                dimension="price",
                direction=PreferenceDirection.LOWER_IS_BETTER,
                weight=0.8,
            ),
        ],
        influence_weights={"price": 0.3},
    )
    org = Stakeholder(
        stakeholder_id="org-low",
        role=StakeholderRole.ORG,
        display_name="Org",
        scenario="travel",
        interest_dimensions=[
            InterestDimension(
                dimension="price",
                direction=PreferenceDirection.HIGHER_IS_BETTER,
                weight=0.8,
            ),
        ],
        influence_weights={"price": 0.3},
    )
    # severity = 0.3 * 0.3 = 0.09, well below 0.5
    smap = _make_stakeholder_map(stakeholders=[user, org])
    plan = build_capability_plan(
        query="下周去上海出差",
        scenario="travel",
        stakeholder_map=smap,
    )
    assert "explanation" not in plan


def test_empty_stakeholder_map_still_injects_context():
    """An empty stakeholder map (no stakeholders) still adds context with no conflicts."""
    smap = _make_stakeholder_map(stakeholders=[])
    plan = build_capability_plan(
        query="下周去上海出差",
        scenario="travel",
        stakeholder_map=smap,
    )
    assert "stakeholder_context" in plan
    assert plan["stakeholder_context"]["conflicts"] == []
    assert plan["stakeholder_context"]["negotiation_proposals"] == []
    assert "explanation" not in plan
