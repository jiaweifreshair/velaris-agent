"""Unit tests for NegotiationStrategy.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
"""

from __future__ import annotations

from datetime import datetime, timezone

from velaris_agent.memory.conflict_engine import ConflictDetectionEngine
from velaris_agent.memory.negotiation import NegotiationStrategy
from velaris_agent.memory.types import (
    Conflict,
    InterestDimension,
    OrgPolicy,
    PreferenceDirection,
    Stakeholder,
    StakeholderMapModel,
    StakeholderRole,
)


# ---------------------------------------------------------------------------
# Helpers (same pattern as other test files)
# ---------------------------------------------------------------------------


def _make_stakeholder(
    stakeholder_id: str = "user-alice",
    role: StakeholderRole = StakeholderRole.USER,
    display_name: str = "Alice",
    scenario: str = "travel",
    interest_dimensions: list[InterestDimension] | None = None,
    influence_weights: dict[str, float] | None = None,
    related_stakeholder_ids: list[str] | None = None,
    active: bool = True,
    version: int = 1,
) -> Stakeholder:
    """Build a Stakeholder with sensible defaults for testing."""
    if interest_dimensions is None:
        interest_dimensions = [
            InterestDimension(
                dimension="cost",
                direction=PreferenceDirection.LOWER_IS_BETTER,
                weight=0.7,
            ),
            InterestDimension(
                dimension="quality",
                direction=PreferenceDirection.HIGHER_IS_BETTER,
                weight=0.5,
            ),
        ]
    if influence_weights is None:
        influence_weights = {"cost": 0.8, "quality": 0.6}
    if related_stakeholder_ids is None:
        related_stakeholder_ids = []

    return Stakeholder(
        stakeholder_id=stakeholder_id,
        role=role,
        display_name=display_name,
        scenario=scenario,
        interest_dimensions=interest_dimensions,
        influence_weights=influence_weights,
        related_stakeholder_ids=related_stakeholder_ids,
        active=active,
        version=version,
    )


def _make_map_model(
    stakeholders: list[Stakeholder],
    scenario: str = "travel",
) -> StakeholderMapModel:
    """Build a minimal StakeholderMapModel for testing."""
    return StakeholderMapModel(
        map_id="test-map",
        scenario=scenario,
        stakeholders=stakeholders,
        alignment_matrix=[],
        conflicts=[],
        timestamp=datetime.now(tz=timezone.utc),
    )


def _make_conflict(
    a_id: str = "user-alice",
    b_id: str = "org-acme",
    dimension: str = "cost",
    conflict_type: str = "direction",
    severity: float = 0.5,
) -> Conflict:
    """Build a Conflict with sensible defaults."""
    return Conflict(
        stakeholder_a_id=a_id,
        stakeholder_b_id=b_id,
        dimension=dimension,
        conflict_type=conflict_type,
        severity=severity,
        details={},
    )


# ---------------------------------------------------------------------------
# Test: Proposal generation with known conflict values (Req 5.1)
# ---------------------------------------------------------------------------


class TestProposalGeneration:
    """generate() must produce one proposal per conflicting dimension."""

    def test_empty_conflicts_returns_empty(self) -> None:
        strategy = NegotiationStrategy()
        alice = _make_stakeholder()
        map_model = _make_map_model([alice])

        proposals = strategy.generate([], map_model)
        assert proposals == []

    def test_single_conflict_produces_one_proposal(self) -> None:
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.8,
                ),
            ],
            influence_weights={"cost": 0.9},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.3,
                ),
            ],
            influence_weights={"cost": 0.7},
        )
        map_model = _make_map_model([alice, acme])
        conflict = _make_conflict(
            a_id="user-alice", b_id="org-acme", dimension="cost",
        )

        strategy = NegotiationStrategy()
        proposals = strategy.generate([conflict], map_model)

        assert len(proposals) == 1
        assert proposals[0].dimension == "cost"

    def test_two_dimensions_produce_two_proposals(self) -> None:
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.8,
                ),
                InterestDimension(
                    dimension="quality",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.6,
                ),
            ],
            influence_weights={"cost": 0.9, "quality": 0.5},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.3,
                ),
                InterestDimension(
                    dimension="quality",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.9,
                ),
            ],
            influence_weights={"cost": 0.7, "quality": 0.8},
        )
        map_model = _make_map_model([alice, acme])
        conflicts = [
            _make_conflict(dimension="cost"),
            _make_conflict(dimension="quality"),
        ]

        strategy = NegotiationStrategy()
        proposals = strategy.generate(conflicts, map_model)

        assert len(proposals) == 2
        dims = {p.dimension for p in proposals}
        assert dims == {"cost", "quality"}

    def test_multiple_conflicts_same_dimension_produce_one_proposal(self) -> None:
        """Two conflicts on the same dimension → only one proposal."""
        alice = _make_stakeholder(stakeholder_id="user-alice")
        bob = _make_stakeholder(stakeholder_id="user-bob", display_name="Bob")
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
        )
        map_model = _make_map_model([alice, bob, acme])
        conflicts = [
            _make_conflict(a_id="user-alice", b_id="org-acme", dimension="cost"),
            _make_conflict(a_id="user-bob", b_id="org-acme", dimension="cost"),
        ]

        strategy = NegotiationStrategy()
        proposals = strategy.generate(conflicts, map_model)

        assert len(proposals) == 1
        assert proposals[0].dimension == "cost"


