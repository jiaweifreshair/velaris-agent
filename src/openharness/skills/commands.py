"""Skills 动态命令支持。"""

from __future__ import annotations

from pathlib import Path

from openharness.skills import load_skill_registry
from openharness.skills.helpers import normalize_skill_slug
from openharness.skills.types import SkillDefinition

_ALLOWED_SUPPORT_DIRS = {"references", "templates", "scripts", "assets"}


def resolve_skill_command(command_name: str, cwd: str | Path) -> SkillDefinition | None:
    """把 `/skill-name` 解析到具体技能。"""

    slug = normalize_skill_slug(command_name.lstrip("/"))
    registry = load_skill_registry(cwd)
    for skill in registry.list_skills():
        if skill.slug == slug:
            return skill
    return None


def build_skill_invocation_message(
    skill: SkillDefinition,
    *,
    user_instruction: str = "",
) -> str:
    """构造技能动态加载消息。

    该消息作为用户消息注入，而不是放回系统提示，避免破坏 prefix caching。
    """

    parts = [
        f'[SYSTEM: 用户显式调用了技能 "{skill.name}"，你必须先遵循该技能说明再继续执行。]',
        "",
        skill.content.strip(),
    ]

    support_files = list_skill_support_files(skill)
    if support_files:
        parts.extend(
            [
                "",
                "[该技能还有支持文件，可按需通过 `skill(name=..., file_path=...)` 继续读取：]",
            ]
        )
        parts.extend(f"- {path}" for path in support_files)

    if user_instruction.strip():
        parts.extend(
            [
                "",
                f"用户随技能一起提供的补充要求：{user_instruction.strip()}",
            ]
        )

    return "\n".join(parts)


def list_skill_support_files(skill: SkillDefinition) -> list[str]:
    """列出技能目录下允许暴露的支持文件。"""

    if not skill.skill_dir:
        return []
    skill_dir = Path(skill.skill_dir)
    if not skill_dir.exists():
        return []

    results: list[str] = []
    for subdir in sorted(_ALLOWED_SUPPORT_DIRS):
        root = skill_dir / subdir
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file():
                results.append(str(path.relative_to(skill_dir)))
    return results
