"""Tests for the skill-creator bundled skill.

Validates: Requirements 8.1, 8.2, 8.4
"""

from __future__ import annotations

from pathlib import Path

import yaml

from openharness.skills.bundled import get_bundled_skills
from openharness.skills.helpers import parse_skill_markdown
from openharness.skills.loader import load_skill_registry


_SKILL_CREATOR_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "openharness"
    / "skills"
    / "bundled"
    / "content"
    / "skill-creator.md"
)


def _read_skill_creator() -> str:
    return _SKILL_CREATOR_PATH.read_text(encoding="utf-8")


# --- Frontmatter parsing (Requirement 8.2) ---


def test_frontmatter_has_valid_yaml():
    """The skill-creator.md file should have parseable YAML frontmatter."""
    content = _read_skill_creator()
    assert content.startswith("---"), "File must start with YAML frontmatter delimiter"
    end = content.index("---", 3)
    yaml_block = content[4:end]
    parsed = yaml.safe_load(yaml_block)
    assert isinstance(parsed, dict)


def test_frontmatter_name_is_skill_creator():
    """Frontmatter name field must be 'skill-creator'."""
    content = _read_skill_creator()
    name, _ = parse_skill_markdown("fallback", content)
    assert name == "skill-creator"


def test_frontmatter_has_description():
    """Frontmatter must include a non-empty description."""
    content = _read_skill_creator()
    _, description = parse_skill_markdown("fallback", content)
    assert description, "description must not be empty"
    assert len(description) > 10, "description should be meaningful"


# --- Registry discovery (Requirements 8.1, 8.4) ---


def test_bundled_skills_include_skill_creator():
    """get_bundled_skills() must return a skill named 'skill-creator'."""
    skills = get_bundled_skills()
    names = [s.name for s in skills]
    assert "skill-creator" in names


def test_load_skill_registry_includes_skill_creator(tmp_path: Path, monkeypatch):
    """load_skill_registry() must discover 'skill-creator'."""
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = load_skill_registry()
    skill = registry.get("skill-creator")
    assert skill is not None
    assert skill.source == "bundled"


# --- Content structure (Requirement 8.4) ---


def test_content_contains_five_phase_section():
    """Skill content must describe the Five-Phase guided flow."""
    content = _read_skill_creator()
    assert "Five-Phase" in content or "five-phase" in content.lower()


def test_content_contains_skill_file_format_section():
    """Skill content must describe the Skill File Format."""
    content = _read_skill_creator()
    assert "Skill File Format" in content


def test_content_contains_frontmatter_fields_spec():
    """Skill content must document required frontmatter fields (name, description)."""
    content = _read_skill_creator()
    # The spec section should mention mandatory fields
    assert "name" in content
    assert "description" in content
