"""Property-based tests for stakeholder mapping using Hypothesis.

Shared Hypothesis strategies and property tests for the stakeholder-mapping feature.
All property tests for this feature live in this file.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp

from pydantic import ValidationError
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from velaris_agent.biz.engine import build_capability_plan, get_scenario_registry
from velaris_agent.memory.conflict_engine import ConflictDetectionEngine
from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.memory.negotiation import NegotiationStrategy
from velaris_agent.memory.preference_learner import PreferenceLearner
from velaris_agent.memory.stakeholder import DecisionCurveTracker, StakeholderRegistry
from velaris_agent.memory.stakeholder_map import StakeholderMapBuilder
from velaris_agent.memory.types import (
    AlignmentReport,
    Conflict,
    DecisionActor,
    DecisionCurvePoint,
    DecisionRecord,
    InterestDimension,
    OrgPolicy,
    PairwiseAlignment,
    PreferenceDirection,
    Stakeholder,
    StakeholderMapModel,
    StakeholderRole,
    UserPreferences,
)


# ---------------------------------------------------------------------------
# Shared Hypothesis Strategies
# ---------------------------------------------------------------------------

# Dimension names used across strategies — kept finite to encourage shared dims
_DIMENSION_NAMES = [
    "cost",
    "growth",
    "compliance",
    "quality",
    "speed",
    "risk",
    "innovation",
    "retention",
]


def st_preference_direction() -> st.SearchStrategy[PreferenceDirection]:
    """Generate a PreferenceDirection enum value."""
    return st.sampled_from(list(PreferenceDirection))


def st_stakeholder_role() -> st.SearchStrategy[StakeholderRole]:
    """Generate a StakeholderRole enum value (user or org only)."""
    return st.sampled_from([StakeholderRole.USER, StakeholderRole.ORG])


@st.composite
def st_interest_dimension(draw: st.DrawFn) -> InterestDimension:
    """Generate a valid InterestDimension object."""
    dimension = draw(st.sampled_from(_DIMENSION_NAMES))
    direction = draw(st_preference_direction())
    weight = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    return InterestDimension(dimension=dimension, direction=direction, weight=weight)


@st.composite
def st_influence_weights(
    draw: st.DrawFn,
    dimensions: list[InterestDimension],
) -> dict[str, float]:
    """Generate valid influence weight dict for the given dimensions."""
    weights: dict[str, float] = {}
    for dim in dimensions:
        weights[dim.dimension] = draw(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        )
    return weights


@st.composite
def st_stakeholder(draw: st.DrawFn) -> Stakeholder:
    """Generate a valid non-relationship Stakeholder."""
    stakeholder_id = draw(
        st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True),
    )
    role = draw(st_stakeholder_role())
    display_name = draw(
        st.from_regex(r"[A-Za-z][A-Za-z0-9 ]{1,20}", fullmatch=True),
    )
    scenario = draw(st.sampled_from(["travel", "career", "finance", "health"]))

    # At least one interest dimension, up to 4
    dims = draw(
        st.lists(st_interest_dimension(), min_size=1, max_size=4).filter(
            # Ensure unique dimension names
            lambda ds: len({d.dimension for d in ds}) == len(ds),
        ),
    )
    influence = draw(st_influence_weights(dims))

    ts = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 1, 1),
            timezones=st.just(timezone.utc),
        ),
    )

    return Stakeholder(
        stakeholder_id=stakeholder_id,
        role=role,
        display_name=display_name,
        scenario=scenario,
        interest_dimensions=dims,
        influence_weights=influence,
        related_stakeholder_ids=[],
        active=True,
        version=draw(st.integers(min_value=1, max_value=100)),
        created_at=ts,
        updated_at=ts,
    )


@st.composite
def st_pairwise_alignment(draw: st.DrawFn) -> PairwiseAlignment:
    """Generate a valid PairwiseAlignment."""
    score = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    if score >= 0.7:
        classification = "aligned"
    elif score >= 0.3:
        classification = "neutral"
    else:
        classification = "conflicting"
    return PairwiseAlignment(
        stakeholder_a_id=draw(
            st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True),
        ),
        stakeholder_b_id=draw(
            st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True),
        ),
        score=score,
        classification=classification,
    )


@st.composite
def st_conflict(draw: st.DrawFn) -> Conflict:
    """Generate a valid Conflict."""
    return Conflict(
        stakeholder_a_id=draw(
            st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True),
        ),
        stakeholder_b_id=draw(
            st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True),
        ),
        dimension=draw(st.sampled_from(_DIMENSION_NAMES)),
        conflict_type=draw(st.sampled_from(["direction", "weight"])),
        severity=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
        details={},
    )


@st.composite
def st_stakeholder_map_model(draw: st.DrawFn) -> StakeholderMapModel:
    """Generate a valid StakeholderMapModel with consistent data."""
    scenario = draw(st.sampled_from(["travel", "career", "finance", "health"]))

    # Generate 0-4 stakeholders, all sharing the same scenario
    stakeholders = draw(
        st.lists(st_stakeholder(), min_size=0, max_size=4).filter(
            # Ensure unique stakeholder_ids
            lambda ss: len({s.stakeholder_id for s in ss}) == len(ss),
        ),
    )
    # Override scenario to be consistent
    stakeholders = [s.model_copy(update={"scenario": scenario}) for s in stakeholders]

    # Generate alignment matrix entries (can be empty)
    alignment_matrix = draw(
        st.lists(st_pairwise_alignment(), min_size=0, max_size=6),
    )

    # Generate conflicts (can be empty)
    conflicts = draw(st.lists(st_conflict(), min_size=0, max_size=4))

    ts = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 1, 1),
            timezones=st.just(timezone.utc),
        ),
    )

    map_id = draw(st.from_regex(r"map-[a-z0-9]{4,8}", fullmatch=True))

    return StakeholderMapModel(
        map_id=map_id,
        scenario=scenario,
        stakeholders=stakeholders,
        alignment_matrix=alignment_matrix,
        conflicts=conflicts,
        timestamp=ts,
    )


# ---------------------------------------------------------------------------
# Property 28: Serialization round-trip
# Feature: stakeholder-mapping, Property 28: Serialization round-trip
# ---------------------------------------------------------------------------


class TestProperty28SerializationRoundTrip:
    """**Validates: Requirements 8.1, 8.2, 8.3**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(model=st_stakeholder_map_model())
    def test_serialization_round_trip(self, model: StakeholderMapModel) -> None:
        """For any valid StakeholderMapModel, serializing to JSON and
        deserializing back produces identical JSON output.

        Property: model_validate_json(model.model_dump_json()).model_dump_json()
                  == model.model_dump_json()
        """
        # Feature: stakeholder-mapping, Property 28: Serialization round-trip
        first_json = model.model_dump_json()
        restored = StakeholderMapModel.model_validate_json(first_json)
        second_json = restored.model_dump_json()
        assert first_json == second_json, (
            f"Round-trip JSON mismatch.\n"
            f"First:  {first_json[:200]}...\n"
            f"Second: {second_json[:200]}..."
        )

# ---------------------------------------------------------------------------
# Property 1: Stakeholder structural completeness
# Feature: stakeholder-mapping, Property 1: Stakeholder structural completeness
# ---------------------------------------------------------------------------


class TestProperty1StakeholderStructuralCompleteness:
    """**Validates: Requirements 1.1**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(stakeholder=st_stakeholder())
    def test_registered_stakeholder_has_all_required_fields(
        self, stakeholder: Stakeholder
    ) -> None:
        """For any valid Stakeholder created via the registry, the object shall
        contain a non-empty stakeholder_id, a role in {user, org, relationship},
        a non-empty display_name, a non-empty scenario, at least one
        InterestDimension, and a non-empty influence_weights dict.
        """
        # Feature: stakeholder-mapping, Property 1: Stakeholder structural completeness
        registry = StakeholderRegistry()
        sid = registry.register(stakeholder)
        retrieved = registry.get(sid, stakeholder.scenario)
        assert retrieved is not None

        assert retrieved.stakeholder_id != ""
        assert retrieved.role in (
            StakeholderRole.USER,
            StakeholderRole.ORG,
            StakeholderRole.RELATIONSHIP,
        )
        assert retrieved.display_name != ""
        assert retrieved.scenario != ""
        assert len(retrieved.interest_dimensions) >= 1
        assert len(retrieved.influence_weights) > 0


# ---------------------------------------------------------------------------
# Property 2: Relationship stakeholder requires exactly two references
# Feature: stakeholder-mapping, Property 2: Relationship stakeholder requires exactly two references
# ---------------------------------------------------------------------------


class TestProperty2RelationshipRequiresTwoRefs:
    """**Validates: Requirements 1.2**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(stakeholder=st_stakeholder(), data=st.data())
    def test_relationship_requires_two_refs(
        self, stakeholder: Stakeholder, data: st.DataObject
    ) -> None:
        """For any Stakeholder with role == 'relationship', the
        related_stakeholder_ids list must have exactly 2 elements.
        For any Stakeholder with role != 'relationship', the registry must
        accept it regardless of related_stakeholder_ids length.
        """
        # Feature: stakeholder-mapping, Property 2: Relationship stakeholder requires exactly two references
        registry = StakeholderRegistry()

        # Non-relationship stakeholders should be accepted
        assert stakeholder.role != StakeholderRole.RELATIONSHIP
        registry.register(stakeholder)

        # Now test relationship role: wrong ref count should fail
        bad_ref_count = data.draw(
            st.sampled_from([0, 1, 3, 4]),
        )
        rel_stakeholder = stakeholder.model_copy(
            update={
                "stakeholder_id": stakeholder.stakeholder_id + "-rel",
                "role": StakeholderRole.RELATIONSHIP,
                "related_stakeholder_ids": [
                    f"ref-{i}" for i in range(bad_ref_count)
                ],
            },
        )
        try:
            registry.register(rel_stakeholder)
            raise AssertionError(
                f"Expected ValueError for relationship with "
                f"{bad_ref_count} refs, but registration succeeded."
            )
        except ValueError:
            pass  # Expected


# ---------------------------------------------------------------------------
# Property 3: Stakeholder field validation invariants
# Feature: stakeholder-mapping, Property 3: Stakeholder field validation invariants
# ---------------------------------------------------------------------------


