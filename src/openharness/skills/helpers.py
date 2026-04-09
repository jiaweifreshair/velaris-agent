"""Skills 解析与命名辅助函数。"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from openharness.skills.types import SkillDefinition

_SKILL_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_SKILL_SLUG_CLEAN_RE = re.compile(r"[^a-z0-9._-]+")


def normalize_skill_slug(name: str) -> str:
    """把技能名规整为稳定 slug。

    该 slug 用于目录名和 `/skill-name` 动态命令，避免空格和大小写差异造成重复。
    """

    lowered = name.strip().lower().replace(" ", "-").replace("_", "-")
    normalized = _SKILL_SLUG_CLEAN_RE.sub("-", lowered).strip("-")
    return normalized or "skill"


def parse_skill_markdown(default_name: str, content: str) -> tuple[str, str]:
    """从技能 Markdown 中解析 name 和 description。

    优先读取 YAML frontmatter；没有 frontmatter 时回退到标题和首段正文。
    """

    name = default_name
    description = ""

    match = _SKILL_FRONTMATTER_RE.match(content)
    if match:
        yaml_block, body = match.groups()
        try:
            parsed = yaml.safe_load(yaml_block) or {}
        except yaml.YAMLError:
            parsed = {}
        if isinstance(parsed, dict):
            raw_name = parsed.get("name")
            raw_description = parsed.get("description")
            if isinstance(raw_name, str) and raw_name.strip():
                name = raw_name.strip()
            if isinstance(raw_description, str) and raw_description.strip():
                description = raw_description.strip()
        if description:
            return name, description
        content_for_fallback = body
    else:
        content_for_fallback = content

    for line in content_for_fallback.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            heading = stripped[2:].strip()
            if heading:
                name = heading
            continue
        if stripped and not stripped.startswith("#"):
            description = stripped[:200]
            break

    return name, description or f"Skill: {name}"


def build_skill_definition(
    *,
    path: Path,
    content: str,
    source: str,
) -> SkillDefinition:
    """根据技能文件生成统一的 SkillDefinition。"""

    default_name = path.parent.name if path.name == "SKILL.md" else path.stem
    name, description = parse_skill_markdown(default_name, content)
    skill_dir = path.parent if path.name == "SKILL.md" else None
    return SkillDefinition(
        name=name,
        description=description,
        content=content,
        source=source,
        path=str(path),
        slug=normalize_skill_slug(name),
        skill_dir=str(skill_dir) if skill_dir is not None else None,
    )
