"""Skills 系统提示索引构建。

目标：
1. 系统提示只注入“技能名 + 描述”的轻量索引；
2. 完整技能内容通过 `skill` 工具或 `/skill-name` 动态按需加载；
3. 在进程内缓存索引，避免每轮都重复解析所有技能文件。
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from openharness.skills import load_skill_registry

_SKILLS_PROMPT_CACHE_MAX = 16
_SKILLS_PROMPT_CACHE: OrderedDict[tuple[str, tuple[tuple[str, int, int], ...]], str] = OrderedDict()

SKILLS_GUIDANCE = (
    "After completing a complex task (5+ tool calls), fixing a tricky error, "
    "or discovering a non-trivial workflow, save the approach as a skill with "
    "skill_manage so you can reuse it next time.\n"
    "When using a skill and finding it outdated, incomplete, or wrong, patch it "
    "immediately with skill_manage(action='patch') instead of leaving stale guidance behind."
)


def clear_skills_system_prompt_cache() -> None:
    """清空技能索引缓存。"""

    _SKILLS_PROMPT_CACHE.clear()


def build_skills_system_prompt(cwd: str | Path, *, max_entries: int = 200) -> str | None:
    """构建技能索引型系统提示。

    这是 Hermes 风格的 Level-0 加载：只注入技能目录索引，不直接塞入完整内容。
    """

    registry = load_skill_registry(cwd)
    skills = registry.list_skills()
    if not skills:
        return None

    manifest = tuple(
        sorted(
            (
                str(skill.path or skill.name),
                int(Path(skill.path).stat().st_mtime_ns) if skill.path and Path(skill.path).exists() else 0,
                int(Path(skill.path).stat().st_size) if skill.path and Path(skill.path).exists() else 0,
            )
            for skill in skills
        )
    )
    cache_key = (str(Path(cwd).resolve()), manifest)
    cached = _SKILLS_PROMPT_CACHE.get(cache_key)
    if cached is not None:
        _SKILLS_PROMPT_CACHE.move_to_end(cache_key)
        return cached

    lines = [
        "# Skills",
        "",
        SKILLS_GUIDANCE,
        "",
        "Before replying, scan the available skills below. If one clearly matches the task, "
        "load it with `skill(name=\"<skill_name>\")` or invoke it via `/skill-name` so the full "
        "instructions are injected on demand instead of bloating the system prompt.",
        "",
        "<available_skills>",
    ]

    for skill in skills[:max_entries]:
        lines.append(f"- {skill.name}: {skill.description}")

    if len(skills) > max_entries:
        lines.append(f"- ... truncated {len(skills) - max_entries} additional skills")

    lines.extend(
        [
            "</available_skills>",
            "",
            "If no skill matches, proceed normally. If a skill proves stale while executing, "
            "update it before you finish the task.",
        ]
    )
    result = "\n".join(lines)

    _SKILLS_PROMPT_CACHE[cache_key] = result
    _SKILLS_PROMPT_CACHE.move_to_end(cache_key)
    while len(_SKILLS_PROMPT_CACHE) > _SKILLS_PROMPT_CACHE_MAX:
        _SKILLS_PROMPT_CACHE.popitem(last=False)
    return result