class TestProperty3FieldValidationInvariants:
    """**Validates: Requirements 1.3, 1.4**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(stakeholder=st_stakeholder())
    def test_field_validation_invariants(self, stakeholder: Stakeholder) -> None:
        """For any Stakeholder accepted by the registry:
        (a) every InterestDimension has a non-empty dimension name, a direction
            in {higher_is_better, lower_is_better}, and a weight in [0.0, 1.0];
        (b) every value in influence_weights is in [0.0, 1.0].
        """
        # Feature: stakeholder-mapping, Property 3: Stakeholder field validation invariants
        registry = StakeholderRegistry()
        sid = registry.register(stakeholder)
        retrieved = registry.get(sid, stakeholder.scenario)
        assert retrieved is not None

        for dim in retrieved.interest_dimensions:
            assert dim.dimension != ""
            assert dim.direction in (
                PreferenceDirection.HIGHER_IS_BETTER,
                PreferenceDirection.LOWER_IS_BETTER,
            )
            assert 0.0 <= dim.weight <= 1.0

        for dim_name, weight in retrieved.influence_weights.items():
            assert 0.0 <= weight <= 1.0


# ---------------------------------------------------------------------------
# Property 4: Duplicate stakeholder rejection
# Feature: stakeholder-mapping, Property 4: Duplicate stakeholder rejection
# ---------------------------------------------------------------------------


class TestProperty4DuplicateStakeholderRejection:
    """**Validates: Requirements 1.5**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(stakeholder=st_stakeholder())
    def test_duplicate_stakeholder_rejected(self, stakeholder: Stakeholder) -> None:
        """For any registered Stakeholder, attempting to register another
        Stakeholder with the same stakeholder_id and scenario shall raise
        a validation error.
        """
        # Feature: stakeholder-mapping, Property 4: Duplicate stakeholder rejection
        registry = StakeholderRegistry()
        registry.register(stakeholder)

        duplicate = stakeholder.model_copy(
            update={"display_name": stakeholder.display_name + " dup"},
        )
        try:
            registry.register(duplicate)
            raise AssertionError(
                "Expected ValueError for duplicate stakeholder, "
                "but registration succeeded."
            )
        except ValueError:
            pass  # Expected


# ---------------------------------------------------------------------------
# Property 5: Register then retrieve round-trip
# Feature: stakeholder-mapping, Property 5: Register then retrieve round-trip
# ---------------------------------------------------------------------------


class TestProperty5RegisterRetrieveRoundTrip:
    """**Validates: Requirements 2.1**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(stakeholder=st_stakeholder())
    def test_register_then_retrieve(self, stakeholder: Stakeholder) -> None:
        """For any valid Stakeholder, after registry.register(s) returns an id,
        registry.get(id, scenario) shall return a Stakeholder equal to the
        original (modulo timestamps set by the registry).
        """
        # Feature: stakeholder-mapping, Property 5: Register then retrieve round-trip
        registry = StakeholderRegistry()
        sid = registry.register(stakeholder)
        retrieved = registry.get(sid, stakeholder.scenario)
        assert retrieved is not None
        assert retrieved.stakeholder_id == stakeholder.stakeholder_id
        assert retrieved.role == stakeholder.role
        assert retrieved.display_name == stakeholder.display_name
        assert retrieved.scenario == stakeholder.scenario
        assert retrieved.interest_dimensions == stakeholder.interest_dimensions
        assert retrieved.influence_weights == stakeholder.influence_weights
        assert retrieved.active == stakeholder.active
        assert retrieved.version == stakeholder.version


# ---------------------------------------------------------------------------
# Property 6: Update increments version and merges fields
# Feature: stakeholder-mapping, Property 6: Update increments version and merges fields
# ---------------------------------------------------------------------------


class TestProperty6UpdateIncrementsVersionAndMerges:
    """**Validates: Requirements 2.2**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(stakeholder=st_stakeholder(), new_display_name=st.from_regex(r"[A-Za-z][A-Za-z0-9 ]{1,20}", fullmatch=True))
    def test_update_increments_version_and_merges(
        self, stakeholder: Stakeholder, new_display_name: str
    ) -> None:
        """For any registered Stakeholder and any valid field update, calling
        registry.update() shall produce a Stakeholder whose version equals
        the previous version + 1, whose updated field matches the new value,
        and whose non-updated fields remain unchanged.
        """
        # Feature: stakeholder-mapping, Property 6: Update increments version and merges fields
        registry = StakeholderRegistry()
        registry.register(stakeholder)

        old_version = stakeholder.version
        updated = registry.update(
            stakeholder.stakeholder_id,
            stakeholder.scenario,
            display_name=new_display_name,
        )

        assert updated.version == old_version + 1
        assert updated.display_name == new_display_name
        # Non-updated fields remain unchanged
        assert updated.stakeholder_id == stakeholder.stakeholder_id
        assert updated.role == stakeholder.role
        assert updated.scenario == stakeholder.scenario
        assert updated.interest_dimensions == stakeholder.interest_dimensions
        assert updated.influence_weights == stakeholder.influence_weights


# ---------------------------------------------------------------------------
# Property 7: Soft-delete preserves record
# Feature: stakeholder-mapping, Property 7: Soft-delete preserves record
# ---------------------------------------------------------------------------


class TestProperty7SoftDeletePreservesRecord:
    """**Validates: Requirements 2.3**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(stakeholder=st_stakeholder())
    def test_soft_delete_preserves_record(self, stakeholder: Stakeholder) -> None:
        """For any registered Stakeholder (not referenced by an active map),
        calling registry.remove() shall set active=False but the record shall
        still be retrievable via registry.get().
        """
        # Feature: stakeholder-mapping, Property 7: Soft-delete preserves record
        registry = StakeholderRegistry()
        registry.register(stakeholder)

        registry.remove(stakeholder.stakeholder_id, stakeholder.scenario)

        retrieved = registry.get(stakeholder.stakeholder_id, stakeholder.scenario)
        assert retrieved is not None
        assert retrieved.active is False
        assert retrieved.stakeholder_id == stakeholder.stakeholder_id


# ---------------------------------------------------------------------------
# Property 8: List filtering correctness
# Feature: stakeholder-mapping, Property 8: List filtering correctness
# ---------------------------------------------------------------------------


@st.composite
def st_stakeholder_batch(draw: st.DrawFn) -> list[Stakeholder]:
    """Generate a batch of 2-6 stakeholders with unique id+scenario pairs."""
    count = draw(st.integers(min_value=2, max_value=6))
    stakeholders: list[Stakeholder] = []
    seen_keys: set[tuple[str, str]] = set()
    for _ in range(count):
        s = draw(st_stakeholder())
        key = (s.stakeholder_id, s.scenario)
        # Ensure unique keys
        attempt = 0
        while key in seen_keys and attempt < 10:
            s = draw(st_stakeholder())
            key = (s.stakeholder_id, s.scenario)
            attempt += 1
        if key not in seen_keys:
            seen_keys.add(key)
            # Randomly set active to True or False
            active = draw(st.booleans())
            stakeholders.append(s.model_copy(update={"active": active}))
    return stakeholders


class TestProperty8ListFilteringCorrectness:
    """**Validates: Requirements 2.4**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(batch=st_stakeholder_batch())
    def test_list_filtering_correctness(self, batch: list[Stakeholder]) -> None:
        """For any set of registered Stakeholders with mixed scenarios, roles,
        and active states, registry.list_active(scenario, role) shall return
        exactly those Stakeholders matching the given scenario and role
        (if specified) where active == True.
        """
        # Feature: stakeholder-mapping, Property 8: List filtering correctness
        registry = StakeholderRegistry()
        for s in batch:
            # Force active=True for registration (registry validates),
            # then update to desired active state if needed
            active_desired = s.active
            to_register = s.model_copy(update={"active": True})
            registry.register(to_register)
            if not active_desired:
                registry.remove(s.stakeholder_id, s.scenario)

        # Pick a scenario from the batch to query
        for scenario in {s.scenario for s in batch}:
            # Test without role filter
            result = registry.list_active(scenario)
            expected = [
                s for s in batch if s.scenario == scenario and s.active
            ]
            assert len(result) == len(expected), (
                f"Expected {len(expected)} active stakeholders for "
                f"scenario '{scenario}', got {len(result)}"
            )
            result_ids = {r.stakeholder_id for r in result}
            expected_ids = {s.stakeholder_id for s in expected}
            assert result_ids == expected_ids

            # Test with role filter
            for role in [StakeholderRole.USER, StakeholderRole.ORG]:
                result_role = registry.list_active(scenario, role=role)
                expected_role = [
                    s
                    for s in batch
                    if s.scenario == scenario and s.active and s.role == role
                ]
                assert len(result_role) == len(expected_role)


# ---------------------------------------------------------------------------
# Property 9: Referential integrity on remove
# Feature: stakeholder-mapping, Property 9: Referential integrity on remove
# ---------------------------------------------------------------------------


class TestProperty9ReferentialIntegrityOnRemove:
    """**Validates: Requirements 2.5**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(stakeholder=st_stakeholder())
    def test_referential_integrity_on_remove(
        self, stakeholder: Stakeholder
    ) -> None:
        """For any Stakeholder that is a member of an active StakeholderMap,
        calling registry.remove() on that Stakeholder shall raise an error.
        """
        # Feature: stakeholder-mapping, Property 9: Referential integrity on remove
        registry = StakeholderRegistry()
        registry.register(stakeholder)

        # Mark the stakeholder as being in an active map
        registry.mark_in_map(stakeholder.stakeholder_id, stakeholder.scenario)

        try:
            registry.remove(stakeholder.stakeholder_id, stakeholder.scenario)
            raise AssertionError(
                "Expected ValueError when removing stakeholder in active map, "
                "but removal succeeded."
            )
        except ValueError:
            pass  # Expected — referential integrity enforced

        # Verify the stakeholder is still active
        retrieved = registry.get(stakeholder.stakeholder_id, stakeholder.scenario)
        assert retrieved is not None
        assert retrieved.active is True

        # After unmarking, removal should succeed
        registry.unmark_from_map(stakeholder.stakeholder_id, stakeholder.scenario)
        registry.remove(stakeholder.stakeholder_id, stakeholder.scenario)
        retrieved = registry.get(stakeholder.stakeholder_id, stakeholder.scenario)
        assert retrieved is not None
        assert retrieved.active is False

# ---------------------------------------------------------------------------
# Property 29: Parser rejects missing required fields
# Feature: stakeholder-mapping, Property 29: Parser rejects missing required fields
# ---------------------------------------------------------------------------

# Required top-level fields of StakeholderMapModel
_STAKEHOLDER_MAP_REQUIRED_FIELDS = [
    "map_id",
    "scenario",
    "stakeholders",
    "alignment_matrix",
    "conflicts",
    "timestamp",
]


class TestProperty29ParserRejectsMissingRequiredFields:
    """**Validates: Requirements 8.4**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        model=st_stakeholder_map_model(),
        fields_to_remove=st.lists(
            st.sampled_from(_STAKEHOLDER_MAP_REQUIRED_FIELDS),
            min_size=1,
            max_size=len(_STAKEHOLDER_MAP_REQUIRED_FIELDS),
            unique=True,
        ),
    )
    def test_parser_rejects_missing_required_fields(
        self,
        model: StakeholderMapModel,
        fields_to_remove: list[str],
    ) -> None:
        """For any valid StakeholderMapModel with one or more required fields
        removed, the parser shall raise a ValidationError that names the
        missing fields.

        Property: removing required fields from serialized JSON causes
                  ValidationError listing those fields.
        """
        # Feature: stakeholder-mapping, Property 29: Parser rejects missing required fields
        json_str = model.model_dump_json()
        data = json.loads(json_str)

        for field in fields_to_remove:
            data.pop(field, None)

        modified_json = json.dumps(data)

        try:
            StakeholderMapModel.model_validate_json(modified_json)
            # If we get here, the parser did not reject — fail the test
            raise AssertionError(
                f"Expected ValidationError for missing fields {fields_to_remove}, "
                f"but parsing succeeded."
            )
        except ValidationError as exc:
            error_str = str(exc)
            # Each removed field should be mentioned in the error
            for field in fields_to_remove:
                assert field in error_str, (
                    f"ValidationError did not mention missing field '{field}'.\n"
                    f"Removed fields: {fields_to_remove}\n"
                    f"Error: {error_str}"
                )


