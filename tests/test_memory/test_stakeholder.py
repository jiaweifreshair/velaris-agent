"""Unit tests for StakeholderRegistry CRUD operations.

Requirements: 1.1, 1.2, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5
"""

from __future__ import annotations

import pytest

from velaris_agent.memory.stakeholder import StakeholderRegistry
from velaris_agent.memory.types import (
    InterestDimension,
    PreferenceDirection,
    Stakeholder,
    StakeholderRole,
)


# ---------------------------------------------------------------------------
# Helpers
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


# ---------------------------------------------------------------------------
# Test: Register known stakeholder and verify fields (Req 1.1, 2.1)
# ---------------------------------------------------------------------------


class TestRegisterAndVerifyFields:
    """Register a known stakeholder and verify all fields are persisted."""

    def test_register_returns_id(self) -> None:
        registry = StakeholderRegistry()
        s = _make_stakeholder()
        sid = registry.register(s)
        assert sid == "user-alice"

    def test_register_and_get_preserves_fields(self) -> None:
        registry = StakeholderRegistry()
        s = _make_stakeholder()
        sid = registry.register(s)
        retrieved = registry.get(sid, "travel")

        assert retrieved is not None
        assert retrieved.stakeholder_id == "user-alice"
        assert retrieved.role == StakeholderRole.USER
        assert retrieved.display_name == "Alice"
        assert retrieved.scenario == "travel"
        assert len(retrieved.interest_dimensions) == 2
        assert retrieved.interest_dimensions[0].dimension == "cost"
        assert retrieved.interest_dimensions[0].direction == PreferenceDirection.LOWER_IS_BETTER
        assert retrieved.interest_dimensions[0].weight == 0.7
        assert retrieved.influence_weights == {"cost": 0.8, "quality": 0.6}
        assert retrieved.active is True
        assert retrieved.version == 1
        assert retrieved.created_at is not None
        assert retrieved.updated_at is not None

    def test_get_nonexistent_returns_none(self) -> None:
        registry = StakeholderRegistry()
        assert registry.get("no-such-id", "travel") is None


# ---------------------------------------------------------------------------
# Test: Relationship stakeholder with missing refs raises ValueError (Req 1.2)
# ---------------------------------------------------------------------------


class TestRelationshipStakeholderValidation:
    """Relationship stakeholders must reference exactly 2 existing stakeholders."""

    def test_relationship_with_zero_refs_raises(self) -> None:
        registry = StakeholderRegistry()
        rel = _make_stakeholder(
            stakeholder_id="rel-1",
            role=StakeholderRole.RELATIONSHIP,
            related_stakeholder_ids=[],
        )
        with pytest.raises(ValueError, match="exactly 2"):
            registry.register(rel)

    def test_relationship_with_one_ref_raises(self) -> None:
        registry = StakeholderRegistry()
        rel = _make_stakeholder(
            stakeholder_id="rel-1",
            role=StakeholderRole.RELATIONSHIP,
            related_stakeholder_ids=["user-alice"],
        )
        with pytest.raises(ValueError, match="exactly 2"):
            registry.register(rel)

    def test_relationship_with_three_refs_raises(self) -> None:
        registry = StakeholderRegistry()
        rel = _make_stakeholder(
            stakeholder_id="rel-1",
            role=StakeholderRole.RELATIONSHIP,
            related_stakeholder_ids=["a", "b", "c"],
        )
        with pytest.raises(ValueError, match="exactly 2"):
            registry.register(rel)

    def test_relationship_with_nonexistent_refs_raises(self) -> None:
        registry = StakeholderRegistry()
        rel = _make_stakeholder(
            stakeholder_id="rel-1",
            role=StakeholderRole.RELATIONSHIP,
            related_stakeholder_ids=["ghost-a", "ghost-b"],
        )
        with pytest.raises(ValueError, match="not found"):
            registry.register(rel)

    def test_relationship_with_valid_refs_succeeds(self) -> None:
        registry = StakeholderRegistry()
        user = _make_stakeholder(stakeholder_id="user-alice", role=StakeholderRole.USER)
        org = _make_stakeholder(stakeholder_id="org-acme", role=StakeholderRole.ORG, display_name="Acme")
        registry.register(user)
        registry.register(org)

        rel = _make_stakeholder(
            stakeholder_id="rel-alice-acme",
            role=StakeholderRole.RELATIONSHIP,
            display_name="Alice-Acme",
            related_stakeholder_ids=["user-alice", "org-acme"],
        )
        sid = registry.register(rel)
        assert sid == "rel-alice-acme"


