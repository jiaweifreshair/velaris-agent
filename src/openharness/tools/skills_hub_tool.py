"""Skills Hub agent tool.

Wraps Hub operations (search, install, update, uninstall, check, audit)
so the LLM can manage skills through the tool interface.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

logger = logging.getLogger(__name__)


class SkillsHubInput(BaseModel):
    """Skills Hub tool input."""

    action: str = Field(description="操作：search/install/check/update/uninstall/audit")
    query: str | None = Field(default=None, description="搜索关键词")
    name: str | None = Field(default=None, description="技能名称或标识符")
    force: bool = Field(default=False, description="是否强制安装/更新")


def default_sources() -> list:
    """Return the default list of skill sources.

    Currently only includes the local ``optional-skills/`` directory.
    GitHub and Tap sources are configured at runtime.
    """
    from openharness.skills.hub import OptionalSkillSource
    from openharness.skills.loader import get_user_skills_dir

    optional_dir = get_user_skills_dir()
    return [OptionalSkillSource(optional_dir)]


class SkillsHubTool(BaseTool):
    """Search, install, update, and manage skills from Skills Hub."""

    name = "skills_hub"
    description = "Search, install, update, and manage skills from Skills Hub."
    input_model = SkillsHubInput

    def is_read_only(self, arguments: SkillsHubInput) -> bool:
        """Read-only for search, check, and audit actions."""
        return arguments.action in {"search", "check", "audit"}

    async def execute(
        self, arguments: SkillsHubInput, context: ToolExecutionContext
    ) -> ToolResult:
        """Dispatch to the appropriate hub operation."""
        action = arguments.action
        try:
            if action == "search":
                return await self._do_search(arguments)
            elif action == "install":
                return await self._do_install(arguments)
            elif action == "check":
                return await self._do_check()
            elif action == "update":
                return await self._do_update(arguments)
            elif action == "uninstall":
                return self._do_uninstall(arguments)
            elif action == "audit":
                return self._do_audit()
            else:
                return ToolResult(
                    output=f"Unknown action: {action!r}. "
                    "Supported: search, install, check, update, uninstall, audit.",
                    is_error=True,
                )
        except Exception as exc:
            logger.exception("skills_hub %s failed", action)
            return ToolResult(output=str(exc), is_error=True)

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    async def _do_search(self, arguments: SkillsHubInput) -> ToolResult:
        from openharness.skills.hub import parallel_search_sources

        query = arguments.query or ""
        sources = default_sources()
        results = await parallel_search_sources(query, sources)
        if not results:
            return ToolResult(output="No skills found.")
        lines = [f"Found {len(results)} skill(s):"]
        for meta in results:
            lines.append(
                f"  - {meta.name} [{meta.source}] ({meta.identifier}): "
                f"{meta.description}"
            )
        return ToolResult(output="\n".join(lines))

    async def _do_install(self, arguments: SkillsHubInput) -> ToolResult:
        from openharness.skills.hub import install_skill

        if not arguments.name:
            return ToolResult(
                output="'name' is required for install action.",
                is_error=True,
            )
        sources = default_sources()
        msg = await install_skill(
            arguments.name, sources, force=arguments.force
        )
        return ToolResult(output=msg)

    async def _do_check(self) -> ToolResult:
        from openharness.skills.hub import check_for_skill_updates

        sources = default_sources()
        updates = await check_for_skill_updates(sources)
        if not updates:
            return ToolResult(output="All installed skills are up to date.")
        lines = [f"{len(updates)} skill(s) have updates available:"]
        for u in updates:
            lines.append(f"  - {u['name']} (source: {u['source']})")
        return ToolResult(output="\n".join(lines))

    async def _do_update(self, arguments: SkillsHubInput) -> ToolResult:
        from openharness.skills.hub import update_skill

        if not arguments.name:
            return ToolResult(
                output="'name' is required for update action.",
                is_error=True,
            )
        sources = default_sources()
        msg = await update_skill(arguments.name, sources)
        return ToolResult(output=msg)

    def _do_uninstall(self, arguments: SkillsHubInput) -> ToolResult:
        from openharness.skills.hub import uninstall_skill

        if not arguments.name:
            return ToolResult(
                output="'name' is required for uninstall action.",
                is_error=True,
            )
        msg = uninstall_skill(arguments.name)
        return ToolResult(output=msg)

    def _do_audit(self) -> ToolResult:
        from openharness.skills.hub import ensure_hub_dirs

        _, audit_dir = ensure_hub_dirs()
        log_path = audit_dir / "skills-audit.log"
        if not log_path.exists():
            return ToolResult(output="No audit log entries found.")
        try:
            text = log_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            return ToolResult(
                output=f"Failed to read audit log: {exc}",
                is_error=True,
            )
        if not text:
            return ToolResult(output="No audit log entries found.")
        # Return the most recent entries (last 50 lines)
        lines = text.splitlines()
        recent = lines[-50:]
        return ToolResult(
            output=f"Audit log ({len(lines)} total entries, showing last {len(recent)}):\n"
            + "\n".join(recent)
        )