# ---------------------------------------------------------------------------
# Property 30: Parser rejects invalid field types
# Feature: stakeholder-mapping, Property 30: Parser rejects invalid field types
# ---------------------------------------------------------------------------

# Mapping of field name → strategy that produces an incompatible type value
_INCOMPATIBLE_TYPE_REPLACEMENTS: dict[str, list] = {
    "map_id": [12345, True, ["not", "a", "string"], {"key": "val"}],
    "scenario": [99999, False, [1, 2, 3], {"nested": True}],
    "stakeholders": ["not_a_list", 42, True],
    "alignment_matrix": ["not_a_list", 42, False],
    "conflicts": ["not_a_list", 42, True],
    "timestamp": ["not-a-date", ["bad"], {"not": "a_datetime"}],
}


class TestProperty30ParserRejectsInvalidFieldTypes:
    """**Validates: Requirements 8.5**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        model=st_stakeholder_map_model(),
        field_name=st.sampled_from(list(_INCOMPATIBLE_TYPE_REPLACEMENTS.keys())),
        data=st.data(),
    )
    def test_parser_rejects_invalid_field_types(
        self,
        model: StakeholderMapModel,
        field_name: str,
        data: st.DataObject,
    ) -> None:
        """For any valid StakeholderMapModel with one or more field values
        replaced by incompatible types, the parser shall raise a
        ValidationError identifying the field.

        Property: replacing a field value with an incompatible type causes
                  ValidationError mentioning that field.
        """
        # Feature: stakeholder-mapping, Property 30: Parser rejects invalid field types
        json_str = model.model_dump_json()
        parsed = json.loads(json_str)

        # Pick a random incompatible replacement for the chosen field
        replacements = _INCOMPATIBLE_TYPE_REPLACEMENTS[field_name]
        bad_value = data.draw(st.sampled_from(replacements))
        parsed[field_name] = bad_value

        modified_json = json.dumps(parsed)

        try:
            StakeholderMapModel.model_validate_json(modified_json)
            raise AssertionError(
                f"Expected ValidationError for field '{field_name}' "
                f"set to {bad_value!r}, but parsing succeeded."
            )
        except ValidationError as exc:
            error_str = str(exc)
            assert field_name in error_str, (
                f"ValidationError did not mention field '{field_name}'.\n"
                f"Bad value: {bad_value!r}\n"
                f"Error: {error_str}"
            )

# ---------------------------------------------------------------------------
# Shared strategy: batch of stakeholders sharing one scenario with unique IDs
# ---------------------------------------------------------------------------


@st.composite
def st_scenario_stakeholder_batch(
    draw: st.DrawFn,
    min_size: int = 0,
    max_size: int = 5,
) -> tuple[str, list[Stakeholder]]:
    """Generate a scenario and a batch of unique-ID stakeholders for it."""
    scenario = draw(st.sampled_from(["travel", "career", "finance", "health"]))
    count = draw(st.integers(min_value=min_size, max_value=max_size))
    stakeholders: list[Stakeholder] = []
    seen_ids: set[str] = set()
    for _ in range(count):
        s = draw(st_stakeholder())
        attempt = 0
        while s.stakeholder_id in seen_ids and attempt < 10:
            s = draw(st_stakeholder())
            attempt += 1
        if s.stakeholder_id not in seen_ids:
            seen_ids.add(s.stakeholder_id)
            stakeholders.append(
                s.model_copy(update={"scenario": scenario, "active": True}),
            )
    return scenario, stakeholders


# ---------------------------------------------------------------------------
# Property 10: Map includes all active stakeholders
# Feature: stakeholder-mapping, Property 10: Map includes all active stakeholders
# ---------------------------------------------------------------------------


class TestProperty10MapIncludesAllActiveStakeholders:
    """**Validates: Requirements 3.1**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_scenario_stakeholder_batch(min_size=0, max_size=5))
    def test_map_includes_all_active_stakeholders(
        self, data: tuple[str, list[Stakeholder]]
    ) -> None:
        """For any scenario with N active Stakeholders,
        StakeholderMapBuilder.build(scenario) shall produce a map
        containing exactly those N Stakeholders.
        """
        # Feature: stakeholder-mapping, Property 10: Map includes all active stakeholders
        scenario, stakeholders = data
        registry = StakeholderRegistry()
        for s in stakeholders:
            registry.register(s)

        builder = StakeholderMapBuilder(registry)
        result = builder.build(scenario)

        expected_ids = {s.stakeholder_id for s in stakeholders}
        actual_ids = {s.stakeholder_id for s in result.stakeholders}
        assert actual_ids == expected_ids, (
            f"Expected stakeholder IDs {expected_ids}, got {actual_ids}"
        )
        assert len(result.stakeholders) == len(stakeholders)


# ---------------------------------------------------------------------------
# Property 11: Pairwise alignment count
# Feature: stakeholder-mapping, Property 11: Pairwise alignment count
# ---------------------------------------------------------------------------


class TestProperty11PairwiseAlignmentCount:
    """**Validates: Requirements 3.2**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_scenario_stakeholder_batch(min_size=0, max_size=5))
    def test_pairwise_alignment_count(
        self, data: tuple[str, list[Stakeholder]]
    ) -> None:
        """For any StakeholderMap with N stakeholders (N >= 2), the alignment
        matrix shall contain exactly N*(N-1)/2 pairwise entries.
        For N < 2, the alignment matrix shall be empty.
        """
        # Feature: stakeholder-mapping, Property 11: Pairwise alignment count
        scenario, stakeholders = data
        registry = StakeholderRegistry()
        for s in stakeholders:
            registry.register(s)

        builder = StakeholderMapBuilder(registry)
        result = builder.build(scenario)

        n = len(stakeholders)
        expected_count = n * (n - 1) // 2
        assert len(result.alignment_matrix) == expected_count, (
            f"Expected {expected_count} pairwise entries for {n} stakeholders, "
            f"got {len(result.alignment_matrix)}"
        )


# ---------------------------------------------------------------------------
# Property 12: Classification consistency with score
# Feature: stakeholder-mapping, Property 12: Classification consistency with score
# ---------------------------------------------------------------------------


class TestProperty12ClassificationConsistencyWithScore:
    """**Validates: Requirements 3.3**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_scenario_stakeholder_batch(min_size=2, max_size=5))
    def test_classification_consistency_with_score(
        self, data: tuple[str, list[Stakeholder]]
    ) -> None:
        """For any PairwiseAlignment entry, the classification shall be
        "aligned" if score >= 0.7, "neutral" if 0.3 <= score < 0.7,
        and "conflicting" if score < 0.3.
        """
        # Feature: stakeholder-mapping, Property 12: Classification consistency with score
        scenario, stakeholders = data
        registry = StakeholderRegistry()
        for s in stakeholders:
            registry.register(s)

        builder = StakeholderMapBuilder(registry)
        result = builder.build(scenario)

        for pa in result.alignment_matrix:
            if pa.score >= 0.7:
                expected_cls = "aligned"
            elif pa.score >= 0.3:
                expected_cls = "neutral"
            else:
                expected_cls = "conflicting"
            assert pa.classification == expected_cls, (
                f"Score {pa.score} should be '{expected_cls}', "
                f"got '{pa.classification}' "
                f"(pair: {pa.stakeholder_a_id} ↔ {pa.stakeholder_b_id})"
            )


# ---------------------------------------------------------------------------
# Property 13: Map traceability fields
# Feature: stakeholder-mapping, Property 13: Map traceability fields
# ---------------------------------------------------------------------------


class TestProperty13MapTraceabilityFields:
    """**Validates: Requirements 3.5**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_scenario_stakeholder_batch(min_size=0, max_size=5))
    def test_map_traceability_fields(
        self, data: tuple[str, list[Stakeholder]]
    ) -> None:
        """For any built StakeholderMap, timestamp shall be non-null and
        scenario shall match the requested scenario.
        """
        # Feature: stakeholder-mapping, Property 13: Map traceability fields
        scenario, stakeholders = data
        registry = StakeholderRegistry()
        for s in stakeholders:
            registry.register(s)

        builder = StakeholderMapBuilder(registry)
        result = builder.build(scenario)

        assert result.timestamp is not None, "Map timestamp must not be None"
        assert result.scenario == scenario, (
            f"Expected scenario '{scenario}', got '{result.scenario}'"
        )


# ---------------------------------------------------------------------------
# Property 34: Two-party export produces valid AlignmentReport
# Feature: stakeholder-mapping, Property 34: Two-party export produces valid AlignmentReport
# ---------------------------------------------------------------------------


@st.composite
def st_user_and_org_stakeholders(
    draw: st.DrawFn,
) -> tuple[str, Stakeholder, Stakeholder]:
    """Generate a scenario with at least one user and one org stakeholder."""
    from hypothesis import assume

    scenario = draw(st.sampled_from(["travel", "career", "finance", "health"]))

    user_s = draw(st_stakeholder())
    user_s = user_s.model_copy(
        update={
            "scenario": scenario,
            "role": StakeholderRole.USER,
            "active": True,
        },
    )

    org_s = draw(st_stakeholder())
    assume(org_s.stakeholder_id != user_s.stakeholder_id)
    org_s = org_s.model_copy(
        update={
            "scenario": scenario,
            "role": StakeholderRole.ORG,
            "active": True,
        },
    )

    return scenario, user_s, org_s


class TestProperty34TwoPartyExportProducesValidAlignmentReport:
    """**Validates: Requirements 9.4**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_user_and_org_stakeholders())
    def test_two_party_export_produces_valid_alignment_report(
        self, data: tuple[str, Stakeholder, Stakeholder]
    ) -> None:
        """For any StakeholderMap containing at least one user-type and one
        org-type Stakeholder, export_as_alignment_report(map, user_id, org_id)
        shall return an AlignmentReport whose alignment_score is in [0, 1]
        and whose conflicts list matches the pairwise conflicts between
        those two stakeholders.
        """
        # Feature: stakeholder-mapping, Property 34: Two-party export produces valid AlignmentReport
        scenario, user_s, org_s = data

        registry = StakeholderRegistry()
        registry.register(user_s)
        registry.register(org_s)

        builder = StakeholderMapBuilder(registry)
        map_model = builder.build(scenario)

        report = builder.export_as_alignment_report(
            map_model, user_s.stakeholder_id, org_s.stakeholder_id,
        )

        # Validate it's an AlignmentReport with correct fields
        assert isinstance(report, AlignmentReport)
        assert 0.0 <= report.alignment_score <= 1.0, (
            f"alignment_score {report.alignment_score} out of [0, 1]"
        )
        assert report.user_id == user_s.stakeholder_id
        assert report.org_id == org_s.stakeholder_id
        assert report.scenario == scenario

        # Conflicts should only reference shared dimensions with actual disagreements
        user_dims = {d.dimension: d for d in user_s.interest_dimensions}
        org_dims = {d.dimension: d for d in org_s.interest_dimensions}
        shared = set(user_dims.keys()) & set(org_dims.keys())

        for conflict in report.conflicts:
            dim_name = conflict["dimension"]
            assert dim_name in shared, (
                f"Conflict dimension '{dim_name}' not in shared dims {shared}"
            )

