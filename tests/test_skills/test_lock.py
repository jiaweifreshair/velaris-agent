"""Unit tests for LockEntry / HubLockFile.

Covers:
- load/save round-trip consistency  (Req 4.1, 4.2, 12.1, 12.2)
- Corrupted file recovery           (Req 4.5)
- Atomic write behaviour            (Req 4.4)
- Empty file handling               (Req 4.5)
- record_install / record_uninstall / get_installed / list_installed
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openharness.skills.lock import HubLockFile, LockEntry, TapsManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    name: str = "my-skill",
    source: str = "github",
    identifier: str = "owner/repo/skills/my-skill",
    trust_level: str = "community",
    content_hash: str = "sha256:abc123",
    install_path: str = "~/.velaris-agent/skills/my-skill",
    files: list[str] | None = None,
    installed_at: str = "2025-01-15T10:30:00Z",
    updated_at: str | None = None,
) -> LockEntry:
    return LockEntry(
        name=name,
        source=source,
        identifier=identifier,
        trust_level=trust_level,
        content_hash=content_hash,
        install_path=install_path,
        files=files or ["SKILL.md"],
        installed_at=installed_at,
        updated_at=updated_at,
    )


# ---------------------------------------------------------------------------
# Load / Save round-trip
# ---------------------------------------------------------------------------


class TestLoadSaveRoundTrip:
    """Req 4.1, 4.2, 12.1, 12.2 — save then load produces equivalent data."""

    def test_single_entry_round_trip(self, tmp_path: Path) -> None:
        lock = HubLockFile(tmp_path / "lock.json")
        entry = _make_entry()
        lock.save({"my-skill": entry})

        loaded = lock.load()
        assert "my-skill" in loaded
        assert loaded["my-skill"] == entry

    def test_multiple_entries_round_trip(self, tmp_path: Path) -> None:
        lock = HubLockFile(tmp_path / "lock.json")
        entries = {
            "alpha": _make_entry(name="alpha", content_hash="sha256:aaa"),
            "beta": _make_entry(name="beta", content_hash="sha256:bbb"),
        }
        lock.save(entries)

        loaded = lock.load()
        assert len(loaded) == 2
        assert loaded["alpha"].content_hash == "sha256:aaa"
        assert loaded["beta"].content_hash == "sha256:bbb"

    def test_entry_with_updated_at(self, tmp_path: Path) -> None:
        lock = HubLockFile(tmp_path / "lock.json")
        entry = _make_entry(updated_at="2025-06-01T12:00:00Z")
        lock.save({"my-skill": entry})

        loaded = lock.load()
        assert loaded["my-skill"].updated_at == "2025-06-01T12:00:00Z"

    def test_json_format_on_disk(self, tmp_path: Path) -> None:
        """The persisted file must be valid JSON with version + skills keys."""
        lock_path = tmp_path / "lock.json"
        lock = HubLockFile(lock_path)
        lock.save({"s": _make_entry(name="s")})

        raw = json.loads(lock_path.read_text(encoding="utf-8"))
        assert raw["version"] == 1
        assert "s" in raw["skills"]


# ---------------------------------------------------------------------------
# Corrupted / invalid file recovery
# ---------------------------------------------------------------------------


class TestCorruptedFileRecovery:
    """Req 4.5 — invalid JSON returns empty dict."""

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "lock.json"
        lock_path.write_text("{not valid json!!!", encoding="utf-8")

        lock = HubLockFile(lock_path)
        assert lock.load() == {}

    def test_partial_json_returns_empty(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "lock.json"
        lock_path.write_text('{"version": 1, "skills": {', encoding="utf-8")

        lock = HubLockFile(lock_path)
        assert lock.load() == {}

    def test_non_dict_json_returns_empty(self, tmp_path: Path) -> None:
        """A JSON array at the top level has no 'skills' key → empty."""
        lock_path = tmp_path / "lock.json"
        lock_path.write_text("[1, 2, 3]", encoding="utf-8")

        lock = HubLockFile(lock_path)
        assert lock.load() == {}

    def test_invalid_entry_skipped(self, tmp_path: Path) -> None:
        """An entry missing required fields is silently skipped."""
        lock_path = tmp_path / "lock.json"
        payload = {
            "version": 1,
            "skills": {
                "good": _make_entry(name="good").model_dump(),
                "bad": {"name": "bad"},  # missing required fields
            },
        }
        lock_path.write_text(json.dumps(payload), encoding="utf-8")

        lock = HubLockFile(lock_path)
        loaded = lock.load()
        assert "good" in loaded
        assert "bad" not in loaded


# ---------------------------------------------------------------------------
# Atomic write behaviour
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    """Req 4.4 — writes use temp file + os.replace."""

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep_path = tmp_path / "a" / "b" / "lock.json"
        lock = HubLockFile(deep_path)
        lock.save({})

        assert deep_path.exists()

    def test_no_leftover_tmp_on_success(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "lock.json"
        lock = HubLockFile(lock_path)
        lock.save({"x": _make_entry(name="x")})

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_overwrite_preserves_consistency(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "lock.json"
        lock = HubLockFile(lock_path)

        lock.save({"v1": _make_entry(name="v1")})
        lock.save({"v2": _make_entry(name="v2")})

        loaded = lock.load()
        assert "v2" in loaded
        assert "v1" not in loaded


# ---------------------------------------------------------------------------
# Empty / missing file handling
# ---------------------------------------------------------------------------


class TestEmptyFileHandling:
    """Req 4.5 — missing or empty file returns empty dict."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        lock = HubLockFile(tmp_path / "nonexistent.json")
        assert lock.load() == {}

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "lock.json"
        lock_path.write_text("", encoding="utf-8")

        lock = HubLockFile(lock_path)
        assert lock.load() == {}

    def test_empty_skills_dict(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "lock.json"
        lock_path.write_text('{"version":1,"skills":{}}', encoding="utf-8")

        lock = HubLockFile(lock_path)
        assert lock.load() == {}


# ---------------------------------------------------------------------------
# record_install / record_uninstall / get_installed / list_installed
# ---------------------------------------------------------------------------


class TestRecordInstall:
    def test_record_install_creates_entry(self, tmp_path: Path) -> None:
        lock = HubLockFile(tmp_path / "lock.json")
        entry = _make_entry()
        lock.record_install(entry)

        assert lock.get_installed("my-skill") == entry

    def test_record_install_overwrites_existing(self, tmp_path: Path) -> None:
        lock = HubLockFile(tmp_path / "lock.json")
        lock.record_install(_make_entry(content_hash="old"))
        lock.record_install(_make_entry(content_hash="new"))

        result = lock.get_installed("my-skill")
        assert result is not None
        assert result.content_hash == "new"


class TestRecordUninstall:
    def test_record_uninstall_removes_entry(self, tmp_path: Path) -> None:
        lock = HubLockFile(tmp_path / "lock.json")
        lock.record_install(_make_entry())
        lock.record_uninstall("my-skill")

        assert lock.get_installed("my-skill") is None

    def test_record_uninstall_nonexistent_is_noop(self, tmp_path: Path) -> None:
        lock = HubLockFile(tmp_path / "lock.json")
        lock.record_install(_make_entry())
        lock.record_uninstall("no-such-skill")

        assert lock.get_installed("my-skill") is not None


class TestGetInstalled:
    def test_returns_none_for_unknown(self, tmp_path: Path) -> None:
        lock = HubLockFile(tmp_path / "lock.json")
        assert lock.get_installed("nope") is None

    def test_returns_correct_entry(self, tmp_path: Path) -> None:
        lock = HubLockFile(tmp_path / "lock.json")
        lock.record_install(_make_entry(name="a", content_hash="h1"))
        lock.record_install(_make_entry(name="b", content_hash="h2"))

        result = lock.get_installed("b")
        assert result is not None
        assert result.content_hash == "h2"


class TestListInstalled:
    def test_empty_when_no_entries(self, tmp_path: Path) -> None:
        lock = HubLockFile(tmp_path / "lock.json")
        assert lock.list_installed() == []

    def test_returns_all_entries(self, tmp_path: Path) -> None:
        lock = HubLockFile(tmp_path / "lock.json")
        lock.record_install(_make_entry(name="a"))
        lock.record_install(_make_entry(name="b"))

        names = {e.name for e in lock.list_installed()}
        assert names == {"a", "b"}


# ---------------------------------------------------------------------------
# TapsManager tests  (Req 5.1, 5.3, 5.5)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tap_repos(taps: list[dict[str, str]]) -> list[str]:
    """Extract repo names from a taps list."""
    return [t["repo"] for t in taps]


# ---------------------------------------------------------------------------
# Add / Remove / List
# ---------------------------------------------------------------------------


class TestTapsManagerAdd:
    """Req 5.1 — add registers a new tap with valid owner/repo format."""

    def test_add_valid_repo(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        mgr.add("myorg/my-skills")

        taps = mgr.list_taps()
        assert len(taps) == 1
        assert taps[0]["repo"] == "myorg/my-skills"

    def test_add_includes_added_at(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        mgr.add("owner/repo")

        taps = mgr.list_taps()
        assert "added_at" in taps[0]

    def test_add_multiple_repos(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        mgr.add("org-a/repo-a")
        mgr.add("org-b/repo-b")

        repos = _tap_repos(mgr.list_taps())
        assert repos == ["org-a/repo-a", "org-b/repo-b"]

    def test_add_repo_with_dots_and_hyphens(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        mgr.add("my-org.v2/my-skills_repo.v3")

        assert _tap_repos(mgr.list_taps()) == ["my-org.v2/my-skills_repo.v3"]


class TestTapsManagerRemove:
    """Req 5.3 — remove deletes the tap from taps.json."""

    def test_remove_existing_tap(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        mgr.add("org/repo")
        mgr.remove("org/repo")

        assert mgr.list_taps() == []

    def test_remove_nonexistent_is_noop(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        mgr.add("org/repo")
        mgr.remove("other/repo")

        assert len(mgr.list_taps()) == 1

    def test_remove_one_of_many(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        mgr.add("a/one")
        mgr.add("b/two")
        mgr.add("c/three")
        mgr.remove("b/two")

        repos = _tap_repos(mgr.list_taps())
        assert "b/two" not in repos
        assert len(repos) == 2


class TestTapsManagerList:
    """Req 5.1 — list_taps returns all registered taps."""

    def test_list_empty(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        assert mgr.list_taps() == []

    def test_list_returns_all(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        mgr.add("a/one")
        mgr.add("b/two")

        repos = _tap_repos(mgr.list_taps())
        assert set(repos) == {"a/one", "b/two"}


# ---------------------------------------------------------------------------
# Format validation
# ---------------------------------------------------------------------------


class TestTapsManagerFormatValidation:
    """Req 5.5 — reject invalid tap repo formats."""

    def test_empty_string_rejected(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        with pytest.raises(ValueError):
            mgr.add("")

    def test_missing_slash_rejected(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        with pytest.raises(ValueError):
            mgr.add("noslash")

    def test_spaces_rejected(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        with pytest.raises(ValueError):
            mgr.add("has space/repo")

    def test_special_chars_rejected(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        with pytest.raises(ValueError):
            mgr.add("owner!/repo")

    def test_triple_segment_rejected(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        with pytest.raises(ValueError):
            mgr.add("a/b/c")

    def test_leading_slash_rejected(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        with pytest.raises(ValueError):
            mgr.add("/repo")

    def test_trailing_slash_rejected(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        with pytest.raises(ValueError):
            mgr.add("owner/")

    def test_at_sign_rejected(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        with pytest.raises(ValueError):
            mgr.add("@owner/repo")


# ---------------------------------------------------------------------------
# Empty / missing file handling
# ---------------------------------------------------------------------------


class TestTapsManagerEmptyFile:
    """Req 5.1 — missing or empty taps file returns empty list."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "nonexistent.json")
        assert mgr.list_taps() == []

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        taps_path = tmp_path / "taps.json"
        taps_path.write_text("", encoding="utf-8")

        mgr = TapsManager(taps_path)
        assert mgr.list_taps() == []

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        taps_path = tmp_path / "taps.json"
        taps_path.write_text("{bad json!!!", encoding="utf-8")

        mgr = TapsManager(taps_path)
        assert mgr.list_taps() == []

    def test_empty_taps_array(self, tmp_path: Path) -> None:
        taps_path = tmp_path / "taps.json"
        taps_path.write_text('{"version":1,"taps":[]}', encoding="utf-8")

        mgr = TapsManager(taps_path)
        assert mgr.list_taps() == []


# ---------------------------------------------------------------------------
# Duplicate add is a no-op
# ---------------------------------------------------------------------------


class TestTapsManagerDuplicateAdd:
    """Req 5.1 — adding the same repo twice does not create duplicates."""

    def test_duplicate_add_is_noop(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        mgr.add("org/repo")
        mgr.add("org/repo")

        taps = mgr.list_taps()
        assert len(taps) == 1
        assert taps[0]["repo"] == "org/repo"

    def test_duplicate_among_multiple(self, tmp_path: Path) -> None:
        mgr = TapsManager(tmp_path / "taps.json")
        mgr.add("a/one")
        mgr.add("b/two")
        mgr.add("a/one")

        repos = _tap_repos(mgr.list_taps())
        assert repos == ["a/one", "b/two"]
