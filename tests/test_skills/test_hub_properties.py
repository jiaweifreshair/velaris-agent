"""Property-based tests for hub.py using Hypothesis.

Tests cover:
- Property 1: Search result deduplication
- Property 2: Content hash consistency
- Property 3: Source fault tolerance
- Property 6: Duplicate install rejection
- Property 7: Hash change detection
- Property 13: Audit log append
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from openharness.skills.hub import (
    SkillBundle,
    SkillMeta,
    SkillSource,
    append_audit_log,
    bundle_content_hash,
    check_for_skill_updates,
    install_skill,
    parallel_search_sources,
)
from openharness.skills.lock import HubLockFile, LockEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSource(SkillSource):
    """A configurable fake SkillSource for property tests."""

    def __init__(
        self,
        sid: str = "fake",
        search_results: list[SkillMeta] | None = None,
        fetch_bundle: SkillBundle | None = None,
        fetch_error: Exception | None = None,
        search_error: Exception | None = None,
    ) -> None:
        self._sid = sid
        self._search_results = search_results or []
        self._fetch_bundle = fetch_bundle
        self._fetch_error = fetch_error
        self._search_error = search_error

    def source_id(self) -> str:
        return self._sid

    def trust_level_for(self, identifier: str) -> str:
        return "community"

    async def search(self, query: str) -> list[SkillMeta]:
        if self._search_error:
            raise self._search_error
        return self._search_results

    async def fetch(self, identifier: str) -> SkillBundle:
        if self._fetch_error:
            raise self._fetch_error
        if self._fetch_bundle is None:
            raise RuntimeError(f"No bundle for {identifier}")
        return self._fetch_bundle


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid skill name: starts with alnum, then alnum/dot/dash/underscore
_skill_name_st = st.from_regex(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,30}", fullmatch=True)

# Valid identifier: "source/name" style
_identifier_st = st.builds(
    lambda prefix, name: f"{prefix}/{name}",
    st.sampled_from(["github", "optional", "tap"]),
    _skill_name_st,
)

_trust_level_st = st.sampled_from(["builtin", "trusted", "community"])

_skill_meta_st = st.builds(
    SkillMeta,
    name=_skill_name_st,
    description=st.text(min_size=1, max_size=50),
    source=st.sampled_from(["github", "optional", "tap:org/repo"]),
    identifier=_identifier_st,
    trust_level=_trust_level_st,
)

# File path segments: simple safe names
_safe_path_segment = st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,15}", fullmatch=True)
_file_path_st = st.builds(
    lambda parts: "/".join(parts),
    st.lists(_safe_path_segment, min_size=1, max_size=3),
)

# Files dict: path -> content (non-empty)
_files_dict_st = st.dictionaries(
    keys=_file_path_st,
    values=st.text(min_size=1, max_size=200),
    min_size=1,
    max_size=5,
)


# ---------------------------------------------------------------------------
# Property 1: Search result deduplication
# Feature: skill-self-update, Property 1: Search result deduplication
# ---------------------------------------------------------------------------


class TestProperty1SearchDeduplication:
    """**Validates: Requirements 1.3**"""

    @settings(max_examples=100)
    @given(
        metas=st.lists(_skill_meta_st, min_size=0, max_size=20),
        num_sources=st.integers(min_value=1, max_value=4),
    )
    async def test_no_duplicate_identifiers_after_merge(
        self, metas: list[SkillMeta], num_sources: int
    ) -> None:
        # Feature: skill-self-update, Property 1: Search result deduplication
        # Distribute metas across sources (with overlap to create duplicates)
        sources: list[SkillSource] = []
        for i in range(num_sources):
            # Each source gets a subset of metas, creating potential duplicates
            subset = [m for j, m in enumerate(metas) if j % num_sources <= i]
            sources.append(_FakeSource(sid=f"src-{i}", search_results=subset))

        results = await parallel_search_sources("", sources)

        # Verify: no duplicate identifiers
        identifiers = [r.identifier for r in results]
        assert len(identifiers) == len(set(identifiers)), (
            f"Duplicate identifiers found: {identifiers}"
        )


# ---------------------------------------------------------------------------
# Property 2: Content hash consistency
# Feature: skill-self-update, Property 2: Content hash consistency
# ---------------------------------------------------------------------------


class TestProperty2ContentHashConsistency:
    """**Validates: Requirements 1.4**"""

    @settings(max_examples=100)
    @given(files=_files_dict_st)
    def test_bundle_hash_matches_recomputed_hash(
        self, files: dict[str, str]
    ) -> None:
        # Feature: skill-self-update, Property 2: Content hash consistency
        computed_hash = bundle_content_hash(files)
        bundle = SkillBundle(
            name="test",
            files=files,
            source="optional",
            identifier="optional/test",
            trust_level="builtin",
            content_hash=computed_hash,
        )
        # Recompute from bundle.files and verify consistency
        assert bundle.content_hash == bundle_content_hash(bundle.files)


# ---------------------------------------------------------------------------
# Property 3: Source fault tolerance
# Feature: skill-self-update, Property 3: Source fault tolerance
# ---------------------------------------------------------------------------


class TestProperty3SourceFaultTolerance:
    """**Validates: Requirements 1.5, 3.6**"""

    @settings(max_examples=100)
    @given(
        good_metas=st.lists(_skill_meta_st, min_size=0, max_size=10),
        num_good=st.integers(min_value=1, max_value=3),
        num_bad=st.integers(min_value=1, max_value=3),
    )
    async def test_failing_sources_do_not_block_results(
        self,
        good_metas: list[SkillMeta],
        num_good: int,
        num_bad: int,
    ) -> None:
        # Feature: skill-self-update, Property 3: Source fault tolerance
        # Deduplicate metas by identifier for predictable expected count
        unique_metas: dict[str, SkillMeta] = {}
        for m in good_metas:
            if m.identifier not in unique_metas:
                unique_metas[m.identifier] = m
        deduped = list(unique_metas.values())

        sources: list[SkillSource] = []
        # Good sources all return the same deduped list
        for i in range(num_good):
            sources.append(_FakeSource(sid=f"good-{i}", search_results=deduped))
        # Bad sources raise exceptions
        for i in range(num_bad):
            sources.append(
                _FakeSource(
                    sid=f"bad-{i}",
                    search_error=RuntimeError(f"source {i} down"),
                )
            )

        results = await parallel_search_sources("", sources)

        # All unique metas from good sources should be present
        result_ids = {r.identifier for r in results}
        expected_ids = {m.identifier for m in deduped}
        assert expected_ids == result_ids
        # No exception should have propagated


# ---------------------------------------------------------------------------
# Property 6: Duplicate install rejection
# Feature: skill-self-update, Property 6: Duplicate install rejection
# ---------------------------------------------------------------------------


class TestProperty6DuplicateInstallRejection:
    """**Validates: Requirements 2.6**"""

    @settings(max_examples=100)
    @given(skill_name=_skill_name_st)
    async def test_force_false_rejects_already_installed(
        self, skill_name: str, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        # Feature: skill-self-update, Property 6: Duplicate install rejection
        tmp_path = tmp_path_factory.mktemp("prop6")
        lock_path = tmp_path / "lock.json"
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        # Pre-install the skill in the lock file
        lock = HubLockFile(lock_path)
        entry = LockEntry(
            name=skill_name,
            source="optional",
            identifier=f"optional/{skill_name}",
            trust_level="builtin",
            content_hash="sha256:existing",
            install_path=str(skills_dir / skill_name),
            files=["SKILL.md"],
            installed_at="2025-01-01T00:00:00Z",
        )
        lock.record_install(entry)

        # Snapshot lock file content before attempted install
        lock_before = lock_path.read_text(encoding="utf-8")

        # Create a fake source that would provide the bundle
        files = {"SKILL.md": "# Test"}
        bundle = SkillBundle(
            name=skill_name,
            files=files,
            source="optional",
            identifier=f"optional/{skill_name}",
            trust_level="builtin",
            content_hash=bundle_content_hash(files),
        )
        source = _FakeSource(fetch_bundle=bundle)

        with (
            patch("openharness.skills.hub.get_user_skills_dir", return_value=skills_dir),
            patch("openharness.config.paths.get_config_dir", return_value=tmp_path),
            patch(
                "openharness.skills.hub.HubLockFile",
                return_value=HubLockFile(lock_path),
            ),
        ):
            with pytest.raises(RuntimeError, match="already installed"):
                await install_skill(
                    f"optional/{skill_name}", [source], force=False
                )

        # Lock file should be unchanged
        lock_after = lock_path.read_text(encoding="utf-8")
        assert lock_before == lock_after


# ---------------------------------------------------------------------------
# Property 7: Hash change detection
# Feature: skill-self-update, Property 7: Hash change detection
# ---------------------------------------------------------------------------


class TestProperty7HashChangeDetection:
    """**Validates: Requirements 3.3**"""

    @settings(max_examples=100)
    @given(
        skill_name=_skill_name_st,
        local_content=st.text(min_size=1, max_size=100),
        remote_content=st.text(min_size=1, max_size=100),
    )
    async def test_detects_update_iff_hash_differs(
        self,
        skill_name: str,
        local_content: str,
        remote_content: str,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        # Feature: skill-self-update, Property 7: Hash change detection
        tmp_path = tmp_path_factory.mktemp("prop7")
        lock_path = tmp_path / "lock.json"

        local_files = {"SKILL.md": local_content}
        local_hash = bundle_content_hash(local_files)

        remote_files = {"SKILL.md": remote_content}
        remote_hash = bundle_content_hash(remote_files)

        identifier = f"optional/{skill_name}"

        # Set up lock file with local hash
        lock = HubLockFile(lock_path)
        lock.record_install(
            LockEntry(
                name=skill_name,
                source="optional",
                identifier=identifier,
                trust_level="builtin",
                content_hash=local_hash,
                install_path=str(tmp_path / skill_name),
                files=["SKILL.md"],
                installed_at="2025-01-01T00:00:00Z",
            )
        )

        # Create source returning remote bundle
        remote_bundle = SkillBundle(
            name=skill_name,
            files=remote_files,
            source="optional",
            identifier=identifier,
            trust_level="builtin",
            content_hash=remote_hash,
        )
        source = _FakeSource(fetch_bundle=remote_bundle)

        with patch(
            "openharness.skills.hub.HubLockFile",
            return_value=HubLockFile(lock_path),
        ):
            updates = await check_for_skill_updates([source])

        hashes_differ = local_hash != remote_hash

        if hashes_differ:
            assert len(updates) == 1
            assert updates[0]["name"] == skill_name
            assert updates[0]["current_hash"] == local_hash
            assert updates[0]["latest_hash"] == remote_hash
        else:
            assert len(updates) == 0


# ---------------------------------------------------------------------------
# Property 13: Audit log append
# Feature: skill-self-update, Property 13: Audit log append
# ---------------------------------------------------------------------------


class TestProperty13AuditLogAppend:
    """**Validates: Requirements 7.5**"""

    @settings(max_examples=100)
    @given(
        operations=st.lists(
            st.tuples(
                st.sampled_from(["install", "uninstall", "update"]),
                _skill_name_st,
            ),
            min_size=1,
            max_size=10,
        )
    )
    def test_each_operation_appends_log_entry(
        self,
        operations: list[tuple[str, str]],
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        # Feature: skill-self-update, Property 13: Audit log append
        tmp_path = tmp_path_factory.mktemp("prop13")
        skills_dir = tmp_path / "skills"

        with (
            patch("openharness.skills.hub.get_user_skills_dir", return_value=skills_dir),
            patch("openharness.config.paths.get_config_dir", return_value=tmp_path),
        ):
            for action, skill_name in operations:
                append_audit_log(
                    action=action,
                    skill_name=skill_name,
                    details={"source": "test"},
                )

        log_path = tmp_path / "audit" / "skills-audit.log"
        assert log_path.exists()

        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == len(operations)

        for i, (expected_action, expected_name) in enumerate(operations):
            record = json.loads(lines[i])
            assert record["action"] == expected_action
            assert record["skill"] == expected_name
            assert "timestamp" in record
            # Timestamp should be a non-empty ISO format string
            assert len(record["timestamp"]) > 0
