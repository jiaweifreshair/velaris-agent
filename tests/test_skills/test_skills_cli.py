"""Unit tests for skills_cli.py — CLI command registration, parameter parsing, output format.

Validates: Requirements 6.1, 6.2, 6.7, 6.8, 6.9
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from openharness.commands.skills_cli import skills_app, tap_app

runner = CliRunner()


# ---------------------------------------------------------------------------
# 1. Command registration
# ---------------------------------------------------------------------------


class TestSkillsAppCommandRegistration:
    """Verify skills_app has the expected commands."""

    EXPECTED_COMMANDS = {"search", "install", "check", "update", "uninstall", "list", "audit"}

    def test_all_commands_registered(self) -> None:
        registered = {cmd.name for cmd in skills_app.registered_commands}
        assert self.EXPECTED_COMMANDS.issubset(registered)

    def test_tap_subgroup_registered(self) -> None:
        group_names = [g.typer_instance.info.name for g in skills_app.registered_groups]
        assert "tap" in group_names


class TestTapAppCommandRegistration:
    """Verify tap_app has add, remove, list commands."""

    EXPECTED_COMMANDS = {"add", "remove", "list"}

    def test_all_tap_commands_registered(self) -> None:
        registered = {cmd.name for cmd in tap_app.registered_commands}
        assert self.EXPECTED_COMMANDS.issubset(registered)


# ---------------------------------------------------------------------------
# 2. Skills commands — parameter parsing & output format
# ---------------------------------------------------------------------------


class TestSearchCommand:
    @patch("openharness.tools.skills_hub_tool.default_sources", return_value=[])
    @patch(
        "openharness.skills.hub.parallel_search_sources",
        new_callable=AsyncMock,
        return_value=[],
    )
    def test_search_no_results(self, mock_search: AsyncMock, mock_src: MagicMock) -> None:
        result = runner.invoke(skills_app, ["search", "nonexistent"])
        assert result.exit_code == 0
        assert "No skills found" in result.output

    @patch("openharness.tools.skills_hub_tool.default_sources", return_value=[])
    @patch("openharness.skills.hub.parallel_search_sources", new_callable=AsyncMock)
    def test_search_with_results(self, mock_search: AsyncMock, mock_src: MagicMock) -> None:
        from openharness.skills.hub import SkillMeta

        mock_search.return_value = [
            SkillMeta(
                name="alpha",
                description="Alpha skill",
                source="github",
                identifier="owner/repo/alpha",
                trust_level="community",
            ),
        ]
        result = runner.invoke(skills_app, ["search", "alpha"])
        assert result.exit_code == 0
        assert "Found 1 skill(s)" in result.output
        assert "alpha" in result.output

    def test_search_missing_query_exits_nonzero(self) -> None:
        result = runner.invoke(skills_app, ["search"])
        assert result.exit_code != 0


class TestInstallCommand:
    @patch("openharness.tools.skills_hub_tool.default_sources", return_value=[])
    @patch(
        "openharness.skills.hub.install_skill",
        new_callable=AsyncMock,
        return_value="Successfully installed test-skill",
    )
    def test_install_success(self, mock_install: AsyncMock, mock_src: MagicMock) -> None:
        result = runner.invoke(skills_app, ["install", "owner/repo/test-skill"])
        assert result.exit_code == 0
        assert "Successfully installed" in result.output

    @patch("openharness.tools.skills_hub_tool.default_sources", return_value=[])
    @patch(
        "openharness.skills.hub.install_skill",
        new_callable=AsyncMock,
        side_effect=RuntimeError("already installed"),
    )
    def test_install_failure_exits_nonzero(self, mock_install: AsyncMock, mock_src: MagicMock) -> None:
        result = runner.invoke(skills_app, ["install", "owner/repo/dup"])
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_install_missing_identifier_exits_nonzero(self) -> None:
        result = runner.invoke(skills_app, ["install"])
        assert result.exit_code != 0

    @patch("openharness.tools.skills_hub_tool.default_sources", return_value=[])
    @patch("openharness.skills.hub.install_skill", new_callable=AsyncMock, return_value="Forced install done")
    def test_install_force_flag(self, mock_install: AsyncMock, mock_src: MagicMock) -> None:
        result = runner.invoke(skills_app, ["install", "owner/repo/x", "--force"])
        assert result.exit_code == 0
        mock_install.assert_called_once()


class TestCheckCommand:
    @patch("openharness.tools.skills_hub_tool.default_sources", return_value=[])
    @patch(
        "openharness.skills.hub.check_for_skill_updates",
        new_callable=AsyncMock,
        return_value=[],
    )
    def test_check_all_up_to_date(self, mock_check: AsyncMock, mock_src: MagicMock) -> None:
        result = runner.invoke(skills_app, ["check"])
        assert result.exit_code == 0
        assert "up to date" in result.output

    @patch("openharness.tools.skills_hub_tool.default_sources", return_value=[])
    @patch("openharness.skills.hub.check_for_skill_updates", new_callable=AsyncMock)
    def test_check_with_updates(self, mock_check: AsyncMock, mock_src: MagicMock) -> None:
        mock_check.return_value = [
            {"name": "my-skill", "source": "github"},
        ]
        result = runner.invoke(skills_app, ["check"])
        assert result.exit_code == 0
        assert "1 skill(s) have updates" in result.output
        assert "my-skill" in result.output

    @patch("openharness.tools.skills_hub_tool.default_sources", return_value=[])
    @patch("openharness.skills.hub.check_for_skill_updates", new_callable=AsyncMock)
    def test_check_filters_by_name(self, mock_check: AsyncMock, mock_src: MagicMock) -> None:
        mock_check.return_value = [
            {"name": "skill-a", "source": "github"},
            {"name": "skill-b", "source": "optional"},
        ]
        result = runner.invoke(skills_app, ["check", "skill-a"])
        assert result.exit_code == 0
        assert "skill-a" in result.output
        assert "skill-b" not in result.output


class TestUpdateCommand:
    @patch("openharness.tools.skills_hub_tool.default_sources", return_value=[])
    @patch(
        "openharness.skills.hub.update_skill",
        new_callable=AsyncMock,
        return_value="Updated my-skill",
    )
    def test_update_specific_skill(self, mock_update: AsyncMock, mock_src: MagicMock) -> None:
        result = runner.invoke(skills_app, ["update", "my-skill"])
        assert result.exit_code == 0
        assert "Updated" in result.output

    @patch("openharness.tools.skills_hub_tool.default_sources", return_value=[])
    @patch(
        "openharness.skills.hub.check_for_skill_updates",
        new_callable=AsyncMock,
        return_value=[],
    )
    def test_update_all_no_updates(self, mock_check: AsyncMock, mock_src: MagicMock) -> None:
        result = runner.invoke(skills_app, ["update"])
        assert result.exit_code == 0
        assert "up to date" in result.output

    @patch("openharness.tools.skills_hub_tool.default_sources", return_value=[])
    @patch(
        "openharness.skills.hub.update_skill",
        new_callable=AsyncMock,
        side_effect=RuntimeError("source unreachable"),
    )
    def test_update_failure_exits_nonzero(self, mock_update: AsyncMock, mock_src: MagicMock) -> None:
        result = runner.invoke(skills_app, ["update", "bad-skill"])
        assert result.exit_code != 0
        assert "Error" in result.output


class TestUninstallCommand:
    @patch("openharness.skills.hub.uninstall_skill", return_value="Successfully uninstalled my-skill")
    def test_uninstall_success(self, mock_uninstall: MagicMock) -> None:
        result = runner.invoke(skills_app, ["uninstall", "my-skill"])
        assert result.exit_code == 0
        assert "Successfully uninstalled" in result.output

    @patch("openharness.skills.hub.uninstall_skill", side_effect=RuntimeError("is not installed"))
    def test_uninstall_failure_exits_nonzero(self, mock_uninstall: MagicMock) -> None:
        result = runner.invoke(skills_app, ["uninstall", "missing"])
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_uninstall_missing_name_exits_nonzero(self) -> None:
        result = runner.invoke(skills_app, ["uninstall"])
        assert result.exit_code != 0


class TestListCommand:
    @patch("openharness.skills.lock.HubLockFile")
    def test_list_no_skills(self, mock_lock_cls: MagicMock) -> None:
        mock_lock_cls.return_value.list_installed.return_value = []
        result = runner.invoke(skills_app, ["list"])
        assert result.exit_code == 0
        assert "No skills installed" in result.output

    @patch("openharness.skills.lock.HubLockFile")
    def test_list_with_skills(self, mock_lock_cls: MagicMock) -> None:
        from openharness.skills.lock import LockEntry

        mock_lock_cls.return_value.list_installed.return_value = [
            LockEntry(
                name="skill-a",
                source="github",
                identifier="owner/repo/skill-a",
                trust_level="community",
                content_hash="sha256:" + "a" * 64,
                install_path="/tmp/skills/skill-a",
                files=["SKILL.md"],
                installed_at="2025-01-01T00:00:00Z",
            ),
        ]
        result = runner.invoke(skills_app, ["list"])
        assert result.exit_code == 0
        assert "1 skill(s) installed" in result.output
        assert "skill-a" in result.output
        assert "github" in result.output


class TestAuditCommand:
    @patch("openharness.skills.hub.ensure_hub_dirs")
    def test_audit_no_log(self, mock_dirs: MagicMock, tmp_path) -> None:
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        mock_dirs.return_value = (tmp_path / "quarantine", audit_dir)
        result = runner.invoke(skills_app, ["audit"])
        assert result.exit_code == 0
        assert "No audit log entries" in result.output

    @patch("openharness.skills.hub.ensure_hub_dirs")
    def test_audit_shows_log(self, mock_dirs: MagicMock, tmp_path) -> None:
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        log_path = audit_dir / "skills-audit.log"
        log_path.write_text('{"action":"install","skill":"x"}\n', encoding="utf-8")
        mock_dirs.return_value = (tmp_path / "quarantine", audit_dir)
        result = runner.invoke(skills_app, ["audit"])
        assert result.exit_code == 0
        assert "Audit log" in result.output
        assert "install" in result.output


# ---------------------------------------------------------------------------
# 3. Tap commands
# ---------------------------------------------------------------------------


class TestTapAddCommand:
    @patch("openharness.skills.lock.TapsManager")
    def test_tap_add_success(self, mock_mgr_cls: MagicMock) -> None:
        result = runner.invoke(skills_app, ["tap", "add", "myorg/my-skills"])
        assert result.exit_code == 0
        assert "Added tap" in result.output
        mock_mgr_cls.return_value.add.assert_called_once_with("myorg/my-skills")

    @patch("openharness.skills.lock.TapsManager")
    def test_tap_add_invalid_format(self, mock_mgr_cls: MagicMock) -> None:
        mock_mgr_cls.return_value.add.side_effect = ValueError("Invalid tap format")
        result = runner.invoke(skills_app, ["tap", "add", "bad-format"])
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_tap_add_missing_repo_exits_nonzero(self) -> None:
        result = runner.invoke(skills_app, ["tap", "add"])
        assert result.exit_code != 0


class TestTapRemoveCommand:
    @patch("openharness.skills.lock.TapsManager")
    def test_tap_remove_success(self, mock_mgr_cls: MagicMock) -> None:
        result = runner.invoke(skills_app, ["tap", "remove", "myorg/my-skills"])
        assert result.exit_code == 0
        assert "Removed tap" in result.output

    @patch("openharness.skills.lock.TapsManager")
    def test_tap_remove_failure(self, mock_mgr_cls: MagicMock) -> None:
        mock_mgr_cls.return_value.remove.side_effect = RuntimeError("not found")
        result = runner.invoke(skills_app, ["tap", "remove", "bad/repo"])
        assert result.exit_code != 0
        assert "Error" in result.output


class TestTapListCommand:
    @patch("openharness.skills.lock.TapsManager")
    def test_tap_list_empty(self, mock_mgr_cls: MagicMock) -> None:
        mock_mgr_cls.return_value.list_taps.return_value = []
        result = runner.invoke(skills_app, ["tap", "list"])
        assert result.exit_code == 0
        assert "No taps registered" in result.output

    @patch("openharness.skills.lock.TapsManager")
    def test_tap_list_with_taps(self, mock_mgr_cls: MagicMock) -> None:
        mock_mgr_cls.return_value.list_taps.return_value = [
            {"repo": "org/skills", "added_at": "2025-01-01T00:00:00Z"},
        ]
        result = runner.invoke(skills_app, ["tap", "list"])
        assert result.exit_code == 0
        assert "1 tap(s) registered" in result.output
        assert "org/skills" in result.output
