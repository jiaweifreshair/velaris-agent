"""Unit tests for StakeholderMapBuilder.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 9.4
"""

from __future__ import annotations

from velaris_agent.memory.stakeholder import StakeholderRegistry
from velaris_agent.memory.stakeholder_map import StakeholderMapBuilder
from velaris_agent.memory.types import (
    InterestDimension,
    PreferenceDirection,
    Stakeholder,
    StakeholderRole,
)


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_stakeholder.py)
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


def _registry_with(*stakeholders: Stakeholder) -> StakeholderRegistry:
    """Create a registry pre-loaded with the given stakeholders."""
    registry = StakeholderRegistry()
    for s in stakeholders:
        registry.register(s)
    return registry


# ---------------------------------------------------------------------------
# Test: build with 0, 1, and 2+ stakeholders (Req 3.1, 3.2, 3.4)
# ---------------------------------------------------------------------------


class TestBuildStakeholderCounts:
    """build() must handle 0, 1, and 2+ stakeholders correctly."""

    def test_build_zero_stakeholders(self) -> None:
        """Empty scenario → valid map with empty alignment matrix."""
        registry = StakeholderRegistry()
        builder = StakeholderMapBuilder(registry)
        result = builder.build("empty-scenario")

        assert result.scenario == "empty-scenario"
        assert result.stakeholders == []
        assert result.alignment_matrix == []
        assert result.conflicts == []
        assert result.timestamp is not None
        assert result.map_id != ""

    def test_build_one_stakeholder(self) -> None:
        """Single stakeholder → valid map with empty alignment matrix."""
        alice = _make_stakeholder()
        registry = _registry_with(alice)
        builder = StakeholderMapBuilder(registry)
        result = builder.build("travel")

        assert len(result.stakeholders) == 1
        assert result.stakeholders[0].stakeholder_id == "user-alice"
        assert result.alignment_matrix == []
        assert result.conflicts == []

    def test_build_two_stakeholders(self) -> None:
        """Two stakeholders → exactly 1 pairwise alignment entry."""
        alice = _make_stakeholder(stakeholder_id="user-alice")
        bob = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
        )
        registry = _registry_with(alice, bob)
        builder = StakeholderMapBuilder(registry)
        result = builder.build("travel")

        assert len(result.stakeholders) == 2
        assert len(result.alignment_matrix) == 1

    def test_build_three_stakeholders(self) -> None:
        """Three stakeholders → exactly 3 pairwise alignment entries (3C2)."""
        alice = _make_stakeholder(stakeholder_id="user-alice")
        bob = _make_stakeholder(
            stakeholder_id="user-bob",
            display_name="Bob",
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
        )
        registry = _registry_with(alice, bob, acme)
        builder = StakeholderMapBuilder(registry)
        result = builder.build("travel")

        assert len(result.stakeholders) == 3
        assert len(result.alignment_matrix) == 3

    def test_build_includes_only_active_stakeholders(self) -> None:
        """Inactive stakeholders should not appear in the map."""
        alice = _make_stakeholder(stakeholder_id="user-alice")
        bob = _make_stakeholder(
            stakeholder_id="user-bob",
            display_name="Bob",
        )
        registry = _registry_with(alice, bob)
        # Soft-delete bob
        registry.remove("user-bob", "travel")

        builder = StakeholderMapBuilder(registry)
        result = builder.build("travel")

        assert len(result.stakeholders) == 1
        assert result.stakeholders[0].stakeholder_id == "user-alice"
        assert result.alignment_matrix == []


# ---------------------------------------------------------------------------
# Test: Pairwise alignment with identical stakeholders (Req 3.2, 3.3)
# ---------------------------------------------------------------------------


class TestPairwiseAlignmentIdentical:
    """Identical interest dimensions → score near 1.0, classified as aligned."""

    def test_identical_stakeholders_score_near_one(self) -> None:
        a = _make_stakeholder(stakeholder_id="a")
        b = _make_stakeholder(stakeholder_id="b", display_name="B")

        builder = StakeholderMapBuilder(StakeholderRegistry())
        pa = builder.compute_pairwise_alignment(a, b)

        # Same directions, same weights → direction_match=1.0, weight_similarity=1.0
        # dim_score = 1.0*0.6 + 1.0*0.4 = 1.0 for each dim
        assert pa.score >= 0.95
        assert pa.score <= 1.0
        assert pa.classification == "aligned"

    def test_identical_stakeholders_ids_correct(self) -> None:
        a = _make_stakeholder(stakeholder_id="a")
        b = _make_stakeholder(stakeholder_id="b", display_name="B")

        builder = StakeholderMapBuilder(StakeholderRegistry())
        pa = builder.compute_pairwise_alignment(a, b)

        assert pa.stakeholder_a_id == "a"
        assert pa.stakeholder_b_id == "b"