# ---------------------------------------------------------------------------
# Shared strategies for ConflictDetectionEngine property tests
# ---------------------------------------------------------------------------


@st.composite
def st_direction_conflict_pair(
    draw: st.DrawFn,
) -> tuple[str, Stakeholder, Stakeholder, str]:
    """Generate two stakeholders that share at least one dimension with
    opposing preference directions, suitable for testing direction conflicts.

    Returns (scenario, stakeholder_a, stakeholder_b, shared_dim_name).
    """
    scenario = draw(st.sampled_from(["travel", "career", "finance", "health"]))

    # Pick a shared dimension name
    shared_dim = draw(st.sampled_from(_DIMENSION_NAMES))

    # Generate weights and influence for the shared dimension
    weight_a = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    weight_b = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    influence_a = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    influence_b = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))

    # Stakeholder A: higher_is_better, Stakeholder B: lower_is_better
    dim_a = InterestDimension(
        dimension=shared_dim,
        direction=PreferenceDirection.HIGHER_IS_BETTER,
        weight=weight_a,
    )
    dim_b = InterestDimension(
        dimension=shared_dim,
        direction=PreferenceDirection.LOWER_IS_BETTER,
        weight=weight_b,
    )

    id_a = draw(st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True))
    id_b = draw(
        st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True).filter(
            lambda x: x != id_a
        ),
    )

    ts = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 1, 1),
            timezones=st.just(timezone.utc),
        ),
    )

    stakeholder_a = Stakeholder(
        stakeholder_id=id_a,
        role=StakeholderRole.USER,
        display_name="User A",
        scenario=scenario,
        interest_dimensions=[dim_a],
        influence_weights={shared_dim: influence_a},
        active=True,
        version=1,
        created_at=ts,
        updated_at=ts,
    )
    stakeholder_b = Stakeholder(
        stakeholder_id=id_b,
        role=StakeholderRole.ORG,
        display_name="Org B",
        scenario=scenario,
        interest_dimensions=[dim_b],
        influence_weights={shared_dim: influence_b},
        active=True,
        version=1,
        created_at=ts,
        updated_at=ts,
    )

    return scenario, stakeholder_a, stakeholder_b, shared_dim


@st.composite
def st_weight_conflict_pair(
    draw: st.DrawFn,
) -> tuple[str, Stakeholder, Stakeholder, str]:
    """Generate two stakeholders that share at least one dimension with the
    same preference direction but weight difference > 0.3, suitable for
    testing weight conflicts.

    Returns (scenario, stakeholder_a, stakeholder_b, shared_dim_name).
    """
    scenario = draw(st.sampled_from(["travel", "career", "finance", "health"]))
    shared_dim = draw(st.sampled_from(_DIMENSION_NAMES))
    direction = draw(st_preference_direction())

    # Ensure weight difference > 0.3
    weight_a = draw(st.floats(min_value=0.0, max_value=0.69, allow_nan=False))
    weight_b = draw(
        st.floats(
            min_value=weight_a + 0.31,
            max_value=1.0,
            allow_nan=False,
        ),
    )

    influence_a = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    influence_b = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))

    dim_a = InterestDimension(
        dimension=shared_dim, direction=direction, weight=weight_a,
    )
    dim_b = InterestDimension(
        dimension=shared_dim, direction=direction, weight=weight_b,
    )

    id_a = draw(st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True))
    id_b = draw(
        st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True).filter(
            lambda x: x != id_a
        ),
    )

    ts = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 1, 1),
            timezones=st.just(timezone.utc),
        ),
    )

    stakeholder_a = Stakeholder(
        stakeholder_id=id_a,
        role=StakeholderRole.USER,
        display_name="User A",
        scenario=scenario,
        interest_dimensions=[dim_a],
        influence_weights={shared_dim: influence_a},
        active=True,
        version=1,
        created_at=ts,
        updated_at=ts,
    )
    stakeholder_b = Stakeholder(
        stakeholder_id=id_b,
        role=StakeholderRole.ORG,
        display_name="Org B",
        scenario=scenario,
        interest_dimensions=[dim_b],
        influence_weights={shared_dim: influence_b},
        active=True,
        version=1,
        created_at=ts,
        updated_at=ts,
    )

    return scenario, stakeholder_a, stakeholder_b, shared_dim


# ---------------------------------------------------------------------------
# Property 14: Direction conflict detection completeness
# Feature: stakeholder-mapping, Property 14: Direction conflict detection completeness
# ---------------------------------------------------------------------------


class TestProperty14DirectionConflictDetectionCompleteness:
    """**Validates: Requirements 4.1**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_direction_conflict_pair())
    def test_direction_conflict_detected(
        self,
        data: tuple[str, Stakeholder, Stakeholder, str],
    ) -> None:
        """For any pair of Stakeholders sharing a dimension where one has
        higher_is_better and the other has lower_is_better, the
        ConflictDetectionEngine shall produce a conflict of type "direction"
        for that dimension.
        """
        # Feature: stakeholder-mapping, Property 14: Direction conflict detection completeness
        scenario, stakeholder_a, stakeholder_b, shared_dim = data

        map_model = StakeholderMapModel(
            map_id="test-map",
            scenario=scenario,
            stakeholders=[stakeholder_a, stakeholder_b],
            alignment_matrix=[],
            conflicts=[],
            timestamp=datetime.now(tz=timezone.utc),
        )

        engine = ConflictDetectionEngine()
        conflicts = engine.detect(map_model)

        # There must be at least one direction conflict on the shared dimension
        direction_conflicts = [
            c
            for c in conflicts
            if c.dimension == shared_dim and c.conflict_type == "direction"
        ]
        assert len(direction_conflicts) >= 1, (
            f"Expected a direction conflict on dimension '{shared_dim}' "
            f"between {stakeholder_a.stakeholder_id} and "
            f"{stakeholder_b.stakeholder_id}, but found none. "
            f"All conflicts: {conflicts}"
        )

        # Verify the conflict references the correct stakeholder pair
        c = direction_conflicts[0]
        pair_ids = {c.stakeholder_a_id, c.stakeholder_b_id}
        expected_ids = {
            stakeholder_a.stakeholder_id,
            stakeholder_b.stakeholder_id,
        }
        assert pair_ids == expected_ids, (
            f"Conflict stakeholder IDs {pair_ids} don't match "
            f"expected {expected_ids}"
        )


# ---------------------------------------------------------------------------
# Property 15: Weight conflict detection completeness
# Feature: stakeholder-mapping, Property 15: Weight conflict detection completeness
# ---------------------------------------------------------------------------


class TestProperty15WeightConflictDetectionCompleteness:
    """**Validates: Requirements 4.2**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_weight_conflict_pair())
    def test_weight_conflict_detected(
        self,
        data: tuple[str, Stakeholder, Stakeholder, str],
    ) -> None:
        """For any pair of Stakeholders sharing a dimension with the same
        preference direction but weight difference > 0.3, the
        ConflictDetectionEngine shall produce a conflict of type "weight"
        for that dimension.
        """
        # Feature: stakeholder-mapping, Property 15: Weight conflict detection completeness
        scenario, stakeholder_a, stakeholder_b, shared_dim = data

        map_model = StakeholderMapModel(
            map_id="test-map",
            scenario=scenario,
            stakeholders=[stakeholder_a, stakeholder_b],
            alignment_matrix=[],
            conflicts=[],
            timestamp=datetime.now(tz=timezone.utc),
        )

        engine = ConflictDetectionEngine()
        conflicts = engine.detect(map_model)

        # There must be at least one weight conflict on the shared dimension
        weight_conflicts = [
            c
            for c in conflicts
            if c.dimension == shared_dim and c.conflict_type == "weight"
        ]
        assert len(weight_conflicts) >= 1, (
            f"Expected a weight conflict on dimension '{shared_dim}' "
            f"between {stakeholder_a.stakeholder_id} and "
            f"{stakeholder_b.stakeholder_id} "
            f"(weight_a={stakeholder_a.interest_dimensions[0].weight}, "
            f"weight_b={stakeholder_b.interest_dimensions[0].weight}, "
            f"diff={abs(stakeholder_a.interest_dimensions[0].weight - stakeholder_b.interest_dimensions[0].weight)}), "
            f"but found none. All conflicts: {conflicts}"
        )

        # Verify the conflict references the correct stakeholder pair
        c = weight_conflicts[0]
        pair_ids = {c.stakeholder_a_id, c.stakeholder_b_id}
        expected_ids = {
            stakeholder_a.stakeholder_id,
            stakeholder_b.stakeholder_id,
        }
        assert pair_ids == expected_ids, (
            f"Conflict stakeholder IDs {pair_ids} don't match "
            f"expected {expected_ids}"
        )


# ---------------------------------------------------------------------------
# Property 16: Conflict severity range and formula
# Feature: stakeholder-mapping, Property 16: Conflict severity range and formula
# ---------------------------------------------------------------------------


