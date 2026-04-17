"""Property-based integration tests for skill-self-update using Hypothesis.

Tests cover:
- Property 14: Hub-installed skill discoverable by registry
- Property 15: Manual skill does not affect lock file
"""

from __future__ import annotations

from unittest.mock import patch

# Pre-import to resolve circular dependency chain:
# config/__init__ -> config.settings -> api.registry -> api/__init__ -> api.provider -> config.settings
import openharness.config.paths  # noqa: F401  (side-effect: no circular dep)
import openharness.api.registry  # noqa: F401  (side-effect: loads api.provider -> config.settings)

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from openharness.skills.loader import load_skill_registry
from openharness.skills.lock import HubLockFile


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid skill slug: lowercase alnum with dashes, suitable for directory names
_skill_slug_st = st.from_regex(r"[a-z][a-z0-9-]{1,20}", fullmatch=True)

# Skill name for frontmatter: at least 2 chars to avoid edge cases with
# single-char names colliding with bundled skill slugs
_skill_name_st = st.from_regex(r"[A-Za-z][A-Za-z0-9 _-]{1,30}", fullmatch=True)

# Description that YAML will always parse as a string (must start with a
# letter so yaml.safe_load doesn't coerce it to int/float/bool/None).
_description_st = st.from_regex(r"[A-Za-z][A-Za-z0-9 ,._-]{4,60}", fullmatch=True)

# Title line for the markdown body
_title_st = st.from_regex(r"[A-Za-z][A-Za-z0-9 ]{1,30}", fullmatch=True)

# Body content
_body_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Z"), whitelist_characters="-_,.!"),
    min_size=1,
    max_size=120,
)


@st.composite
def _skill_md_content(draw: st.DrawFn) -> tuple[str, str, str]:
    """Generate (slug, frontmatter_name, full SKILL.md content).

    The description always starts with a letter so YAML parses it as a
    string, preventing the fallback path from overwriting the name.
    """
    slug = draw(_skill_slug_st)
    name = draw(_skill_name_st)
    description = draw(_description_st)
    title = draw(_title_st)
    body = draw(_body_st)
    content = f"---\nname: {name}\ndescription: {description}\n---\n# {title}\n{body}\n"
    return slug, name, content


# ---------------------------------------------------------------------------
# Property 14: Hub-installed skill discoverable by registry
# Feature: skill-self-update, Property 14: Hub-installed skill discoverable by registry
# ---------------------------------------------------------------------------


class TestProperty14HubInstalledSkillDiscoverable:
    """**Validates: Requirements 11.2**"""

    @settings(max_examples=100, deadline=None)
    @given(data=_skill_md_content())
    def test_skill_md_in_user_dir_discovered_by_registry(
        self,
        data: tuple[str, str, str],
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        # Feature: skill-self-update, Property 14: Hub-installed skill discoverable by registry
        slug, expected_name, content = data
        tmp_path = tmp_path_factory.mktemp("prop14")

        # Set up user skills directory with <slug>/SKILL.md
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / slug
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

        with (
            patch("openharness.skills.loader.get_user_skills_dir", return_value=skills_dir),
            patch("openharness.config.paths.get_config_dir", return_value=tmp_path),
        ):
            registry = load_skill_registry()

        # The skill should be discoverable by its frontmatter name
        skill = registry.get(expected_name)
        assert skill is not None, (
            f"Skill '{expected_name}' not found in registry. "
            f"Available: {[s.name for s in registry.list_skills()]}"
        )
        assert skill.source == "user"


# ---------------------------------------------------------------------------
# Property 15: Manual skill does not affect lock file
# Feature: skill-self-update, Property 15: Manual skill does not affect lock file
# ---------------------------------------------------------------------------


class TestProperty15ManualSkillDoesNotAffectLockFile:
    """**Validates: Requirements 11.4**"""

    @settings(max_examples=100, deadline=None)
    @given(data=_skill_md_content())
    def test_manual_skill_leaves_lock_file_unchanged(
        self,
        data: tuple[str, str, str],
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        # Feature: skill-self-update, Property 15: Manual skill does not affect lock file
        slug, _name, content = data
        tmp_path = tmp_path_factory.mktemp("prop15")

        # Set up directories
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        # Create lock file and snapshot its content before manual skill creation
        lock_path = skills_dir / "lock.json"
        lock = HubLockFile(lock_path)
        # Ensure lock file exists with empty state
        lock.save({})
        lock_before = lock_path.read_text(encoding="utf-8")

        # Simulate manual skill creation: write SKILL.md directly
        skill_dir = skills_dir / slug
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

        # Load registry (which scans user skills dir) — this should NOT touch lock file
        with (
            patch("openharness.skills.loader.get_user_skills_dir", return_value=skills_dir),
            patch("openharness.config.paths.get_config_dir", return_value=tmp_path),
        ):
            load_skill_registry()

        # Verify lock file content is unchanged
        lock_after = lock_path.read_text(encoding="utf-8")
        assert lock_before == lock_after, (
            "Lock file was modified after manual skill creation and registry load"
        )
