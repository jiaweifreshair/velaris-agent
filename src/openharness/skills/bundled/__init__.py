"""Bundled skill definitions loaded from .md files."""

from __future__ import annotations

from pathlib import Path

from openharness.skills.helpers import build_skill_definition
from openharness.skills.types import SkillDefinition

_CONTENT_DIR = Path(__file__).parent / "content"


def get_bundled_skills() -> list[SkillDefinition]:
    """Load all bundled skills from the content/ directory."""
    skills: list[SkillDefinition] = []
    if not _CONTENT_DIR.exists():
        return skills
    for path in sorted(_CONTENT_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        skills.append(build_skill_definition(path=path, content=content, source="bundled"))
    return skills