class TestProperty16ConflictSeverityRangeAndFormula:
    """**Validates: Requirements 4.3**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_scenario_stakeholder_batch(min_size=2, max_size=5))
    def test_conflict_severity_range_and_formula(
        self,
        data: tuple[str, list[Stakeholder]],
    ) -> None:
        """For any detected Conflict, severity shall be in [0.0, 1.0] and
        shall equal clamp(influence_A * influence_B * disagreement_magnitude,
        0, 1).

        For direction conflicts, disagreement_magnitude = 1.0 (implicit in
        the formula: severity = clamp(influence_A * influence_B, 0, 1)).
        For weight conflicts, disagreement_magnitude = abs(weight_A - weight_B).
        """
        # Feature: stakeholder-mapping, Property 16: Conflict severity range and formula
        scenario, stakeholders = data

        map_model = StakeholderMapModel(
            map_id="test-map",
            scenario=scenario,
            stakeholders=stakeholders,
            alignment_matrix=[],
            conflicts=[],
            timestamp=datetime.now(tz=timezone.utc),
        )

        engine = ConflictDetectionEngine()
        conflicts = engine.detect(map_model)

        # Build lookup for stakeholders
        s_lookup = {s.stakeholder_id: s for s in stakeholders}

        for c in conflicts:
            # Severity must be in [0.0, 1.0]
            assert 0.0 <= c.severity <= 1.0, (
                f"Severity {c.severity} out of range [0, 1] "
                f"for conflict on '{c.dimension}'"
            )

            sa = s_lookup[c.stakeholder_a_id]
            sb = s_lookup[c.stakeholder_b_id]
            inf_a = sa.influence_weights.get(c.dimension, 0.0)
            inf_b = sb.influence_weights.get(c.dimension, 0.0)

            if c.conflict_type == "direction":
                # severity = clamp(influence_A * influence_B, 0, 1)
                expected = max(0.0, min(1.0, inf_a * inf_b))
            else:
                # weight conflict: severity = clamp(inf_A * inf_B * weight_diff, 0, 1)
                a_dims = {d.dimension: d for d in sa.interest_dimensions}
                b_dims = {d.dimension: d for d in sb.interest_dimensions}
                weight_diff = abs(
                    a_dims[c.dimension].weight - b_dims[c.dimension].weight,
                )
                expected = max(0.0, min(1.0, inf_a * inf_b * weight_diff))

            assert abs(c.severity - expected) < 1e-9, (
                f"Severity mismatch for {c.conflict_type} conflict on "
                f"'{c.dimension}': got {c.severity}, expected {expected} "
                f"(inf_a={inf_a}, inf_b={inf_b})"
            )


# ---------------------------------------------------------------------------
# Property 17: Conflicts sorted by severity descending
# Feature: stakeholder-mapping, Property 17: Conflicts sorted by severity descending
# ---------------------------------------------------------------------------


class TestProperty17ConflictsSortedBySeverityDescending:
    """**Validates: Requirements 4.4**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_scenario_stakeholder_batch(min_size=2, max_size=5))
    def test_conflicts_sorted_by_severity_descending(
        self,
        data: tuple[str, list[Stakeholder]],
    ) -> None:
        """For any list of conflicts returned by the engine, for all
        consecutive pairs, conflicts[i].severity >= conflicts[i+1].severity.
        """
        # Feature: stakeholder-mapping, Property 17: Conflicts sorted by severity descending
        scenario, stakeholders = data

        map_model = StakeholderMapModel(
            map_id="test-map",
            scenario=scenario,
            stakeholders=stakeholders,
            alignment_matrix=[],
            conflicts=[],
            timestamp=datetime.now(tz=timezone.utc),
        )

        engine = ConflictDetectionEngine()
        conflicts = engine.detect(map_model)

        for i in range(len(conflicts) - 1):
            assert conflicts[i].severity >= conflicts[i + 1].severity, (
                f"Conflicts not sorted by severity descending: "
                f"conflicts[{i}].severity={conflicts[i].severity} < "
                f"conflicts[{i + 1}].severity={conflicts[i + 1].severity}"
            )

# ---------------------------------------------------------------------------
# Property 18: One proposal per conflicting dimension
# Feature: stakeholder-mapping, Property 18: One proposal per conflicting dimension
# ---------------------------------------------------------------------------


class TestProperty18OneProposalPerConflictingDimension:
    """**Validates: Requirements 5.1**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_scenario_stakeholder_batch(min_size=2, max_size=5))
    def test_one_proposal_per_conflicting_dimension(
        self,
        data: tuple[str, list[Stakeholder]],
    ) -> None:
        """For any set of detected conflicts, the NegotiationStrategy shall
        produce exactly one proposal per unique conflicting dimension.
        """
        # Feature: stakeholder-mapping, Property 18: One proposal per conflicting dimension
        scenario, stakeholders = data

        map_model = StakeholderMapModel(
            map_id="test-map",
            scenario=scenario,
            stakeholders=stakeholders,
            alignment_matrix=[],
            conflicts=[],
            timestamp=datetime.now(tz=timezone.utc),
        )

        engine = ConflictDetectionEngine()
        conflicts = engine.detect(map_model)

        strategy = NegotiationStrategy()
        proposals = strategy.generate(conflicts, map_model)

        # Unique conflicting dimensions from detected conflicts
        unique_dims = {c.dimension for c in conflicts}

        # There should be exactly one proposal per unique dimension
        proposal_dims = [p.dimension for p in proposals]
        assert len(proposal_dims) == len(unique_dims), (
            f"Expected {len(unique_dims)} proposals (one per dimension), "
            f"got {len(proposal_dims)}. "
            f"Conflict dims: {unique_dims}, proposal dims: {proposal_dims}"
        )
        assert set(proposal_dims) == unique_dims, (
            f"Proposal dimensions {set(proposal_dims)} don't match "
            f"conflict dimensions {unique_dims}"
        )

        # No duplicate dimensions in proposals
        assert len(proposal_dims) == len(set(proposal_dims)), (
            f"Duplicate dimensions in proposals: {proposal_dims}"
        )


# ---------------------------------------------------------------------------
# Shared strategy: two stakeholders with different influence on a shared dim
# ---------------------------------------------------------------------------


@st.composite
def st_influence_conflict_pair(
    draw: st.DrawFn,
) -> tuple[str, Stakeholder, Stakeholder, str, list[Conflict]]:
    """Generate two stakeholders with a direction conflict on a shared
    dimension where influence_A < influence_B (strictly).

    Returns (scenario, stakeholder_a, stakeholder_b, shared_dim, conflicts).
    """
    scenario = draw(st.sampled_from(["travel", "career", "finance", "health"]))
    shared_dim = draw(st.sampled_from(_DIMENSION_NAMES))

    weight_a = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    weight_b = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))

    # Ensure influence_a < influence_b (strictly)
    influence_a = draw(st.floats(min_value=0.01, max_value=0.49, allow_nan=False))
    influence_b = draw(st.floats(min_value=influence_a + 0.01, max_value=1.0, allow_nan=False))

    dim_a = InterestDimension(
        dimension=shared_dim,
        direction=PreferenceDirection.HIGHER_IS_BETTER,
        weight=weight_a,
    )
    dim_b = InterestDimension(
        dimension=shared_dim,
        direction=PreferenceDirection.LOWER_IS_BETTER,
        weight=weight_b,
    )

    id_a = draw(st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True))
    id_b = draw(
        st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True).filter(
            lambda x: x != id_a
        ),
    )

    ts = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 1, 1),
            timezones=st.just(timezone.utc),
        ),
    )

    stakeholder_a = Stakeholder(
        stakeholder_id=id_a,
        role=StakeholderRole.USER,
        display_name="User A",
        scenario=scenario,
        interest_dimensions=[dim_a],
        influence_weights={shared_dim: influence_a},
        active=True,
        version=1,
        created_at=ts,
        updated_at=ts,
    )
    stakeholder_b = Stakeholder(
        stakeholder_id=id_b,
        role=StakeholderRole.ORG,
        display_name="Org B",
        scenario=scenario,
        interest_dimensions=[dim_b],
        influence_weights={shared_dim: influence_b},
        active=True,
        version=1,
        created_at=ts,
        updated_at=ts,
    )

    # Build the conflict manually (direction conflict)
    severity = max(0.0, min(1.0, influence_a * influence_b))
    conflict = Conflict(
        stakeholder_a_id=id_a,
        stakeholder_b_id=id_b,
        dimension=shared_dim,
        conflict_type="direction",
        severity=severity,
        details={
            "direction_a": PreferenceDirection.HIGHER_IS_BETTER.value,
            "direction_b": PreferenceDirection.LOWER_IS_BETTER.value,
            "influence_a": influence_a,
            "influence_b": influence_b,
        },
    )

    return scenario, stakeholder_a, stakeholder_b, shared_dim, [conflict]


# ---------------------------------------------------------------------------
# Property 19: Lower influence concedes more
# Feature: stakeholder-mapping, Property 19: Lower influence concedes more
# ---------------------------------------------------------------------------


class TestProperty19LowerInfluenceConcedesMore:
    """**Validates: Requirements 5.2**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_influence_conflict_pair())
    def test_lower_influence_concedes_more(
        self,
        data: tuple[str, Stakeholder, Stakeholder, str, list[Conflict]],
    ) -> None:
        """For any NegotiationProposal involving two stakeholders where
        influence_A < influence_B, the concession for A shall be >= the
        concession for B.
        """
        # Feature: stakeholder-mapping, Property 19: Lower influence concedes more
        scenario, stakeholder_a, stakeholder_b, shared_dim, conflicts = data

        map_model = StakeholderMapModel(
            map_id="test-map",
            scenario=scenario,
            stakeholders=[stakeholder_a, stakeholder_b],
            alignment_matrix=[],
            conflicts=[],
            timestamp=datetime.now(tz=timezone.utc),
        )

        strategy = NegotiationStrategy()
        proposals = strategy.generate(conflicts, map_model)

        # There should be exactly one proposal for the shared dimension
        assert len(proposals) == 1, (
            f"Expected 1 proposal, got {len(proposals)}"
        )
        proposal = proposals[0]
        assert proposal.dimension == shared_dim

        concession_a = proposal.concessions.get(stakeholder_a.stakeholder_id, 0.0)
        concession_b = proposal.concessions.get(stakeholder_b.stakeholder_id, 0.0)

        # influence_a < influence_b → concession_a >= concession_b
        assert concession_a >= concession_b - 1e-9, (
            f"Lower-influence stakeholder A (influence="
            f"{stakeholder_a.influence_weights[shared_dim]}) should concede "
            f">= higher-influence stakeholder B (influence="
            f"{stakeholder_b.influence_weights[shared_dim]}), but "
            f"concession_a={concession_a} < concession_b={concession_b}"
        )


# ---------------------------------------------------------------------------
# Property 20: Negotiation proposal invariants
# Feature: stakeholder-mapping, Property 20: Negotiation proposal invariants
# ---------------------------------------------------------------------------


