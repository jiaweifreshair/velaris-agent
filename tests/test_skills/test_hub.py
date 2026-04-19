"""Unit tests for hub.py — data models, source abstraction, and utility functions."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from openharness.skills.guard import ScanResult
from openharness.skills.hub import (
    GitHubAuth,
    OptionalSkillSource,
    SkillBundle,
    SkillMeta,
    SkillSource,
    _normalize_bundle_path,
    _validate_bundle_rel_path,
    _validate_skill_name,
    append_audit_log,
    bundle_content_hash,
    check_for_skill_updates,
    content_hash,
    install_from_quarantine,
    install_skill,
    parallel_search_sources,
    quarantine_bundle,
    uninstall_skill,
)
from openharness.skills.lock import HubLockFile, LockEntry


# ---------------------------------------------------------------------------
# SkillMeta / SkillBundle model tests
# ---------------------------------------------------------------------------


class TestSkillMeta:
    def test_basic_construction(self) -> None:
        meta = SkillMeta(
            name="my-skill",
            description="A test skill",
            source="github",
            identifier="owner/repo/skills/my-skill",
            trust_level="community",
        )
        assert meta.name == "my-skill"
        assert meta.repo is None
        assert meta.path is None
        assert meta.tags == []

    def test_optional_fields(self) -> None:
        meta = SkillMeta(
            name="x",
            description="d",
            source="github",
            identifier="id",
            trust_level="community",
            repo="owner/repo",
            path="skills/x",
            tags=["ai", "test"],
        )
        assert meta.repo == "owner/repo"
        assert meta.tags == ["ai", "test"]


class TestSkillBundle:
    def test_basic_construction(self) -> None:
        files = {"SKILL.md": "# Hello\nA skill."}
        bundle = SkillBundle(
            name="hello",
            files=files,
            source="github",
            identifier="owner/repo/hello",
            trust_level="community",
            content_hash=bundle_content_hash(files),
        )
        assert bundle.name == "hello"
        assert bundle.metadata == {}
        assert bundle.content_hash.startswith("sha256:")

    def test_content_hash_matches_bundle_hash(self) -> None:
        files = {"SKILL.md": "content", "refs/a.md": "ref content"}
        expected = bundle_content_hash(files)
        bundle = SkillBundle(
            name="b",
            files=files,
            source="optional",
            identifier="optional/b",
            trust_level="builtin",
            content_hash=expected,
        )
        assert bundle.content_hash == expected


# ---------------------------------------------------------------------------
# Utility function tests
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_deterministic(self) -> None:
        assert content_hash("hello") == content_hash("hello")

    def test_different_content(self) -> None:
        assert content_hash("a") != content_hash("b")

    def test_sha256_prefix(self) -> None:
        h = content_hash("test")
        assert h.startswith("sha256:")
        assert len(h) == len("sha256:") + 64


class TestBundleContentHash:
    def test_deterministic(self) -> None:
        files = {"a.md": "aaa", "b.md": "bbb"}
        assert bundle_content_hash(files) == bundle_content_hash(files)

    def test_order_independent(self) -> None:
        """Files are sorted by path, so insertion order doesn't matter."""
        files_a = {"z.md": "z", "a.md": "a"}
        files_b = {"a.md": "a", "z.md": "z"}
        assert bundle_content_hash(files_a) == bundle_content_hash(files_b)

    def test_different_files(self) -> None:
        assert bundle_content_hash({"a": "1"}) != bundle_content_hash({"a": "2"})

    def test_different_paths(self) -> None:
        assert bundle_content_hash({"a": "x"}) != bundle_content_hash({"b": "x"})


class TestValidateSkillName:
    def test_valid_names(self) -> None:
        for name in ("my-skill", "skill_1", "Skill.v2", "a"):
            _validate_skill_name(name)  # should not raise

    def test_empty_name(self) -> None:
        with pytest.raises(ValueError, match="Invalid skill name"):
            _validate_skill_name("")

    def test_starts_with_dash(self) -> None:
        with pytest.raises(ValueError, match="Invalid skill name"):
            _validate_skill_name("-bad")

    def test_contains_spaces(self) -> None:
        with pytest.raises(ValueError, match="Invalid skill name"):
            _validate_skill_name("bad name")

    def test_contains_slash(self) -> None:
        with pytest.raises(ValueError, match="Invalid skill name"):
            _validate_skill_name("bad/name")


