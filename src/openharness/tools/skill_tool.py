"""Tool for reading skill contents."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from openharness.skills import load_skill_registry
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class SkillToolInput(BaseModel):
    """Arguments for skill lookup."""

    name: str = Field(description="Skill name")
    file_path: str | None = Field(
        default=None,
        description="可选支持文件相对路径；为空时返回 SKILL.md 全文",
    )


class SkillTool(BaseTool):
    """Return the content of a loaded skill."""

    name = "skill"
    description = "Read a bundled, user, or plugin skill by name."
    input_model = SkillToolInput

    def is_read_only(self, arguments: SkillToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: SkillToolInput, context: ToolExecutionContext) -> ToolResult:
        registry = load_skill_registry(context.cwd)
        skill = registry.get(arguments.name)
        if skill is None:
            return ToolResult(output=f"Skill not found: {arguments.name}", is_error=True)
        if not arguments.file_path:
            return ToolResult(output=skill.content)

        if not skill.skill_dir:
            return ToolResult(
                output=f"Skill has no support directory: {arguments.name}",
                is_error=True,
            )

        target = (Path(skill.skill_dir) / arguments.file_path).resolve()
        skill_dir = Path(skill.skill_dir).resolve()
        try:
            target.relative_to(skill_dir)
        except ValueError:
            return ToolResult(output="Invalid skill file path.", is_error=True)
        if not target.exists() or not target.is_file():
            return ToolResult(output=f"Skill file not found: {arguments.file_path}", is_error=True)
        return ToolResult(output=target.read_text(encoding="utf-8"))