# ---------------------------------------------------------------------------
# Test: Pairwise alignment with opposing directions (Req 3.2, 3.3)
# ---------------------------------------------------------------------------


class TestPairwiseAlignmentOpposing:
    """Opposing preference directions → low score, classified as conflicting."""

    def test_opposing_directions_score_near_zero(self) -> None:
        a = _make_stakeholder(
            stakeholder_id="a",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.8,
                ),
            ],
            influence_weights={"cost": 1.0},
        )
        b = _make_stakeholder(
            stakeholder_id="b",
            display_name="B",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.8,
                ),
            ],
            influence_weights={"cost": 1.0},
        )

        builder = StakeholderMapBuilder(StakeholderRegistry())
        pa = builder.compute_pairwise_alignment(a, b)

        # direction_match=0.0, weight_similarity=1.0 (same weight)
        # dim_score = 0.0*0.6 + 1.0*0.4 = 0.4
        # score = 0.4 → neutral (0.3 <= 0.4 < 0.7)
        assert pa.score < 0.5
        assert pa.classification == "neutral"

    def test_opposing_directions_different_weights_low_score(self) -> None:
        """Opposing directions + different weights → even lower score."""
        a = _make_stakeholder(
            stakeholder_id="a",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=1.0,
                ),
            ],
            influence_weights={"cost": 1.0},
        )
        b = _make_stakeholder(
            stakeholder_id="b",
            display_name="B",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.0,
                ),
            ],
            influence_weights={"cost": 1.0},
        )

        builder = StakeholderMapBuilder(StakeholderRegistry())
        pa = builder.compute_pairwise_alignment(a, b)

        # direction_match=0.0, weight_similarity=1.0-1.0=0.0
        # dim_score = 0.0*0.6 + 0.0*0.4 = 0.0
        # score = 0.0 → conflicting
        assert pa.score < 0.3
        assert pa.classification == "conflicting"


# ---------------------------------------------------------------------------
# Test: No shared dimensions → neutral score 0.5 (Req 3.2)
# ---------------------------------------------------------------------------


class TestPairwiseAlignmentNoSharedDims:
    """No shared dimensions → score = 0.5, classified as neutral."""

    def test_no_shared_dims_returns_neutral(self) -> None:
        a = _make_stakeholder(
            stakeholder_id="a",
            interest_dimensions=[
                InterestDimension(
                    dimension="cost",
                    direction=PreferenceDirection.LOWER_IS_BETTER,
                    weight=0.7,
                ),
            ],
            influence_weights={"cost": 0.8},
        )
        b = _make_stakeholder(
            stakeholder_id="b",
            display_name="B",
            interest_dimensions=[
                InterestDimension(
                    dimension="growth",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.6,
                ),
            ],
            influence_weights={"growth": 0.5},
        )

        builder = StakeholderMapBuilder(StakeholderRegistry())
        pa = builder.compute_pairwise_alignment(a, b)

        assert pa.score == 0.5
        assert pa.classification == "neutral"


# ---------------------------------------------------------------------------
# Test: Classification thresholds at boundaries (Req 3.3)
# ---------------------------------------------------------------------------


class TestClassificationThresholds:
    """Verify classification boundaries: 0.3 and 0.7."""

    def _build_pair_with_score(self, target_score: float) -> str:
        """Build a pair that produces a known score and return classification.

        We use the no-shared-dims edge case (score=0.5) and the
        compute_pairwise_alignment method directly to test classification
        logic via the _classify_score function indirectly.
        """
        from velaris_agent.memory.stakeholder_map import _classify_score

        return _classify_score(target_score)

    def test_score_exactly_0_7_is_aligned(self) -> None:
        assert self._build_pair_with_score(0.7) == "aligned"

    def test_score_just_below_0_7_is_neutral(self) -> None:
        assert self._build_pair_with_score(0.6999) == "neutral"

    def test_score_exactly_0_3_is_neutral(self) -> None:
        assert self._build_pair_with_score(0.3) == "neutral"

    def test_score_just_below_0_3_is_conflicting(self) -> None:
        assert self._build_pair_with_score(0.2999) == "conflicting"

    def test_score_1_0_is_aligned(self) -> None:
        assert self._build_pair_with_score(1.0) == "aligned"

    def test_score_0_0_is_conflicting(self) -> None:
        assert self._build_pair_with_score(0.0) == "conflicting"

    def test_score_0_5_is_neutral(self) -> None:
        assert self._build_pair_with_score(0.5) == "neutral"