class TestValidateBundleRelPath:
    def test_valid_paths(self) -> None:
        for p in ("SKILL.md", "refs/api.md", "scripts/run.py"):
            _validate_bundle_rel_path(p)  # should not raise

    def test_path_traversal(self) -> None:
        with pytest.raises(ValueError, match="traversal"):
            _validate_bundle_rel_path("../../etc/passwd")

    def test_absolute_path(self) -> None:
        with pytest.raises(ValueError, match="Absolute path"):
            _validate_bundle_rel_path("/etc/passwd")

    def test_backslash_traversal(self) -> None:
        with pytest.raises(ValueError, match="traversal"):
            _validate_bundle_rel_path("..\\..\\etc\\passwd")


class TestNormalizeBundlePath:
    def test_forward_slash(self) -> None:
        assert _normalize_bundle_path("a/b/c") == "a/b/c"

    def test_backslash_to_forward(self) -> None:
        assert _normalize_bundle_path("a\\b\\c") == "a/b/c"

    def test_collapse_double_slash(self) -> None:
        assert _normalize_bundle_path("a//b///c") == "a/b/c"

    def test_strip_leading_trailing(self) -> None:
        assert _normalize_bundle_path("/a/b/") == "a/b"


# ---------------------------------------------------------------------------
# GitHubAuth tests
# ---------------------------------------------------------------------------


class TestGitHubAuth:
    def test_token_from_env(self) -> None:
        auth = GitHubAuth()
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test123"}):
            token = asyncio.get_event_loop().run_until_complete(auth.get_token())
        assert token == "ghp_test123"

    def test_no_token_returns_none(self) -> None:
        auth = GitHubAuth()
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError),
        ):
            token = asyncio.get_event_loop().run_until_complete(auth.get_token())
        assert token is None


# ---------------------------------------------------------------------------
# OptionalSkillSource tests
# ---------------------------------------------------------------------------


