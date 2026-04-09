"""Skill loading from bundled and user directories."""

from __future__ import annotations

from pathlib import Path

from openharness.config.paths import get_config_dir
from openharness.config.settings import load_settings
from openharness.skills.bundled import get_bundled_skills
from openharness.skills.helpers import build_skill_definition
from openharness.skills.registry import SkillRegistry
from openharness.skills.types import SkillDefinition


def get_user_skills_dir() -> Path:
    """Return the user skills directory."""
    path = get_config_dir() / "skills"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_skill_registry(cwd: str | Path | None = None) -> SkillRegistry:
    """Load bundled and user-defined skills."""
    registry = SkillRegistry()
    for skill in get_bundled_skills():
        registry.register(skill)
    for skill in load_user_skills():
        registry.register(skill)
    if cwd is not None:
        from openharness.plugins.loader import load_plugins

        settings = load_settings()
        for plugin in load_plugins(settings, cwd):
            if not plugin.enabled:
                continue
            for skill in plugin.skills:
                registry.register(skill)
    return registry


def load_user_skills() -> list[SkillDefinition]:
    """加载用户技能。

    兼容两种格式：
    1. 旧版平铺文件：`skills/foo.md`
    2. Hermes 风格目录：`skills/foo/SKILL.md`
    """

    skills: list[SkillDefinition] = []
    skills_dir = get_user_skills_dir()

    for path in _iter_user_skill_files(skills_dir):
        content = path.read_text(encoding="utf-8")
        skills.append(build_skill_definition(path=path, content=content, source="user"))

    return skills


def _iter_user_skill_files(skills_dir: Path) -> list[Path]:
    """返回用户技能文件列表，并避免重复扫描。"""

    discovered: dict[Path, None] = {}

    for path in sorted(skills_dir.glob("*.md")):
        discovered[path.resolve()] = None

    for path in sorted(skills_dir.rglob("SKILL.md")):
        discovered[path.resolve()] = None

    return sorted(discovered.keys())