# ---------------------------------------------------------------------------
# Test: Duplicate id+scenario raises ValueError (Req 1.5)
# ---------------------------------------------------------------------------


class TestDuplicateRejection:
    """Registering the same id+scenario twice must raise ValueError."""

    def test_duplicate_raises_value_error(self) -> None:
        registry = StakeholderRegistry()
        s = _make_stakeholder()
        registry.register(s)

        duplicate = _make_stakeholder(display_name="Alice Clone")
        with pytest.raises(ValueError, match="already registered"):
            registry.register(duplicate)

    def test_same_id_different_scenario_ok(self) -> None:
        registry = StakeholderRegistry()
        s1 = _make_stakeholder(scenario="travel")
        s2 = _make_stakeholder(scenario="career")
        registry.register(s1)
        sid = registry.register(s2)
        assert sid == "user-alice"


# ---------------------------------------------------------------------------
# Test: Update increments version (Req 2.2)
# ---------------------------------------------------------------------------


class TestUpdateIncrementsVersion:
    """update() must bump version and merge fields."""

    def test_update_increments_version(self) -> None:
        registry = StakeholderRegistry()
        s = _make_stakeholder(version=1)
        registry.register(s)

        updated = registry.update("user-alice", "travel", display_name="Alice Updated")
        assert updated.version == 2
        assert updated.display_name == "Alice Updated"
        assert updated.updated_at is not None

    def test_update_preserves_unchanged_fields(self) -> None:
        registry = StakeholderRegistry()
        s = _make_stakeholder()
        registry.register(s)

        updated = registry.update("user-alice", "travel", display_name="New Name")
        assert updated.role == StakeholderRole.USER
        assert updated.scenario == "travel"
        assert updated.interest_dimensions == s.interest_dimensions
        assert updated.influence_weights == s.influence_weights

    def test_update_nonexistent_raises_key_error(self) -> None:
        registry = StakeholderRegistry()
        with pytest.raises(KeyError):
            registry.update("no-such-id", "travel", display_name="X")

    def test_multiple_updates_increment_version_sequentially(self) -> None:
        registry = StakeholderRegistry()
        s = _make_stakeholder(version=1)
        registry.register(s)

        registry.update("user-alice", "travel", display_name="V2")
        updated = registry.update("user-alice", "travel", display_name="V3")
        assert updated.version == 3


# ---------------------------------------------------------------------------
# Test: Remove sets active=False (Req 2.3)
# ---------------------------------------------------------------------------


class TestRemoveSoftDelete:
    """remove() must soft-delete by setting active=False."""

    def test_remove_sets_active_false(self) -> None:
        registry = StakeholderRegistry()
        s = _make_stakeholder()
        registry.register(s)

        registry.remove("user-alice", "travel")
        retrieved = registry.get("user-alice", "travel")
        assert retrieved is not None
        assert retrieved.active is False

    def test_remove_preserves_record(self) -> None:
        registry = StakeholderRegistry()
        s = _make_stakeholder()
        registry.register(s)

        registry.remove("user-alice", "travel")
        retrieved = registry.get("user-alice", "travel")
        assert retrieved is not None
        assert retrieved.stakeholder_id == "user-alice"
        assert retrieved.display_name == "Alice"

    def test_remove_nonexistent_raises_key_error(self) -> None:
        registry = StakeholderRegistry()
        with pytest.raises(KeyError):
            registry.remove("no-such-id", "travel")

    def test_remove_in_active_map_raises_value_error(self) -> None:
        """Req 2.5: cannot remove a stakeholder referenced by an active map."""
        registry = StakeholderRegistry()
        s = _make_stakeholder()
        registry.register(s)
        registry.mark_in_map("user-alice", "travel")

        with pytest.raises(ValueError, match="still referenced"):
            registry.remove("user-alice", "travel")

        # Verify still active
        retrieved = registry.get("user-alice", "travel")
        assert retrieved is not None
        assert retrieved.active is True