class TestProperty20NegotiationProposalInvariants:
    """**Validates: Requirements 5.3, 5.4**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_scenario_stakeholder_batch(min_size=2, max_size=5))
    def test_negotiation_proposal_invariants(
        self,
        data: tuple[str, list[Stakeholder]],
    ) -> None:
        """For any NegotiationProposal:
        (a) compromise_weight falls between the min and max weights of the
            conflicting stakeholders on that dimension; and
        (b) feasibility is in [0.0, 1.0].
        """
        # Feature: stakeholder-mapping, Property 20: Negotiation proposal invariants
        scenario, stakeholders = data

        map_model = StakeholderMapModel(
            map_id="test-map",
            scenario=scenario,
            stakeholders=stakeholders,
            alignment_matrix=[],
            conflicts=[],
            timestamp=datetime.now(tz=timezone.utc),
        )

        engine = ConflictDetectionEngine()
        conflicts = engine.detect(map_model)

        strategy = NegotiationStrategy()
        proposals = strategy.generate(conflicts, map_model)

        # Build lookup for stakeholder dimensions
        s_lookup = {s.stakeholder_id: s for s in stakeholders}

        # Group conflicts by dimension to find involved stakeholders per dim
        dim_conflicts: dict[str, list[Conflict]] = {}
        for c in conflicts:
            dim_conflicts.setdefault(c.dimension, []).append(c)

        for proposal in proposals:
            # (a) compromise_weight between min and max weights of involved parties
            involved_ids: set[str] = set()
            for c in dim_conflicts.get(proposal.dimension, []):
                involved_ids.add(c.stakeholder_a_id)
                involved_ids.add(c.stakeholder_b_id)

            weights_on_dim: list[float] = []
            for sid in involved_ids:
                s = s_lookup.get(sid)
                if s is not None:
                    dim_obj = next(
                        (d for d in s.interest_dimensions if d.dimension == proposal.dimension),
                        None,
                    )
                    if dim_obj is not None:
                        weights_on_dim.append(dim_obj.weight)

            if weights_on_dim:
                min_w = min(weights_on_dim)
                max_w = max(weights_on_dim)
                assert min_w - 1e-9 <= proposal.compromise_weight <= max_w + 1e-9, (
                    f"compromise_weight {proposal.compromise_weight} not in "
                    f"[{min_w}, {max_w}] for dimension '{proposal.dimension}'"
                )

            # (b) feasibility in [0.0, 1.0]
            assert 0.0 <= proposal.feasibility <= 1.0, (
                f"feasibility {proposal.feasibility} out of [0, 1] "
                f"for dimension '{proposal.dimension}'"
            )


# ---------------------------------------------------------------------------
# Shared strategy: conflict pair with hard constraint from OrgPolicy
# ---------------------------------------------------------------------------


@st.composite
def st_hard_constraint_conflict(
    draw: st.DrawFn,
) -> tuple[str, Stakeholder, Stakeholder, str, list[Conflict], OrgPolicy]:
    """Generate two stakeholders with a direction conflict on a dimension
    that is a hard constraint in an OrgPolicy.

    Returns (scenario, user_stakeholder, org_stakeholder, dim, conflicts, org_policy).
    """
    scenario = draw(st.sampled_from(["travel", "career", "finance", "health"]))
    shared_dim = draw(st.sampled_from(_DIMENSION_NAMES))

    weight_a = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    weight_b = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    influence_a = draw(st.floats(min_value=0.01, max_value=1.0, allow_nan=False))
    influence_b = draw(st.floats(min_value=0.01, max_value=1.0, allow_nan=False))

    dim_a = InterestDimension(
        dimension=shared_dim,
        direction=PreferenceDirection.HIGHER_IS_BETTER,
        weight=weight_a,
    )
    dim_b = InterestDimension(
        dimension=shared_dim,
        direction=PreferenceDirection.LOWER_IS_BETTER,
        weight=weight_b,
    )

    id_a = draw(st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True))
    id_b = draw(
        st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True).filter(
            lambda x: x != id_a
        ),
    )

    ts = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 1, 1),
            timezones=st.just(timezone.utc),
        ),
    )

    user_stakeholder = Stakeholder(
        stakeholder_id=id_a,
        role=StakeholderRole.USER,
        display_name="User A",
        scenario=scenario,
        interest_dimensions=[dim_a],
        influence_weights={shared_dim: influence_a},
        active=True,
        version=1,
        created_at=ts,
        updated_at=ts,
    )
    org_stakeholder = Stakeholder(
        stakeholder_id=id_b,
        role=StakeholderRole.ORG,
        display_name="Org B",
        scenario=scenario,
        interest_dimensions=[dim_b],
        influence_weights={shared_dim: influence_b},
        active=True,
        version=1,
        created_at=ts,
        updated_at=ts,
    )

    severity = max(0.0, min(1.0, influence_a * influence_b))
    conflict = Conflict(
        stakeholder_a_id=id_a,
        stakeholder_b_id=id_b,
        dimension=shared_dim,
        conflict_type="direction",
        severity=severity,
        details={
            "direction_a": PreferenceDirection.HIGHER_IS_BETTER.value,
            "direction_b": PreferenceDirection.LOWER_IS_BETTER.value,
            "influence_a": influence_a,
            "influence_b": influence_b,
        },
    )

    # OrgPolicy with the shared dimension as a hard constraint
    org_policy = OrgPolicy(
        org_id=id_b,
        scenario=scenario,
        weights={shared_dim: weight_b},
        constraints={shared_dim: True},
    )

    return scenario, user_stakeholder, org_stakeholder, shared_dim, [conflict], org_policy


# ---------------------------------------------------------------------------
# Property 21: Hard constraint non-negotiability
# Feature: stakeholder-mapping, Property 21: Hard constraint non-negotiability
# ---------------------------------------------------------------------------


class TestProperty21HardConstraintNonNegotiability:
    """**Validates: Requirements 5.5**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_hard_constraint_conflict())
    def test_hard_constraint_non_negotiability(
        self,
        data: tuple[str, Stakeholder, Stakeholder, str, list[Conflict], OrgPolicy],
    ) -> None:
        """For any conflict on a dimension that is a hard constraint in an
        OrgPolicy, the NegotiationProposal shall have non_negotiable=True
        and the constraint holder's concession shall be 0.
        """
        # Feature: stakeholder-mapping, Property 21: Hard constraint non-negotiability
        scenario, user_s, org_s, shared_dim, conflicts, org_policy = data

        map_model = StakeholderMapModel(
            map_id="test-map",
            scenario=scenario,
            stakeholders=[user_s, org_s],
            alignment_matrix=[],
            conflicts=[],
            timestamp=datetime.now(tz=timezone.utc),
        )

        strategy = NegotiationStrategy()
        proposals = strategy.generate(conflicts, map_model, org_policy=org_policy)

        # There should be exactly one proposal for the shared dimension
        assert len(proposals) == 1, (
            f"Expected 1 proposal, got {len(proposals)}"
        )
        proposal = proposals[0]
        assert proposal.dimension == shared_dim

        # non_negotiable must be True
        assert proposal.non_negotiable is True, (
            f"Expected non_negotiable=True for hard constraint dimension "
            f"'{shared_dim}', got {proposal.non_negotiable}"
        )

        # The org stakeholder (constraint holder) concession must be 0
        org_concession = proposal.concessions.get(org_s.stakeholder_id, -1.0)
        assert org_concession == 0.0, (
            f"Expected constraint holder ({org_s.stakeholder_id}) concession "
            f"to be 0.0, got {org_concession}"
        )

# ---------------------------------------------------------------------------
# Shared strategies for engine integration property tests
# ---------------------------------------------------------------------------

# Scenario keywords that map to known registry weight entries
_REGISTRY = get_scenario_registry()
_ENGINE_SCENARIOS = ["lifegoal", "travel", "tokencost", "robotclaw"]


@st.composite
def st_stakeholder_map_with_overlapping_weights(
    draw: st.DrawFn,
) -> tuple[str, StakeholderMapModel, dict[str, float]]:
    """Generate a non-empty StakeholderMapModel whose stakeholders have
    influence_weights that overlap with the scenario's decision_weights
    dimensions, and whose influence values differ from the scenario weights
    so that merging is guaranteed to change the output.

    Returns (query_keyword, stakeholder_map, original_decision_weights).
    """
    scenario = draw(st.sampled_from(_ENGINE_SCENARIOS))
    original_weights = dict(_REGISTRY.get_weights(scenario))

    # Pick at least one dimension from the scenario weights
    dims = list(original_weights.keys())
    chosen_dims = draw(
        st.lists(
            st.sampled_from(dims),
            min_size=1,
            max_size=len(dims),
            unique=True,
        ),
    )

    # Build stakeholder(s) with influence_weights on those dimensions
    # that differ from the scenario weights to guarantee merge changes output
    stakeholders: list[Stakeholder] = []
    for i in range(draw(st.integers(min_value=1, max_value=3))):
        influence: dict[str, float] = {}
        interest_dims: list[InterestDimension] = []
        for dim in chosen_dims:
            scenario_w = original_weights[dim]
            # Generate influence that differs from scenario weight
            inf_val = draw(
                st.floats(min_value=0.0, max_value=1.0, allow_nan=False).filter(
                    lambda v, sw=scenario_w: abs(v - sw) > 1e-9
                ),
            )
            influence[dim] = inf_val
            interest_dims.append(
                InterestDimension(
                    dimension=dim,
                    direction=draw(st_preference_direction()),
                    weight=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
                ),
            )

        sid = draw(st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True))
        # Ensure unique IDs
        while any(s.stakeholder_id == sid for s in stakeholders):
            sid = draw(st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True))

        ts = draw(
            st.datetimes(
                min_value=datetime(2020, 1, 1),
                max_value=datetime(2030, 1, 1),
                timezones=st.just(timezone.utc),
            ),
        )
        stakeholders.append(
            Stakeholder(
                stakeholder_id=sid,
                role=draw(st_stakeholder_role()),
                display_name=f"Stakeholder {i}",
                scenario=scenario,
                interest_dimensions=interest_dims,
                influence_weights=influence,
                active=True,
                version=1,
                created_at=ts,
                updated_at=ts,
            ),
        )

    map_model = StakeholderMapModel(
        map_id="test-merge-map",
        scenario=scenario,
        stakeholders=stakeholders,
        alignment_matrix=[],
        conflicts=[],
        timestamp=draw(
            st.datetimes(
                min_value=datetime(2020, 1, 1),
                max_value=datetime(2030, 1, 1),
                timezones=st.just(timezone.utc),
            ),
        ),
    )

    # Use a query keyword that maps to the chosen scenario
    keyword_map = {
        "lifegoal": "career",
        "travel": "travel",
        "tokencost": "tokencost",
        "robotclaw": "robotclaw",
    }
    query = keyword_map[scenario]

    return query, map_model, original_weights


@st.composite
def st_high_severity_conflict_map(
    draw: st.DrawFn,
) -> tuple[str, StakeholderMapModel]:
    """Generate a StakeholderMapModel with at least one conflict whose
    severity > 0.5. This requires two stakeholders with opposing directions
    on a shared dimension and high influence weights (inf_A * inf_B > 0.5).

    Returns (query_keyword, stakeholder_map).
    """
    scenario = draw(st.sampled_from(_ENGINE_SCENARIOS))
    shared_dim = draw(st.sampled_from(_DIMENSION_NAMES))

    # Ensure influence_a * influence_b > 0.5
    # Both must be > sqrt(0.5) ≈ 0.707 to guarantee product > 0.5
    influence_a = draw(st.floats(min_value=0.75, max_value=1.0, allow_nan=False))
    influence_b = draw(st.floats(min_value=0.75, max_value=1.0, allow_nan=False))

    weight_a = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    weight_b = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))

    dim_a = InterestDimension(
        dimension=shared_dim,
        direction=PreferenceDirection.HIGHER_IS_BETTER,
        weight=weight_a,
    )
    dim_b = InterestDimension(
        dimension=shared_dim,
        direction=PreferenceDirection.LOWER_IS_BETTER,
        weight=weight_b,
    )

    id_a = draw(st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True))
    id_b = draw(
        st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True).filter(
            lambda x: x != id_a
        ),
    )

    ts = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 1, 1),
            timezones=st.just(timezone.utc),
        ),
    )

    stakeholder_a = Stakeholder(
        stakeholder_id=id_a,
        role=StakeholderRole.USER,
        display_name="User High",
        scenario=scenario,
        interest_dimensions=[dim_a],
        influence_weights={shared_dim: influence_a},
        active=True,
        version=1,
        created_at=ts,
        updated_at=ts,
    )
    stakeholder_b = Stakeholder(
        stakeholder_id=id_b,
        role=StakeholderRole.ORG,
        display_name="Org High",
        scenario=scenario,
        interest_dimensions=[dim_b],
        influence_weights={shared_dim: influence_b},
        active=True,
        version=1,
        created_at=ts,
        updated_at=ts,
    )

    map_model = StakeholderMapModel(
        map_id="test-severity-map",
        scenario=scenario,
        stakeholders=[stakeholder_a, stakeholder_b],
        alignment_matrix=[],
        conflicts=[],
        timestamp=ts,
    )

    keyword_map = {
        "lifegoal": "career",
        "travel": "travel",
        "tokencost": "tokencost",
        "robotclaw": "robotclaw",
    }
    query = keyword_map[scenario]

    return query, map_model


