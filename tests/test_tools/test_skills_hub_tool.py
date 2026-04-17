"""Unit tests for SkillsHubTool — agent tool wrapping Hub operations.

Validates: Requirements 6.1, 6.2
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from openharness.tools.base import ToolExecutionContext, ToolResult
from openharness.tools.skills_hub_tool import SkillsHubInput, SkillsHubTool


def _context(tmp_path: Path) -> ToolExecutionContext:
    """Build a minimal ToolExecutionContext for testing."""
    return ToolExecutionContext(cwd=tmp_path)


# ---------------------------------------------------------------------------
# SkillsHubInput validation
# ---------------------------------------------------------------------------


class TestSkillsHubInput:
    def test_valid_actions(self) -> None:
        for action in ("search", "install", "check", "update", "uninstall", "audit"):
            inp = SkillsHubInput(action=action)
            assert inp.action == action

    def test_defaults(self) -> None:
        inp = SkillsHubInput(action="search")
        assert inp.query is None
        assert inp.name is None
        assert inp.force is False

    def test_all_fields(self) -> None:
        inp = SkillsHubInput(
            action="install", query="q", name="my-skill", force=True
        )
        assert inp.action == "install"
        assert inp.query == "q"
        assert inp.name == "my-skill"
        assert inp.force is True


# ---------------------------------------------------------------------------
# is_read_only
# ---------------------------------------------------------------------------


class TestIsReadOnly:
    def test_read_only_actions(self) -> None:
        tool = SkillsHubTool()
        for action in ("search", "check", "audit"):
            assert tool.is_read_only(SkillsHubInput(action=action)) is True

    def test_write_actions(self) -> None:
        tool = SkillsHubTool()
        for action in ("install", "update", "uninstall"):
            assert tool.is_read_only(SkillsHubInput(action=action)) is False


# ---------------------------------------------------------------------------
# execute — unknown action
# ---------------------------------------------------------------------------


class TestExecuteUnknownAction:
    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self, tmp_path: Path) -> None:
        tool = SkillsHubTool()
        result = await tool.execute(
            SkillsHubInput(action="bogus"), _context(tmp_path)
        )
        assert result.is_error is True
        assert "Unknown action" in result.output
        assert "bogus" in result.output


# ---------------------------------------------------------------------------
# execute search
# ---------------------------------------------------------------------------


class TestExecuteSearch:
    @pytest.mark.asyncio
    async def test_search_formats_results(self, tmp_path: Path) -> None:
        from openharness.skills.hub import SkillMeta

        fake_results = [
            SkillMeta(
                name="alpha",
                description="Alpha skill",
                source="github",
                identifier="owner/repo/alpha",
                trust_level="community",
            ),
            SkillMeta(
                name="beta",
                description="Beta skill",
                source="optional",
                identifier="optional/beta",
                trust_level="builtin",
            ),
        ]

        tool = SkillsHubTool()
        with patch(
            "openharness.tools.skills_hub_tool.default_sources", return_value=[]
        ), patch(
            "openharness.skills.hub.parallel_search_sources",
            new_callable=AsyncMock,
            return_value=fake_results,
        ):
            result = await tool.execute(
                SkillsHubInput(action="search", query="test"),
                _context(tmp_path),
            )

        assert result.is_error is False
        assert "Found 2 skill(s)" in result.output
        assert "alpha" in result.output
        assert "beta" in result.output

    @pytest.mark.asyncio
    async def test_search_no_results(self, tmp_path: Path) -> None:
        tool = SkillsHubTool()
        with patch(
            "openharness.tools.skills_hub_tool.default_sources", return_value=[]
        ), patch(
            "openharness.skills.hub.parallel_search_sources",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await tool.execute(
                SkillsHubInput(action="search"), _context(tmp_path)
            )

        assert result.is_error is False
        assert "No skills found" in result.output


# ---------------------------------------------------------------------------
# execute install — missing name
# ---------------------------------------------------------------------------


class TestExecuteInstallWithoutName:
    @pytest.mark.asyncio
    async def test_install_without_name_returns_error(self, tmp_path: Path) -> None:
        tool = SkillsHubTool()
        result = await tool.execute(
            SkillsHubInput(action="install"), _context(tmp_path)
        )
        assert result.is_error is True
        assert "name" in result.output.lower()


# ---------------------------------------------------------------------------
# execute uninstall — missing name
# ---------------------------------------------------------------------------


class TestExecuteUninstallWithoutName:
    @pytest.mark.asyncio
    async def test_uninstall_without_name_returns_error(self, tmp_path: Path) -> None:
        tool = SkillsHubTool()
        result = await tool.execute(
            SkillsHubInput(action="uninstall"), _context(tmp_path)
        )
        assert result.is_error is True
        assert "name" in result.output.lower()


# ---------------------------------------------------------------------------
# execute update — missing name
# ---------------------------------------------------------------------------


class TestExecuteUpdateWithoutName:
    @pytest.mark.asyncio
    async def test_update_without_name_returns_error(self, tmp_path: Path) -> None:
        tool = SkillsHubTool()
        result = await tool.execute(
            SkillsHubInput(action="update"), _context(tmp_path)
        )
        assert result.is_error is True
        assert "name" in result.output.lower()