# ---------------------------------------------------------------------------
# Test: list_active filters by scenario and role (Req 2.4)
# ---------------------------------------------------------------------------


class TestListActiveFiltering:
    """list_active() must filter by scenario, role, and active status."""

    def _setup_registry(self) -> StakeholderRegistry:
        registry = StakeholderRegistry()
        registry.register(_make_stakeholder(
            stakeholder_id="user-alice", role=StakeholderRole.USER, scenario="travel",
        ))
        registry.register(_make_stakeholder(
            stakeholder_id="org-acme", role=StakeholderRole.ORG,
            display_name="Acme", scenario="travel",
        ))
        registry.register(_make_stakeholder(
            stakeholder_id="user-bob", role=StakeholderRole.USER,
            display_name="Bob", scenario="career",
        ))
        registry.register(_make_stakeholder(
            stakeholder_id="org-beta", role=StakeholderRole.ORG,
            display_name="Beta", scenario="career",
        ))
        # Soft-delete one
        registry.remove("org-beta", "career")
        return registry

    def test_filter_by_scenario(self) -> None:
        registry = self._setup_registry()
        result = registry.list_active("travel")
        assert len(result) == 2
        ids = {s.stakeholder_id for s in result}
        assert ids == {"user-alice", "org-acme"}

    def test_filter_by_scenario_and_role(self) -> None:
        registry = self._setup_registry()
        result = registry.list_active("travel", role=StakeholderRole.USER)
        assert len(result) == 1
        assert result[0].stakeholder_id == "user-alice"

    def test_filter_excludes_inactive(self) -> None:
        registry = self._setup_registry()
        result = registry.list_active("career")
        assert len(result) == 1
        assert result[0].stakeholder_id == "user-bob"

    def test_filter_empty_scenario(self) -> None:
        registry = self._setup_registry()
        result = registry.list_active("nonexistent")
        assert result == []

    def test_filter_role_with_no_matches(self) -> None:
        registry = self._setup_registry()
        result = registry.list_active("career", role=StakeholderRole.ORG)
        assert result == []


# ---------------------------------------------------------------------------
# Test: from_user_preferences and from_org_policy (Req 9.1, 9.2)
# ---------------------------------------------------------------------------


class TestFromUserPreferences:
    """Tests for StakeholderRegistry.from_user_preferences()."""

    def test_returns_stakeholder_with_user_role(self) -> None:
        from velaris_agent.memory.types import UserPreferences

        registry = StakeholderRegistry()
        prefs = UserPreferences(
            user_id="u1",
            scenario="travel",
            weights={"cost": 0.7, "quality": 0.5},
            confidence=0.8,
        )
        s = registry.from_user_preferences(prefs)
        assert s.role == StakeholderRole.USER

    def test_maps_weights_to_interest_dimensions(self) -> None:
        from velaris_agent.memory.types import UserPreferences

        registry = StakeholderRegistry()
        prefs = UserPreferences(
            user_id="u1",
            scenario="travel",
            weights={"cost": 0.7, "quality": 0.5},
            confidence=0.6,
        )
        s = registry.from_user_preferences(prefs)
        dim_names = {d.dimension for d in s.interest_dimensions}
        assert dim_names == {"cost", "quality"}
        for d in s.interest_dimensions:
            assert d.direction == PreferenceDirection.HIGHER_IS_BETTER

    def test_maps_confidence_to_uniform_influence(self) -> None:
        from velaris_agent.memory.types import UserPreferences

        registry = StakeholderRegistry()
        prefs = UserPreferences(
            user_id="u1",
            scenario="travel",
            weights={"cost": 0.7, "quality": 0.5},
            confidence=0.9,
        )
        s = registry.from_user_preferences(prefs)
        assert s.influence_weights == {"cost": 0.9, "quality": 0.9}

    def test_preserves_user_id_and_scenario(self) -> None:
        from velaris_agent.memory.types import UserPreferences

        registry = StakeholderRegistry()
        prefs = UserPreferences(
            user_id="alice",
            scenario="career",
            weights={"growth": 0.8},
            confidence=0.5,
        )
        s = registry.from_user_preferences(prefs)
        assert s.stakeholder_id == "alice"
        assert s.scenario == "career"

    def test_does_not_register_stakeholder(self) -> None:
        from velaris_agent.memory.types import UserPreferences

        registry = StakeholderRegistry()
        prefs = UserPreferences(
            user_id="u1",
            scenario="travel",
            weights={"cost": 0.7},
            confidence=0.5,
        )
        registry.from_user_preferences(prefs)
        assert registry.get("u1", "travel") is None


