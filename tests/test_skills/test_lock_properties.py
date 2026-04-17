"""Property-based tests for lock.py using Hypothesis.

Tests cover:
- Property 5: Post-install lock file integrity
- Property 8: Post-update lock file refresh
- Property 9: Uninstall cleanup
- Property 10: Tap removal
- Property 11: Tap address format validation
- Property 16: Lock file round-trip consistency
- Property 17: Invalid JSON error handling
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from openharness.skills.lock import HubLockFile, LockEntry, TapsManager


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid skill name: starts with alnum, then alnum/dot/dash/underscore
_skill_name_st = st.from_regex(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,30}", fullmatch=True)

_source_st = st.sampled_from(["github", "optional", "tap:org/repo"])

_trust_level_st = st.sampled_from(["builtin", "trusted", "community"])

_hex_str_st = st.from_regex(r"[0-9a-f]{16,64}", fullmatch=True)

_content_hash_st = st.builds(lambda h: f"sha256:{h}", _hex_str_st)

_safe_path_segment = st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,15}", fullmatch=True)

_file_path_st = st.builds(
    lambda parts: "/".join(parts),
    st.lists(_safe_path_segment, min_size=1, max_size=3),
)

_iso_timestamp_st = st.builds(
    lambda y, mo, d, h, mi, s: f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}Z",
    st.integers(min_value=2020, max_value=2030),
    st.integers(min_value=1, max_value=12),
    st.integers(min_value=1, max_value=28),
    st.integers(min_value=0, max_value=23),
    st.integers(min_value=0, max_value=59),
    st.integers(min_value=0, max_value=59),
)

_lock_entry_st = st.builds(
    LockEntry,
    name=_skill_name_st,
    source=_source_st,
    identifier=st.builds(
        lambda src, name: f"{src}/{name}",
        st.sampled_from(["github", "optional", "tap:org/repo"]),
        _skill_name_st,
    ),
    trust_level=_trust_level_st,
    content_hash=_content_hash_st,
    install_path=st.builds(lambda n: f"/tmp/skills/{n}", _skill_name_st),
    files=st.lists(_file_path_st, min_size=1, max_size=5),
    installed_at=_iso_timestamp_st,
    updated_at=st.one_of(st.none(), _iso_timestamp_st),
)

# Valid owner/repo tap format
_valid_tap_st = st.builds(
    lambda owner, repo: f"{owner}/{repo}",
    st.from_regex(r"[A-Za-z0-9][A-Za-z0-9._-]{0,15}", fullmatch=True),
    st.from_regex(r"[A-Za-z0-9][A-Za-z0-9._-]{0,15}", fullmatch=True),
)


# ---------------------------------------------------------------------------
# Property 5: Post-install lock file integrity
# Feature: skill-self-update, Property 5: Post-install lock file integrity
# ---------------------------------------------------------------------------


class TestProperty5PostInstallLockFileIntegrity:
    """**Validates: Requirements 2.5, 4.2**"""

    @settings(max_examples=100)
    @given(entry=_lock_entry_st)
    def test_record_install_then_get_returns_complete_record(
        self,
        entry: LockEntry,
        tmp_path_factory: "pytest.TempPathFactory",
    ) -> None:
        # Feature: skill-self-update, Property 5: Post-install lock file integrity
        tmp_path = tmp_path_factory.mktemp("prop5")
        lock = HubLockFile(tmp_path / "lock.json")

        lock.record_install(entry)
        result = lock.get_installed(entry.name)

        assert result is not None
        assert result.name == entry.name
        assert result.source == entry.source
        assert result.identifier == entry.identifier
        assert result.trust_level == entry.trust_level
        assert result.content_hash == entry.content_hash
        assert result.install_path == entry.install_path
        assert result.files == entry.files
        assert result.installed_at == entry.installed_at
        assert result.updated_at == entry.updated_at


# ---------------------------------------------------------------------------
# Property 8: Post-update lock file refresh
# Feature: skill-self-update, Property 8: Post-update lock file refresh
# ---------------------------------------------------------------------------


class TestProperty8PostUpdateLockFileRefresh:
    """**Validates: Requirements 3.5**"""

    @settings(max_examples=100)
    @given(
        entry=_lock_entry_st,
        new_hash=_content_hash_st,
        update_ts=_iso_timestamp_st,
    )
    def test_update_refreshes_hash_and_updated_at(
        self,
        entry: LockEntry,
        new_hash: str,
        update_ts: str,
        tmp_path_factory: "pytest.TempPathFactory",
    ) -> None:
        # Feature: skill-self-update, Property 8: Post-update lock file refresh
        tmp_path = tmp_path_factory.mktemp("prop8")
        lock = HubLockFile(tmp_path / "lock.json")

        # Install original entry
        lock.record_install(entry)

        # Simulate update: create updated entry with new hash and updated_at
        updated_entry = entry.model_copy(
            update={"content_hash": new_hash, "updated_at": update_ts}
        )
        lock.record_install(updated_entry)

        result = lock.get_installed(entry.name)
        assert result is not None
        assert result.content_hash == new_hash
        assert result.updated_at is not None
        assert result.updated_at == update_ts
        assert len(result.updated_at) > 0


# ---------------------------------------------------------------------------
# Property 9: Uninstall cleanup
# Feature: skill-self-update, Property 9: Uninstall cleanup
# ---------------------------------------------------------------------------


class TestProperty9UninstallCleanup:
    """**Validates: Requirements 4.3**"""

    @settings(max_examples=100)
    @given(
        entries=st.lists(_lock_entry_st, min_size=1, max_size=10),
    )
    def test_uninstall_removes_skill_from_lock(
        self,
        entries: list[LockEntry],
        tmp_path_factory: "pytest.TempPathFactory",
    ) -> None:
        # Feature: skill-self-update, Property 9: Uninstall cleanup
        tmp_path = tmp_path_factory.mktemp("prop9")
        lock = HubLockFile(tmp_path / "lock.json")

        # Deduplicate by name to avoid overwriting
        unique: dict[str, LockEntry] = {}
        for e in entries:
            unique[e.name] = e
        entries_list = list(unique.values())

        # Install all
        for e in entries_list:
            lock.record_install(e)

        # Pick the first one to uninstall
        target = entries_list[0]
        lock.record_uninstall(target.name)

        # Verify it's gone
        assert lock.get_installed(target.name) is None

        # Verify others remain
        for e in entries_list[1:]:
            assert lock.get_installed(e.name) is not None


# ---------------------------------------------------------------------------
# Property 10: Tap removal
# Feature: skill-self-update, Property 10: Tap removal
# ---------------------------------------------------------------------------


class TestProperty10TapRemoval:
    """**Validates: Requirements 5.3**"""

    @settings(max_examples=100)
    @given(
        taps=st.lists(_valid_tap_st, min_size=1, max_size=10, unique=True),
    )
    def test_remove_tap_not_in_list(
        self,
        taps: list[str],
        tmp_path_factory: "pytest.TempPathFactory",
    ) -> None:
        # Feature: skill-self-update, Property 10: Tap removal
        tmp_path = tmp_path_factory.mktemp("prop10")
        mgr = TapsManager(tmp_path / "taps.json")

        # Add all taps
        for repo in taps:
            mgr.add(repo)

        # Pick the first one to remove
        target = taps[0]
        mgr.remove(target)

        # Verify it's gone
        remaining_repos = [t["repo"] for t in mgr.list_taps()]
        assert target not in remaining_repos

        # Verify others remain
        for repo in taps[1:]:
            assert repo in remaining_repos


# ---------------------------------------------------------------------------
# Property 11: Tap address format validation
# Feature: skill-self-update, Property 11: Tap address format validation
# ---------------------------------------------------------------------------

# Strategies for invalid tap addresses
_invalid_tap_st = st.one_of(
    # Empty string
    st.just(""),
    # No slash
    st.from_regex(r"[a-zA-Z0-9]{1,20}", fullmatch=True),
    # Contains spaces
    st.builds(lambda a, b: f"{a} {b}/{a}", st.from_regex(r"[a-z]{1,5}", fullmatch=True), st.from_regex(r"[a-z]{1,5}", fullmatch=True)),
    # Special characters (!, @, #, $, etc.)
    st.builds(
        lambda c, name: f"{c}{name}/repo",
        st.sampled_from(["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"]),
        st.from_regex(r"[a-z]{1,5}", fullmatch=True),
    ),
    # Triple segment (a/b/c)
    st.builds(
        lambda a, b, c: f"{a}/{b}/{c}",
        st.from_regex(r"[a-z]{1,5}", fullmatch=True),
        st.from_regex(r"[a-z]{1,5}", fullmatch=True),
        st.from_regex(r"[a-z]{1,5}", fullmatch=True),
    ),
    # Leading slash
    st.builds(lambda n: f"/{n}", st.from_regex(r"[a-z]{1,10}", fullmatch=True)),
    # Trailing slash
    st.builds(lambda n: f"{n}/", st.from_regex(r"[a-z]{1,10}", fullmatch=True)),
)


class TestProperty11TapAddressFormatValidation:
    """**Validates: Requirements 5.5**"""

    @settings(max_examples=100)
    @given(invalid_repo=_invalid_tap_st)
    def test_invalid_format_raises_value_error(
        self,
        invalid_repo: str,
        tmp_path_factory: "pytest.TempPathFactory",
    ) -> None:
        # Feature: skill-self-update, Property 11: Tap address format validation
        import pytest

        tmp_path = tmp_path_factory.mktemp("prop11")
        mgr = TapsManager(tmp_path / "taps.json")

        with pytest.raises(ValueError):
            mgr.add(invalid_repo)


# ---------------------------------------------------------------------------
# Property 16: Lock file round-trip consistency
# Feature: skill-self-update, Property 16: Lock file round-trip consistency
# ---------------------------------------------------------------------------


class TestProperty16LockFileRoundTripConsistency:
    """**Validates: Requirements 12.2**"""

    @settings(max_examples=100)
    @given(
        entries=st.dictionaries(
            keys=_skill_name_st,
            values=_lock_entry_st,
            min_size=0,
            max_size=10,
        ),
    )
    def test_save_then_load_produces_equivalent_data(
        self,
        entries: dict[str, LockEntry],
        tmp_path_factory: "pytest.TempPathFactory",
    ) -> None:
        # Feature: skill-self-update, Property 16: Lock file round-trip consistency
        tmp_path = tmp_path_factory.mktemp("prop16")
        lock = HubLockFile(tmp_path / "lock.json")

        # Align dict keys with entry names for consistency
        aligned: dict[str, LockEntry] = {}
        for key, entry in entries.items():
            aligned[key] = entry.model_copy(update={"name": key})

        lock.save(aligned)
        loaded = lock.load()

        assert len(loaded) == len(aligned)
        for key, original in aligned.items():
            assert key in loaded
            assert loaded[key] == original


# ---------------------------------------------------------------------------
# Property 17: Invalid JSON error handling
# Feature: skill-self-update, Property 17: Invalid JSON error handling
# ---------------------------------------------------------------------------

# Strategies for non-JSON strings
_non_json_st = st.one_of(
    # Random text that isn't valid JSON
    st.text(min_size=1, max_size=200).filter(lambda s: _is_not_json(s)),
    # Partial JSON
    st.just("{incomplete"),
    st.just("[1, 2,"),
    st.just("{'single': 'quotes'}"),
    # Random bytes-like strings
    st.from_regex(r"[^{}\[\]\"0-9tfn][a-zA-Z0-9!@#$%^&*]{1,50}", fullmatch=True),
)


def _is_not_json(s: str) -> bool:
    """Return True if *s* is not valid JSON."""
    import json

    try:
        json.loads(s)
        return False
    except (json.JSONDecodeError, ValueError):
        return True


class TestProperty17InvalidJsonErrorHandling:
    """**Validates: Requirements 12.3, 4.5**"""

    @settings(max_examples=100)
    @given(bad_content=_non_json_st)
    def test_invalid_json_returns_empty_dict(
        self,
        bad_content: str,
        tmp_path_factory: "pytest.TempPathFactory",
    ) -> None:
        # Feature: skill-self-update, Property 17: Invalid JSON error handling
        tmp_path = tmp_path_factory.mktemp("prop17")
        lock_path = tmp_path / "lock.json"
        lock_path.write_text(bad_content, encoding="utf-8")

        lock = HubLockFile(lock_path)
        result = lock.load()

        assert result == {}