# ---------------------------------------------------------------------------
# Test: Concession proportionality with asymmetric influence (Req 5.2)
# ---------------------------------------------------------------------------


class TestConcessionProportionality:
    """Lower influence stakeholder must concede more."""

    def test_lower_influence_concedes_more(self) -> None:
        """Alice (influence=0.3) should concede more than Acme (influence=0.9)."""
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.8,
                ),
            ],
            influence_weights={"cost": 0.3},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.2,
                ),
            ],
            influence_weights={"cost": 0.9},
        )
        map_model = _make_map_model([alice, acme])
        conflict = _make_conflict(
            a_id="user-alice", b_id="org-acme", dimension="cost",
        )

        strategy = NegotiationStrategy()
        proposals = strategy.generate([conflict], map_model)

        assert len(proposals) == 1
        p = proposals[0]
        # Alice has lower influence → concedes more
        assert p.concessions["user-alice"] > p.concessions["org-acme"]

    def test_equal_influence_equal_concession(self) -> None:
        """Equal influence → equal concessions."""
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.9,
                ),
            ],
            influence_weights={"cost": 0.5},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.3,
                ),
            ],
            influence_weights={"cost": 0.5},
        )
        map_model = _make_map_model([alice, acme])
        conflict = _make_conflict(
            a_id="user-alice", b_id="org-acme", dimension="cost",
        )

        strategy = NegotiationStrategy()
        proposals = strategy.generate([conflict], map_model)

        assert len(proposals) == 1
        p = proposals[0]
        assert abs(p.concessions["user-alice"] - p.concessions["org-acme"]) < 1e-9

    def test_highly_asymmetric_influence(self) -> None:
        """Very low influence (0.1) vs very high (1.0) → large concession gap."""
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=1.0,
                ),
            ],
            influence_weights={"cost": 0.1},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.0,
                ),
            ],
            influence_weights={"cost": 1.0},
        )
        map_model = _make_map_model([alice, acme])
        conflict = _make_conflict(
            a_id="user-alice", b_id="org-acme", dimension="cost",
        )

        strategy = NegotiationStrategy()
        proposals = strategy.generate([conflict], map_model)

        p = proposals[0]
        # Alice (influence=0.1) concedes much more than Acme (influence=1.0)
        assert p.concessions["user-alice"] > p.concessions["org-acme"]
        # The ratio should roughly be 10:1 (inverse influence)
        ratio = p.concessions["user-alice"] / max(p.concessions["org-acme"], 1e-12)
        assert ratio > 5.0  # At least 5x more concession


# ---------------------------------------------------------------------------
# Test: Hard constraint dimension produces non_negotiable=True (Req 5.5)
# ---------------------------------------------------------------------------


class TestHardConstraintNonNegotiable:
    """OrgPolicy hard constraints → non_negotiable=True, holder concession=0."""

    def test_hard_constraint_marks_non_negotiable(self) -> None:
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="compliance",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.4,
                ),
            ],
            influence_weights={"compliance": 0.5},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="compliance",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.9,
                ),
            ],
            influence_weights={"compliance": 0.8},
        )
        map_model = _make_map_model([alice, acme])
        conflict = _make_conflict(
            a_id="user-alice",
            b_id="org-acme",
            dimension="compliance",
            conflict_type="weight",
        )
        org_policy = OrgPolicy(
            org_id="org-acme",
            scenario="travel",
            constraints={"compliance": True},
        )

        strategy = NegotiationStrategy()
        proposals = strategy.generate([conflict], map_model, org_policy=org_policy)

        assert len(proposals) == 1
        p = proposals[0]
        assert p.non_negotiable is True

    def test_hard_constraint_holder_concession_zero(self) -> None:
        """The org stakeholder (constraint holder) should have concession = 0."""
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="compliance",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.4,
                ),
            ],
            influence_weights={"compliance": 0.5},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="compliance",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.9,
                ),
            ],
            influence_weights={"compliance": 0.8},
        )
        map_model = _make_map_model([alice, acme])
        conflict = _make_conflict(
            a_id="user-alice",
            b_id="org-acme",
            dimension="compliance",
            conflict_type="weight",
        )
        org_policy = OrgPolicy(
            org_id="org-acme",
            scenario="travel",
            constraints={"compliance": True},
        )

        strategy = NegotiationStrategy()
        proposals = strategy.generate([conflict], map_model, org_policy=org_policy)

        p = proposals[0]
        assert p.concessions["org-acme"] == 0.0
        # Non-holder should concede the full gap
        assert p.concessions["user-alice"] > 0.0

    def test_non_constraint_dimension_is_negotiable(self) -> None:
        """A dimension NOT in OrgPolicy.constraints → non_negotiable=False."""
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.8,
                ),
            ],
            influence_weights={"cost": 0.6},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.3,
                ),
            ],
            influence_weights={"cost": 0.7},
        )
        map_model = _make_map_model([alice, acme])
        conflict = _make_conflict(dimension="cost")
        # OrgPolicy constrains "compliance" but NOT "cost"
        org_policy = OrgPolicy(
            org_id="org-acme",
            scenario="travel",
            constraints={"compliance": True},
        )

        strategy = NegotiationStrategy()
        proposals = strategy.generate([conflict], map_model, org_policy=org_policy)

        assert len(proposals) == 1
        assert proposals[0].non_negotiable is False

    def test_no_org_policy_means_all_negotiable(self) -> None:
        """Without OrgPolicy, all proposals should be negotiable."""
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.8,
                ),
            ],
            influence_weights={"cost": 0.6},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.3,
                ),
            ],
            influence_weights={"cost": 0.7},
        )
        map_model = _make_map_model([alice, acme])
        conflict = _make_conflict(dimension="cost")

        strategy = NegotiationStrategy()
        proposals = strategy.generate([conflict], map_model, org_policy=None)

        assert len(proposals) == 1
        assert proposals[0].non_negotiable is False