# ---------------------------------------------------------------------------
# Property 22: Stakeholder weight merge affects output
# Feature: stakeholder-mapping, Property 22: Stakeholder weight merge affects output
# ---------------------------------------------------------------------------


class TestProperty22StakeholderWeightMergeAffectsOutput:
    """**Validates: Requirements 6.2**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_stakeholder_map_with_overlapping_weights())
    def test_stakeholder_weight_merge_affects_output(
        self,
        data: tuple[str, StakeholderMapModel, dict[str, float]],
    ) -> None:
        """For any set of decision weights and a non-empty StakeholderMap,
        the merged weights shall differ from the original decision weights
        (i.e., stakeholder influence is incorporated).
        """
        # Feature: stakeholder-mapping, Property 22: Stakeholder weight merge affects output
        query, stakeholder_map, original_weights = data

        plan = build_capability_plan(
            query=query,
            stakeholder_map=stakeholder_map,
        )

        merged_weights = plan["decision_weights"]

        # At least one dimension should differ from the original
        any_different = any(
            abs(merged_weights.get(dim, 0.0) - original_weights[dim]) > 1e-9
            for dim in original_weights
        )
        assert any_different, (
            f"Merged weights {merged_weights} are identical to original "
            f"weights {original_weights} — stakeholder influence was not "
            f"incorporated."
        )


# ---------------------------------------------------------------------------
# Property 23: High-severity conflicts produce warnings
# Feature: stakeholder-mapping, Property 23: High-severity conflicts produce warnings
# ---------------------------------------------------------------------------


class TestProperty23HighSeverityConflictsProduceWarnings:
    """**Validates: Requirements 6.4**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_high_severity_conflict_map())
    def test_high_severity_conflicts_produce_warnings(
        self,
        data: tuple[str, StakeholderMapModel],
    ) -> None:
        """For any StakeholderMap containing at least one conflict with
        severity > 0.5, the decision explanation shall contain a warning
        substring about unresolved stakeholder conflicts.
        """
        # Feature: stakeholder-mapping, Property 23: High-severity conflicts produce warnings
        query, stakeholder_map = data

        plan = build_capability_plan(
            query=query,
            stakeholder_map=stakeholder_map,
        )

        # Verify that at least one conflict has severity > 0.5
        context = plan.get("stakeholder_context", {})
        conflicts = context.get("conflicts", [])
        high_severity = [c for c in conflicts if c["severity"] > 0.5]
        assert len(high_severity) >= 1, (
            f"Expected at least one conflict with severity > 0.5, "
            f"but got severities: {[c['severity'] for c in conflicts]}"
        )

        # The plan must have an explanation with warning text
        explanation = plan.get("explanation", "")
        assert "Unresolved stakeholder conflict" in explanation, (
            f"Expected warning about unresolved stakeholder conflicts "
            f"in explanation, but got: {explanation!r}"
        )


# ---------------------------------------------------------------------------
# Property 24: No stakeholder map preserves existing behavior
# Feature: stakeholder-mapping, Property 24: No stakeholder map preserves existing behavior
# ---------------------------------------------------------------------------


class TestProperty24NoStakeholderMapPreservesExistingBehavior:
    """**Validates: Requirements 6.5**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        query=st.sampled_from([
            "career planning advice",
            "travel to Beijing",
            "tokencost optimization",
            "robotclaw dispatch",
            "general question about life",
        ]),
        scenario=st.one_of(
            st.none(),
            st.sampled_from(["lifegoal", "travel", "tokencost", "robotclaw"]),
        ),
    )
    def test_no_stakeholder_map_preserves_existing_behavior(
        self,
        query: str,
        scenario: str | None,
    ) -> None:
        """For any call to build_capability_plan() with stakeholder_map=None,
        the output decision_weights shall be identical to the output without
        the parameter (backward compatibility).
        """
        # Feature: stakeholder-mapping, Property 24: No stakeholder map preserves existing behavior
        plan_with_none = build_capability_plan(
            query=query,
            scenario=scenario,
            stakeholder_map=None,
        )

        plan_without = build_capability_plan(
            query=query,
            scenario=scenario,
        )

        assert plan_with_none["decision_weights"] == plan_without["decision_weights"], (
            f"decision_weights differ when stakeholder_map=None vs omitted.\n"
            f"With None: {plan_with_none['decision_weights']}\n"
            f"Without:   {plan_without['decision_weights']}"
        )

        # Also verify no stakeholder_context is injected
        assert "stakeholder_context" not in plan_with_none, (
            "stakeholder_context should not be present when stakeholder_map=None"
        )
        assert "stakeholder_context" not in plan_without, (
            "stakeholder_context should not be present when stakeholder_map is omitted"
        )

# ---------------------------------------------------------------------------
# Property 25: Per-stakeholder curve point completeness
# Feature: stakeholder-mapping, Property 25: Per-stakeholder curve point completeness
# ---------------------------------------------------------------------------


@st.composite
def st_decision_curve_scenario(
    draw: st.DrawFn,
) -> tuple[StakeholderMapModel, DecisionRecord]:
    """Generate a StakeholderMapModel with 1-5 stakeholders sharing a scenario,
    plus a minimal DecisionRecord for that scenario.

    Returns (map_model, decision_record).
    """
    scenario = draw(st.sampled_from(["travel", "career", "finance", "health"]))

    count = draw(st.integers(min_value=1, max_value=5))
    stakeholders: list[Stakeholder] = []
    seen_ids: set[str] = set()
    for _ in range(count):
        s = draw(st_stakeholder())
        attempt = 0
        while s.stakeholder_id in seen_ids and attempt < 10:
            s = draw(st_stakeholder())
            attempt += 1
        if s.stakeholder_id not in seen_ids:
            seen_ids.add(s.stakeholder_id)
            stakeholders.append(
                s.model_copy(update={"scenario": scenario, "active": True}),
            )

    ts = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 1, 1),
            timezones=st.just(timezone.utc),
        ),
    )

    map_model = StakeholderMapModel(
        map_id="test-curve-map",
        scenario=scenario,
        stakeholders=stakeholders,
        alignment_matrix=[],
        conflicts=[],
        timestamp=ts,
    )

    record = DecisionRecord(
        decision_id="dec-001",
        user_id="user-1",
        scenario=scenario,
        query="test decision",
        created_at=ts,
    )

    return map_model, record


class TestProperty25PerStakeholderCurvePointCompleteness:
    """**Validates: Requirements 7.1, 7.2**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st_decision_curve_scenario())
    def test_per_stakeholder_curve_point_completeness(
        self,
        data: tuple[StakeholderMapModel, DecisionRecord],
    ) -> None:
        """For any completed decision involving N stakeholders, the
        DecisionCurveTracker shall produce N updated curve points, each
        containing decision_count >= 1, acceptance_rate in [0, 1],
        bias_count >= 0, and weight_stability in [0, 1].
        """
        # Feature: stakeholder-mapping, Property 25: Per-stakeholder curve point completeness
        map_model, record = data

        registry = StakeholderRegistry()
        tracker = DecisionCurveTracker(memory=object(), registry=registry)

        tracker.update(record, map_model)

        n = len(map_model.stakeholders)

        # Collect all curve points produced
        all_points: list[DecisionCurvePoint] = []
        for s in map_model.stakeholders:
            curve = tracker.get_curve(s.stakeholder_id, s.scenario, window_days=365)
            assert len(curve) >= 1, (
                f"Expected at least 1 curve point for stakeholder "
                f"'{s.stakeholder_id}', got {len(curve)}"
            )
            all_points.extend(curve)

        # We should have at least N points total (one per stakeholder)
        assert len(all_points) >= n, (
            f"Expected at least {n} curve points, got {len(all_points)}"
        )

        # Validate each point's metric ranges
        for point in all_points:
            assert point.decision_count >= 1, (
                f"decision_count should be >= 1, got {point.decision_count}"
            )
            assert 0.0 <= point.acceptance_rate <= 1.0, (
                f"acceptance_rate {point.acceptance_rate} not in [0, 1]"
            )
            assert point.bias_count >= 0, (
                f"bias_count should be >= 0, got {point.bias_count}"
            )
            assert 0.0 <= point.weight_stability <= 1.0, (
                f"weight_stability {point.weight_stability} not in [0, 1]"
            )


# ---------------------------------------------------------------------------
# Property 26: Decision curve time ordering
# Feature: stakeholder-mapping, Property 26: Decision curve time ordering
# ---------------------------------------------------------------------------


