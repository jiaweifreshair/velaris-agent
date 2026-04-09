"""Skill registry."""

from __future__ import annotations

from openharness.skills.helpers import normalize_skill_slug
from openharness.skills.types import SkillDefinition


class SkillRegistry:
    """Store loaded skills by name."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}
        self._aliases: dict[str, str] = {}

    def register(self, skill: SkillDefinition) -> None:
        """Register one skill."""
        self._skills[skill.name] = skill
        self._aliases[skill.name.lower()] = skill.name
        if skill.slug:
            self._aliases[skill.slug] = skill.name

    def get(self, name: str) -> SkillDefinition | None:
        """Return a skill by name."""
        direct = self._skills.get(name)
        if direct is not None:
            return direct
        canonical = self._aliases.get(name.lower()) or self._aliases.get(normalize_skill_slug(name))
        if canonical is None:
            return None
        return self._skills.get(canonical)

    def list_skills(self) -> list[SkillDefinition]:
        """Return all skills sorted by name."""
        return sorted(self._skills.values(), key=lambda skill: skill.name)