# ---------------------------------------------------------------------------
# Test: Feasibility score range (Req 5.4)
# ---------------------------------------------------------------------------


class TestFeasibilityScore:
    """Feasibility must be in [0.0, 1.0]."""

    def test_feasibility_in_range(self) -> None:
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.9,
                ),
            ],
            influence_weights={"cost": 0.8},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.1,
                ),
            ],
            influence_weights={"cost": 0.6},
        )
        map_model = _make_map_model([alice, acme])
        conflict = _make_conflict(dimension="cost")

        strategy = NegotiationStrategy()
        proposals = strategy.generate([conflict], map_model)

        assert len(proposals) == 1
        assert 0.0 <= proposals[0].feasibility <= 1.0

    def test_feasibility_with_hard_constraint(self) -> None:
        """Hard constraint proposals should also have feasibility in [0, 1]."""
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="compliance",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.3,
                ),
            ],
            influence_weights={"compliance": 0.4},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="compliance",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=1.0,
                ),
            ],
            influence_weights={"compliance": 0.9},
        )
        map_model = _make_map_model([alice, acme])
        conflict = _make_conflict(dimension="compliance", conflict_type="weight")
        org_policy = OrgPolicy(
            org_id="org-acme",
            scenario="travel",
            constraints={"compliance": True},
        )

        strategy = NegotiationStrategy()
        proposals = strategy.generate([conflict], map_model, org_policy=org_policy)

        assert 0.0 <= proposals[0].feasibility <= 1.0

    def test_compromise_weight_between_min_max(self) -> None:
        """Compromise weight must be between min and max of conflicting weights (Req 5.3)."""
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.9,
                ),
            ],
            influence_weights={"cost": 0.7},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.2,
                ),
            ],
            influence_weights={"cost": 0.4},
        )
        map_model = _make_map_model([alice, acme])
        conflict = _make_conflict(dimension="cost")

        strategy = NegotiationStrategy()
        proposals = strategy.generate([conflict], map_model)

        p = proposals[0]
        assert p.compromise_weight >= 0.2  # min weight
        assert p.compromise_weight <= 0.9  # max weight

    def test_zero_gap_produces_high_feasibility(self) -> None:
        """When both stakeholders have the same weight, feasibility should be 1.0."""
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.5,
                ),
            ],
            influence_weights={"cost": 0.6},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.5,
                ),
            ],
            influence_weights={"cost": 0.7},
        )
        map_model = _make_map_model([alice, acme])
        conflict = _make_conflict(dimension="cost")

        strategy = NegotiationStrategy()
        proposals = strategy.generate([conflict], map_model)

        # Same weight → zero gap → zero concession → feasibility = 1.0
        assert proposals[0].feasibility == 1.0


# ---------------------------------------------------------------------------
# Test: Integration with ConflictDetectionEngine (Req 5.1)
# ---------------------------------------------------------------------------


class TestNegotiationWithConflictEngine:
    """End-to-end: detect conflicts then generate proposals."""

    def test_detected_conflicts_produce_proposals(self) -> None:
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.8,
                ),
            ],
            influence_weights={"cost": 0.9},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.3,
                ),
            ],
            influence_weights={"cost": 0.7},
        )
        map_model = _make_map_model([alice, acme])

        engine = ConflictDetectionEngine()
        conflicts = engine.detect(map_model)
        assert len(conflicts) >= 1

        strategy = NegotiationStrategy()
        proposals = strategy.generate(conflicts, map_model)

        assert len(proposals) >= 1
        for p in proposals:
            assert 0.0 <= p.feasibility <= 1.0
            assert p.compromise_weight >= 0.3
            assert p.compromise_weight <= 0.8