class TestProperty26DecisionCurveTimeOrdering:
    """**Validates: Requirements 7.4**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        stakeholder=st_stakeholder(),
        num_updates=st.integers(min_value=2, max_value=6),
    )
    def test_decision_curve_time_ordering(
        self,
        stakeholder: Stakeholder,
        num_updates: int,
    ) -> None:
        """For any stakeholder's decision curve, the returned list of
        DecisionCurvePoint objects shall be ordered by period ascending.
        """
        # Feature: stakeholder-mapping, Property 26: Decision curve time ordering
        scenario = stakeholder.scenario
        registry = StakeholderRegistry()
        tracker = DecisionCurveTracker(memory=object(), registry=registry)

        map_model = StakeholderMapModel(
            map_id="test-ordering-map",
            scenario=scenario,
            stakeholders=[stakeholder],
            alignment_matrix=[],
            conflicts=[],
            timestamp=datetime.now(tz=timezone.utc),
        )

        record = DecisionRecord(
            decision_id="dec-order",
            user_id="user-1",
            scenario=scenario,
            query="ordering test",
            created_at=datetime.now(tz=timezone.utc),
        )

        # Call update multiple times to accumulate curve points
        for _ in range(num_updates):
            tracker.update(record, map_model)

        curve = tracker.get_curve(
            stakeholder.stakeholder_id, scenario, window_days=365,
        )

        assert len(curve) >= 2, (
            f"Expected at least 2 curve points after {num_updates} updates, "
            f"got {len(curve)}"
        )

        # Verify period ordering is ascending
        for i in range(len(curve) - 1):
            assert curve[i].period <= curve[i + 1].period, (
                f"Curve not ordered by period ascending: "
                f"curve[{i}].period={curve[i].period!r} > "
                f"curve[{i + 1}].period={curve[i + 1].period!r}"
            )


# ---------------------------------------------------------------------------
# Property 27: Convergence and divergence trend detection
# Feature: stakeholder-mapping, Property 27: Convergence and divergence trend detection
# ---------------------------------------------------------------------------


class TestProperty27ConvergenceAndDivergenceTrendDetection:
    """**Validates: Requirements 7.5**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        base_score=st.floats(min_value=0.1, max_value=0.6, allow_nan=False),
        increment=st.floats(min_value=0.01, max_value=0.1, allow_nan=False),
    )
    def test_convergence_detected(
        self,
        base_score: float,
        increment: float,
    ) -> None:
        """If 3 consecutive alignment scores are strictly increasing,
        the trend shall be "convergence".
        """
        # Feature: stakeholder-mapping, Property 27: Convergence and divergence trend detection
        from hypothesis import assume

        # Ensure all 3 scores stay within valid range [0, 1]
        assume(base_score + 2 * increment <= 1.0)

        scores = [base_score, base_score + increment, base_score + 2 * increment]
        assert scores[0] < scores[1] < scores[2]  # strictly increasing

        registry = StakeholderRegistry()
        tracker = DecisionCurveTracker(memory=object(), registry=registry)

        # Manually inject curve points with controlled alignment scores
        sid_a = "stakeholder-a"
        scenario = "travel"
        key = (sid_a, scenario)
        tracker._curves[key] = [
            DecisionCurvePoint(
                period=f"2026-01-0{i + 1}",
                actor=DecisionActor.USER,
                actor_id=sid_a,
                scenario=scenario,
                decision_count=i + 1,
                acceptance_rate=0.5,
                bias_count=0,
                alignment_score=scores[i],
                weight_stability=0.8,
            )
            for i in range(3)
        ]

        trend = tracker.detect_trends(sid_a, "stakeholder-b", scenario)
        assert trend == "convergence", (
            f"Expected 'convergence' for strictly increasing scores "
            f"{scores}, got '{trend}'"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        base_score=st.floats(min_value=0.4, max_value=0.9, allow_nan=False),
        decrement=st.floats(min_value=0.01, max_value=0.1, allow_nan=False),
    )
    def test_divergence_detected(
        self,
        base_score: float,
        decrement: float,
    ) -> None:
        """If 3 consecutive alignment scores are strictly decreasing,
        the trend shall be "divergence".
        """
        # Feature: stakeholder-mapping, Property 27: Convergence and divergence trend detection
        from hypothesis import assume

        # Ensure all 3 scores stay within valid range [0, 1]
        assume(base_score - 2 * decrement >= 0.0)

        scores = [base_score, base_score - decrement, base_score - 2 * decrement]
        assert scores[0] > scores[1] > scores[2]  # strictly decreasing

        registry = StakeholderRegistry()
        tracker = DecisionCurveTracker(memory=object(), registry=registry)

        sid_a = "stakeholder-a"
        scenario = "travel"
        key = (sid_a, scenario)
        tracker._curves[key] = [
            DecisionCurvePoint(
                period=f"2026-01-0{i + 1}",
                actor=DecisionActor.USER,
                actor_id=sid_a,
                scenario=scenario,
                decision_count=i + 1,
                acceptance_rate=0.5,
                bias_count=0,
                alignment_score=scores[i],
                weight_stability=0.8,
            )
            for i in range(3)
        ]

        trend = tracker.detect_trends(sid_a, "stakeholder-b", scenario)
        assert trend == "divergence", (
            f"Expected 'divergence' for strictly decreasing scores "
            f"{scores}, got '{trend}'"
        )

# ---------------------------------------------------------------------------
# Shared strategies for migration helper property tests
# ---------------------------------------------------------------------------


@st.composite
def st_user_preferences(draw: st.DrawFn) -> UserPreferences:
    """Generate a valid UserPreferences object with random weights and confidence."""
    user_id = draw(st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True))
    scenario = draw(st.sampled_from(["travel", "career", "finance", "health"]))

    # Generate 1-4 unique dimension names with weights in [0, 1]
    dim_names = draw(
        st.lists(
            st.sampled_from(_DIMENSION_NAMES),
            min_size=1,
            max_size=4,
            unique=True,
        ),
    )
    weights = {
        dim: draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
        for dim in dim_names
    }
    confidence = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))

    return UserPreferences(
        user_id=user_id,
        scenario=scenario,
        weights=weights,
        confidence=confidence,
    )


@st.composite
def st_org_policy(draw: st.DrawFn) -> OrgPolicy:
    """Generate a valid OrgPolicy object with random weights and constraints."""
    org_id = draw(st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True))
    scenario = draw(st.sampled_from(["travel", "career", "finance", "health"]))

    # Generate 1-4 unique dimension names with weights in [0, 1]
    dim_names = draw(
        st.lists(
            st.sampled_from(_DIMENSION_NAMES),
            min_size=1,
            max_size=4,
            unique=True,
        ),
    )
    weights = {
        dim: draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
        for dim in dim_names
    }

    # Pick a subset of dimensions as constraints (0 to all)
    constraint_dims = draw(
        st.lists(
            st.sampled_from(dim_names),
            min_size=0,
            max_size=len(dim_names),
            unique=True,
        ),
    )
    constraints = {dim: True for dim in constraint_dims}

    return OrgPolicy(
        org_id=org_id,
        scenario=scenario,
        weights=weights,
        constraints=constraints,
    )


# ---------------------------------------------------------------------------
# Property 31: UserPreferences migration preserves weights
# Feature: stakeholder-mapping, Property 31: UserPreferences migration preserves weights
# ---------------------------------------------------------------------------


class TestProperty31UserPreferencesMigrationPreservesWeights:
    """**Validates: Requirements 9.1**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(prefs=st_user_preferences())
    def test_user_preferences_migration_preserves_weights(
        self, prefs: UserPreferences
    ) -> None:
        """For any valid UserPreferences object, from_user_preferences(prefs)
        shall produce a Stakeholder whose interest_dimensions dimension names
        match prefs.weights.keys() and whose influence weights are derived
        from prefs.confidence.
        """
        # Feature: stakeholder-mapping, Property 31: UserPreferences migration preserves weights
        registry = StakeholderRegistry()
        stakeholder = registry.from_user_preferences(prefs)

        # Dimension names must match prefs.weights.keys()
        stakeholder_dim_names = {
            dim.dimension for dim in stakeholder.interest_dimensions
        }
        expected_dim_names = set(prefs.weights.keys())
        assert stakeholder_dim_names == expected_dim_names, (
            f"Expected dimension names {expected_dim_names}, "
            f"got {stakeholder_dim_names}"
        )

        # Each interest dimension weight should match the corresponding prefs weight
        for dim in stakeholder.interest_dimensions:
            assert dim.weight == prefs.weights[dim.dimension], (
                f"Dimension '{dim.dimension}' weight {dim.weight} "
                f"does not match prefs weight {prefs.weights[dim.dimension]}"
            )
            # All directions should be higher_is_better per design
            assert dim.direction == PreferenceDirection.HIGHER_IS_BETTER, (
                f"Dimension '{dim.dimension}' direction should be "
                f"higher_is_better, got {dim.direction}"
            )

        # Influence weights should all equal prefs.confidence
        for dim_name, influence in stakeholder.influence_weights.items():
            assert influence == prefs.confidence, (
                f"Influence weight for '{dim_name}' is {influence}, "
                f"expected {prefs.confidence} (from confidence)"
            )

        # Influence weight keys should match dimension names
        assert set(stakeholder.influence_weights.keys()) == expected_dim_names


# ---------------------------------------------------------------------------
# Property 32: OrgPolicy migration preserves weights and constraints
# Feature: stakeholder-mapping, Property 32: OrgPolicy migration preserves weights and constraints
# ---------------------------------------------------------------------------


class TestProperty32OrgPolicyMigrationPreservesWeightsAndConstraints:
    """**Validates: Requirements 9.2**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(policy=st_org_policy())
    def test_org_policy_migration_preserves_weights_and_constraints(
        self, policy: OrgPolicy
    ) -> None:
        """For any valid OrgPolicy object, from_org_policy(policy) shall
        produce a Stakeholder whose interest_dimensions dimension names match
        policy.weights.keys() and whose constraint dimensions are marked as
        non-negotiable (lower_is_better direction).
        """
        # Feature: stakeholder-mapping, Property 32: OrgPolicy migration preserves weights and constraints
        registry = StakeholderRegistry()
        stakeholder = registry.from_org_policy(policy)

        # Dimension names must match policy.weights.keys()
        stakeholder_dim_names = {
            dim.dimension for dim in stakeholder.interest_dimensions
        }
        expected_dim_names = set(policy.weights.keys())
        assert stakeholder_dim_names == expected_dim_names, (
            f"Expected dimension names {expected_dim_names}, "
            f"got {stakeholder_dim_names}"
        )

        constraint_dims = set(policy.constraints.keys())

        for dim in stakeholder.interest_dimensions:
            if dim.dimension in constraint_dims:
                # Constraint dimensions should have lower_is_better direction
                assert dim.direction == PreferenceDirection.LOWER_IS_BETTER, (
                    f"Constraint dimension '{dim.dimension}' should have "
                    f"lower_is_better direction, got {dim.direction}"
                )
            else:
                # Non-constraint dimensions should have higher_is_better direction
                assert dim.direction == PreferenceDirection.HIGHER_IS_BETTER, (
                    f"Non-constraint dimension '{dim.dimension}' should have "
                    f"higher_is_better direction, got {dim.direction}"
                )

        # Influence weights should be derived from policy weights, clamped to [0, 1]
        for dim_name, influence in stakeholder.influence_weights.items():
            expected = max(0.0, min(1.0, policy.weights[dim_name]))
            assert influence == expected, (
                f"Influence weight for '{dim_name}' is {influence}, "
                f"expected {expected}"
            )


# ---------------------------------------------------------------------------
# Property 33: compute_alignment backward compatibility
# Feature: stakeholder-mapping, Property 33: compute_alignment backward compatibility
# ---------------------------------------------------------------------------
class TestProperty33ComputeAlignmentBackwardCompatibility:
    """**Validates: Requirements 9.3**"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        user_id=st.from_regex(r"[a-z][a-z0-9_-]{2,12}", fullmatch=True),
        policy=st_org_policy(),
    )
    def test_compute_alignment_backward_compatibility(
        self, user_id: str, policy: OrgPolicy
    ) -> None:
        """For any valid (user_id, org_policy) pair, calling
        PreferenceLearner.compute_alignment(user_id, org_policy) shall return
        an AlignmentReport with all existing fields populated (user_id,
        org_id, scenario, alignment_score, conflicts, synergies,
        negotiation_space).
        """
        # Feature: stakeholder-mapping, Property 33: compute_alignment backward compatibility
        tmp_dir = Path(mkdtemp())
        memory = DecisionMemory(base_dir=tmp_dir / "decisions")
        learner = PreferenceLearner(memory)

        report = learner.compute_alignment(user_id, policy)

        # Verify it's an AlignmentReport
        assert isinstance(report, AlignmentReport)

        # All required fields must be populated
        assert report.user_id == user_id
        assert report.org_id == policy.org_id
        assert report.scenario != ""
        assert 0.0 <= report.alignment_score <= 1.0
        assert isinstance(report.conflicts, list)
        assert isinstance(report.synergies, list)
        assert isinstance(report.negotiation_space, dict)