class TestOptionalSkillSource:
    def test_search_empty_dir(self, tmp_path: Path) -> None:
        source = OptionalSkillSource(tmp_path)
        results = asyncio.get_event_loop().run_until_complete(source.search(""))
        assert results == []

    def test_search_nonexistent_dir(self, tmp_path: Path) -> None:
        source = OptionalSkillSource(tmp_path / "nonexistent")
        results = asyncio.get_event_loop().run_until_complete(source.search(""))
        assert results == []

    def test_search_finds_skill(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# My Skill\nA great skill.", encoding="utf-8")

        source = OptionalSkillSource(tmp_path)
        results = asyncio.get_event_loop().run_until_complete(source.search(""))
        assert len(results) == 1
        assert results[0].name == "my-skill"
        assert results[0].source == "optional"
        assert results[0].trust_level == "builtin"

    def test_search_filters_by_query(self, tmp_path: Path) -> None:
        for name in ("alpha", "beta"):
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(f"# {name}", encoding="utf-8")

        source = OptionalSkillSource(tmp_path)
        results = asyncio.get_event_loop().run_until_complete(source.search("alpha"))
        assert len(results) == 1
        assert results[0].name == "alpha"

    def test_fetch_reads_files(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Test", encoding="utf-8")
        refs = skill_dir / "references"
        refs.mkdir()
        (refs / "api.md").write_text("API docs", encoding="utf-8")

        source = OptionalSkillSource(tmp_path)
        bundle = asyncio.get_event_loop().run_until_complete(
            source.fetch("optional/test-skill")
        )
        assert bundle.name == "test-skill"
        assert "SKILL.md" in bundle.files
        assert "references/api.md" in bundle.files
        assert bundle.content_hash == bundle_content_hash(bundle.files)

    def test_fetch_missing_skill_raises(self, tmp_path: Path) -> None:
        source = OptionalSkillSource(tmp_path)
        with pytest.raises(FileNotFoundError):
            asyncio.get_event_loop().run_until_complete(
                source.fetch("optional/nonexistent")
            )

    def test_source_id(self, tmp_path: Path) -> None:
        source = OptionalSkillSource(tmp_path)
        assert source.source_id() == "optional"

    def test_trust_level(self, tmp_path: Path) -> None:
        source = OptionalSkillSource(tmp_path)
        assert source.trust_level_for("anything") == "builtin"


# ---------------------------------------------------------------------------
# Hub operation function tests (Task 4.3)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bundle(
    name: str = "test-skill",
    source: str = "optional",
    identifier: str = "optional/test-skill",
    trust_level: str = "builtin",
    files: dict[str, str] | None = None,
) -> SkillBundle:
    """Create a SkillBundle for testing."""
    if files is None:
        files = {"SKILL.md": "# Test\nA test skill."}
    return SkillBundle(
        name=name,
        files=files,
        source=source,
        identifier=identifier,
        trust_level=trust_level,
        content_hash=bundle_content_hash(files),
    )


class _FakeSource(SkillSource):
    """A mock SkillSource for testing hub operations."""

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
# quarantine_bundle tests
# ---------------------------------------------------------------------------


class TestQuarantineBundle:
    def test_writes_files_to_quarantine(self, tmp_path: Path) -> None:
        bundle = _make_bundle(files={"SKILL.md": "# Hi", "refs/a.md": "ref"})
        with (
            patch("openharness.skills.hub.get_user_skills_dir", return_value=tmp_path),
            patch("openharness.config.paths.get_config_dir", return_value=tmp_path),
        ):
            qpath = quarantine_bundle(bundle)

        assert qpath.exists()
        assert (qpath / "SKILL.md").read_text(encoding="utf-8") == "# Hi"
        assert (qpath / "refs" / "a.md").read_text(encoding="utf-8") == "ref"

    def test_overwrites_previous_quarantine(self, tmp_path: Path) -> None:
        bundle = _make_bundle(files={"SKILL.md": "v1"})
        with (
            patch("openharness.skills.hub.get_user_skills_dir", return_value=tmp_path),
            patch("openharness.config.paths.get_config_dir", return_value=tmp_path),
        ):
            qpath1 = quarantine_bundle(bundle)
            assert (qpath1 / "SKILL.md").read_text(encoding="utf-8") == "v1"

            bundle2 = _make_bundle(files={"SKILL.md": "v2"})
            qpath2 = quarantine_bundle(bundle2)
            assert (qpath2 / "SKILL.md").read_text(encoding="utf-8") == "v2"


# ---------------------------------------------------------------------------
# install_from_quarantine tests
# ---------------------------------------------------------------------------


class TestInstallFromQuarantine:
    def test_copies_files(self, tmp_path: Path) -> None:
        src = tmp_path / "quarantine" / "my-skill"
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text("# Skill", encoding="utf-8")

        target = tmp_path / "skills" / "my-skill"
        result = install_from_quarantine(src, target)

        assert result == target
        assert (target / "SKILL.md").read_text(encoding="utf-8") == "# Skill"

    def test_overwrites_existing_target(self, tmp_path: Path) -> None:
        src = tmp_path / "quarantine" / "my-skill"
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text("new", encoding="utf-8")

        target = tmp_path / "skills" / "my-skill"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("old", encoding="utf-8")

        install_from_quarantine(src, target)
        assert (target / "SKILL.md").read_text(encoding="utf-8") == "new"


# ---------------------------------------------------------------------------
# install_skill tests
# ---------------------------------------------------------------------------


class TestInstallSkill:
    def test_successful_install(self, tmp_path: Path) -> None:
        bundle = _make_bundle()
        source = _FakeSource(fetch_bundle=bundle)
        lock_path = tmp_path / "lock.json"
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir(parents=True)

        scan_result = ScanResult(
            skill_name="test-skill",
            source="optional",
            trust_level="builtin",
            verdict="pass",
            findings=[],
            scanned_at="2025-01-01T00:00:00Z",
            summary="Clean",
        )

        with (
            patch("openharness.skills.hub.get_user_skills_dir", return_value=skills_dir),
            patch("openharness.config.paths.get_config_dir", return_value=tmp_path),
            patch("openharness.skills.hub.HubLockFile", return_value=HubLockFile(lock_path)),
            patch("openharness.skills.hub.guard_scan_skill", return_value=scan_result),
            patch("openharness.skills.hub.should_allow_install", return_value=(True, "OK")),
        ):
            msg = asyncio.get_event_loop().run_until_complete(
                install_skill("optional/test-skill", [source])
            )

        assert "Successfully installed" in msg
        assert "test-skill" in msg
        # Lock file should have the entry
        lock = HubLockFile(lock_path)
        entry = lock.get_installed("test-skill")
        assert entry is not None
        assert entry.content_hash == bundle.content_hash

    def test_duplicate_install_rejected(self, tmp_path: Path) -> None:
        bundle = _make_bundle()
        source = _FakeSource(fetch_bundle=bundle)
        lock_path = tmp_path / "lock.json"
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir(parents=True)

        # Pre-populate lock file with existing entry
        lock = HubLockFile(lock_path)
        lock.record_install(
            LockEntry(
                name="test-skill",
                source="optional",
                identifier="optional/test-skill",
                trust_level="builtin",
                content_hash="sha256:old",
                install_path=str(skills_dir / "test-skill"),
                files=["SKILL.md"],
                installed_at="2025-01-01T00:00:00Z",
            )
        )

        with (
            patch("openharness.skills.hub.get_user_skills_dir", return_value=skills_dir),
            patch("openharness.config.paths.get_config_dir", return_value=tmp_path),
            patch("openharness.skills.hub.HubLockFile", return_value=HubLockFile(lock_path)),
        ):
            with pytest.raises(RuntimeError, match="already installed"):
                asyncio.get_event_loop().run_until_complete(
                    install_skill("optional/test-skill", [source], force=False)
                )

    def test_security_scan_blocks_install(self, tmp_path: Path) -> None:
        bundle = _make_bundle()
        source = _FakeSource(fetch_bundle=bundle)
        lock_path = tmp_path / "lock.json"
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir(parents=True)

        scan_result = ScanResult(
            skill_name="test-skill",
            source="optional",
            trust_level="builtin",
            verdict="fail",
            findings=[],
            scanned_at="2025-01-01T00:00:00Z",
            summary="High risk",
        )

        with (
            patch("openharness.skills.hub.get_user_skills_dir", return_value=skills_dir),
            patch("openharness.config.paths.get_config_dir", return_value=tmp_path),
            patch("openharness.skills.hub.HubLockFile", return_value=HubLockFile(lock_path)),
            patch("openharness.skills.hub.guard_scan_skill", return_value=scan_result),
            patch(
                "openharness.skills.hub.should_allow_install",
                return_value=(False, "Blocked: high severity"),
            ),
        ):
            with pytest.raises(RuntimeError, match="blocked by security scan"):
                asyncio.get_event_loop().run_until_complete(
                    install_skill("optional/test-skill", [source])
                )

        # Lock file should NOT have the entry
        lock = HubLockFile(lock_path)
        assert lock.get_installed("test-skill") is None


# ---------------------------------------------------------------------------
# uninstall_skill tests
# ---------------------------------------------------------------------------


class TestUninstallSkill:
    def test_successful_uninstall(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "lock.json"
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Test", encoding="utf-8")

        lock = HubLockFile(lock_path)
        lock.record_install(
            LockEntry(
                name="test-skill",
                source="optional",
                identifier="optional/test-skill",
                trust_level="builtin",
                content_hash="sha256:abc",
                install_path=str(skill_dir),
                files=["SKILL.md"],
                installed_at="2025-01-01T00:00:00Z",
            )
        )

        with (
            patch("openharness.skills.hub.get_user_skills_dir", return_value=skills_dir),
            patch("openharness.config.paths.get_config_dir", return_value=tmp_path),
            patch("openharness.skills.hub.HubLockFile", return_value=HubLockFile(lock_path)),
        ):
            msg = uninstall_skill("test-skill")

        assert "Successfully uninstalled" in msg
        assert not skill_dir.exists()
        lock2 = HubLockFile(lock_path)
        assert lock2.get_installed("test-skill") is None

    def test_uninstall_nonexistent_skill(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "lock.json"
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir(parents=True)

        with (
            patch("openharness.skills.hub.get_user_skills_dir", return_value=skills_dir),
            patch("openharness.config.paths.get_config_dir", return_value=tmp_path),
            patch("openharness.skills.hub.HubLockFile", return_value=HubLockFile(lock_path)),
        ):
            with pytest.raises(RuntimeError, match="is not installed"):
                uninstall_skill("nonexistent")


# ---------------------------------------------------------------------------
# check_for_skill_updates tests
# ---------------------------------------------------------------------------


class TestCheckForSkillUpdates:
    def test_detects_update_when_hash_differs(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "lock.json"
        lock = HubLockFile(lock_path)
        lock.record_install(
            LockEntry(
                name="my-skill",
                source="optional",
                identifier="optional/my-skill",
                trust_level="builtin",
                content_hash="sha256:old_hash",
                install_path=str(tmp_path / "my-skill"),
                files=["SKILL.md"],
                installed_at="2025-01-01T00:00:00Z",
            )
        )

        new_bundle = _make_bundle(
            name="my-skill",
            identifier="optional/my-skill",
            files={"SKILL.md": "# Updated content"},
        )
        source = _FakeSource(fetch_bundle=new_bundle)

        with patch("openharness.skills.hub.HubLockFile", return_value=HubLockFile(lock_path)):
            updates = asyncio.get_event_loop().run_until_complete(
                check_for_skill_updates([source])
            )

        assert len(updates) == 1
        assert updates[0]["name"] == "my-skill"
        assert updates[0]["current_hash"] == "sha256:old_hash"
        assert updates[0]["latest_hash"] == new_bundle.content_hash

    def test_no_update_when_hash_matches(self, tmp_path: Path) -> None:
        files = {"SKILL.md": "# Same content"}
        h = bundle_content_hash(files)

        lock_path = tmp_path / "lock.json"
        lock = HubLockFile(lock_path)
        lock.record_install(
            LockEntry(
                name="my-skill",
                source="optional",
                identifier="optional/my-skill",
                trust_level="builtin",
                content_hash=h,
                install_path=str(tmp_path / "my-skill"),
                files=["SKILL.md"],
                installed_at="2025-01-01T00:00:00Z",
            )
        )

        same_bundle = _make_bundle(
            name="my-skill",
            identifier="optional/my-skill",
            files=files,
        )
        source = _FakeSource(fetch_bundle=same_bundle)

        with patch("openharness.skills.hub.HubLockFile", return_value=HubLockFile(lock_path)):
            updates = asyncio.get_event_loop().run_until_complete(
                check_for_skill_updates([source])
            )

        assert updates == []


# ---------------------------------------------------------------------------
# parallel_search_sources tests
# ---------------------------------------------------------------------------


class TestParallelSearchSources:
    def test_merges_and_deduplicates(self) -> None:
        meta_a = SkillMeta(
            name="skill-a",
            description="A",
            source="s1",
            identifier="id-a",
            trust_level="community",
        )
        meta_b = SkillMeta(
            name="skill-b",
            description="B",
            source="s2",
            identifier="id-b",
            trust_level="community",
        )
        # Duplicate of meta_a from a different source
        meta_a_dup = SkillMeta(
            name="skill-a",
            description="A from s2",
            source="s2",
            identifier="id-a",
            trust_level="trusted",
        )

        src1 = _FakeSource(sid="s1", search_results=[meta_a])
        src2 = _FakeSource(sid="s2", search_results=[meta_b, meta_a_dup])

        results = asyncio.get_event_loop().run_until_complete(
            parallel_search_sources("", [src1, src2])
        )

        identifiers = [r.identifier for r in results]
        assert len(identifiers) == 2
        assert identifiers.count("id-a") == 1
        assert identifiers.count("id-b") == 1
        # First occurrence wins — from src1
        a_result = next(r for r in results if r.identifier == "id-a")
        assert a_result.source == "s1"

    def test_fault_tolerance_one_source_fails(self) -> None:
        meta_ok = SkillMeta(
            name="ok-skill",
            description="OK",
            source="good",
            identifier="id-ok",
            trust_level="community",
        )
        good_src = _FakeSource(sid="good", search_results=[meta_ok])
        bad_src = _FakeSource(sid="bad", search_error=RuntimeError("network down"))

        results = asyncio.get_event_loop().run_until_complete(
            parallel_search_sources("", [good_src, bad_src])
        )

        assert len(results) == 1
        assert results[0].identifier == "id-ok"


# ---------------------------------------------------------------------------
# append_audit_log tests
# ---------------------------------------------------------------------------


class TestAppendAuditLog:
    def test_creates_log_entry(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        audit_dir = tmp_path / "audit"

        with (
            patch("openharness.skills.hub.get_user_skills_dir", return_value=skills_dir),
            patch("openharness.config.paths.get_config_dir", return_value=tmp_path),
        ):
            append_audit_log(
                action="install",
                skill_name="my-skill",
                details={"source": "github", "verdict": "pass"},
            )

        log_path = audit_dir / "skills-audit.log"
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["action"] == "install"
        assert record["skill"] == "my-skill"
        assert record["source"] == "github"
        assert "timestamp" in record

    def test_appends_multiple_entries(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"

        with (
            patch("openharness.skills.hub.get_user_skills_dir", return_value=skills_dir),
            patch("openharness.config.paths.get_config_dir", return_value=tmp_path),
        ):
            append_audit_log("install", "skill-a", {"v": 1})
            append_audit_log("uninstall", "skill-b", {"v": 2})

        log_path = tmp_path / "audit" / "skills-audit.log"
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["action"] == "install"
        assert json.loads(lines[1])["action"] == "uninstall"