# ---------------------------------------------------------------------------
# Test: Map traceability fields (Req 3.5)
# ---------------------------------------------------------------------------


class TestMapTraceability:
    """Built map must have non-null timestamp and matching scenario."""

    def test_timestamp_is_set(self) -> None:
        registry = StakeholderRegistry()
        builder = StakeholderMapBuilder(registry)
        result = builder.build("travel")

        assert result.timestamp is not None

    def test_scenario_matches(self) -> None:
        registry = StakeholderRegistry()
        builder = StakeholderMapBuilder(registry)
        result = builder.build("travel")

        assert result.scenario == "travel"

    def test_map_id_is_nonempty(self) -> None:
        registry = StakeholderRegistry()
        builder = StakeholderMapBuilder(registry)
        result = builder.build("travel")

        assert result.map_id != ""


# ---------------------------------------------------------------------------
# Test: export_as_alignment_report produces valid AlignmentReport (Req 9.4)
# ---------------------------------------------------------------------------


class TestExportAsAlignmentReport:
    """export_as_alignment_report must produce a valid AlignmentReport."""

    def test_basic_export(self) -> None:
        alice = _make_stakeholder(stakeholder_id="user-alice")
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
        )
        registry = _registry_with(alice, acme)
        builder = StakeholderMapBuilder(registry)
        map_model = builder.build("travel")

        report = builder.export_as_alignment_report(
            map_model, user_id="user-alice", org_id="org-acme",
        )

        assert report.user_id == "user-alice"
        assert report.org_id == "org-acme"
        assert report.scenario == "travel"
        assert 0.0 <= report.alignment_score <= 1.0
        assert isinstance(report.conflicts, list)
        assert isinstance(report.synergies, list)
        assert isinstance(report.negotiation_space, dict)
        assert report.created_at is not None

    def test_export_alignment_score_matches_pairwise(self) -> None:
        """The report's alignment_score should match the pairwise score."""
        alice = _make_stakeholder(stakeholder_id="user-alice")
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
        )
        registry = _registry_with(alice, acme)
        builder = StakeholderMapBuilder(registry)
        map_model = builder.build("travel")

        report = builder.export_as_alignment_report(
            map_model, user_id="user-alice", org_id="org-acme",
        )

        # The pairwise score between identical-dimension stakeholders
        assert len(map_model.alignment_matrix) == 1
        expected_score = map_model.alignment_matrix[0].score
        assert report.alignment_score == expected_score

    def test_export_with_conflicts(self) -> None:
        """Opposing directions should appear as conflicts in the report."""
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
        registry = _registry_with(alice, acme)
        builder = StakeholderMapBuilder(registry)
        map_model = builder.build("travel")

        report = builder.export_as_alignment_report(
            map_model, user_id="user-alice", org_id="org-acme",
        )

        assert len(report.conflicts) == 1
        assert report.conflicts[0]["dimension"] == "cost"

    def test_export_with_synergies(self) -> None:
        """Same direction + close weights should appear as synergies."""
        alice = _make_stakeholder(
            stakeholder_id="user-alice",
            interest_dimensions=[
                InterestDimension(
                    dimension="quality",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.7,
                ),
            ],
            influence_weights={"quality": 0.8},
        )
        acme = _make_stakeholder(
            stakeholder_id="org-acme",
            role=StakeholderRole.ORG,
            display_name="Acme",
            interest_dimensions=[
                InterestDimension(
                    dimension="quality",
                    direction=PreferenceDirection.HIGHER_IS_BETTER,
                    weight=0.6,
                ),
            ],
            influence_weights={"quality": 0.7},
        )
        registry = _registry_with(alice, acme)
        builder = StakeholderMapBuilder(registry)
        map_model = builder.build("travel")

        report = builder.export_as_alignment_report(
            map_model, user_id="user-alice", org_id="org-acme",
        )

        assert "quality" in report.synergies

    def test_export_nonexistent_pair_returns_neutral(self) -> None:
        """If user/org pair not in matrix, default alignment_score = 0.5."""
        alice = _make_stakeholder(stakeholder_id="user-alice")
        registry = _registry_with(alice)
        builder = StakeholderMapBuilder(registry)
        map_model = builder.build("travel")

        report = builder.export_as_alignment_report(
            map_model, user_id="user-alice", org_id="org-missing",
        )

        assert report.alignment_score == 0.5
        assert report.conflicts == []
        assert report.synergies == []