class TestFromOrgPolicy:
    """Tests for StakeholderRegistry.from_org_policy()."""

    def test_returns_stakeholder_with_org_role(self) -> None:
        from velaris_agent.memory.types import OrgPolicy

        registry = StakeholderRegistry()
        policy = OrgPolicy(
            org_id="acme",
            scenario="travel",
            weights={"compliance": 0.5, "cost": 0.3},
        )
        s = registry.from_org_policy(policy)
        assert s.role == StakeholderRole.ORG

    def test_maps_weights_to_interest_dimensions(self) -> None:
        from velaris_agent.memory.types import OrgPolicy

        registry = StakeholderRegistry()
        policy = OrgPolicy(
            org_id="acme",
            scenario="travel",
            weights={"compliance": 0.5, "cost": 0.3},
        )
        s = registry.from_org_policy(policy)
        dim_names = {d.dimension for d in s.interest_dimensions}
        assert dim_names == {"compliance", "cost"}

    def test_constraint_dims_get_lower_is_better(self) -> None:
        from velaris_agent.memory.types import OrgPolicy

        registry = StakeholderRegistry()
        policy = OrgPolicy(
            org_id="acme",
            scenario="travel",
            weights={"compliance": 0.5, "cost": 0.3},
            constraints={"cost": 5000},
        )
        s = registry.from_org_policy(policy)
        dim_map = {d.dimension: d.direction for d in s.interest_dimensions}
        assert dim_map["cost"] == PreferenceDirection.LOWER_IS_BETTER
        assert dim_map["compliance"] == PreferenceDirection.HIGHER_IS_BETTER

    def test_influence_weights_from_policy_weights(self) -> None:
        from velaris_agent.memory.types import OrgPolicy

        registry = StakeholderRegistry()
        policy = OrgPolicy(
            org_id="acme",
            scenario="travel",
            weights={"compliance": 0.5, "cost": 0.3},
        )
        s = registry.from_org_policy(policy)
        assert s.influence_weights == {"compliance": 0.5, "cost": 0.3}

    def test_preserves_org_id_and_scenario(self) -> None:
        from velaris_agent.memory.types import OrgPolicy

        registry = StakeholderRegistry()
        policy = OrgPolicy(
            org_id="acme-corp",
            scenario="career",
            weights={"growth": 0.8},
        )
        s = registry.from_org_policy(policy)
        assert s.stakeholder_id == "acme-corp"
        assert s.scenario == "career"

    def test_does_not_register_stakeholder(self) -> None:
        from velaris_agent.memory.types import OrgPolicy

        registry = StakeholderRegistry()
        policy = OrgPolicy(
            org_id="acme",
            scenario="travel",
            weights={"cost": 0.3},
        )
        registry.from_org_policy(policy)
        assert registry.get("acme", "travel") is None
