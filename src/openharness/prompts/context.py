"""Higher-level system prompt assembly."""

from __future__ import annotations

from pathlib import Path

from openharness.config.paths import get_project_issue_file, get_project_pr_comments_file
from openharness.config.settings import Settings
from openharness.memory import find_relevant_memories, load_memory_prompt
from openharness.prompts.claudemd import load_claude_md_prompt
from openharness.prompts.system_prompt import build_system_prompt
from openharness.security import scan_context_content, truncate_context_content
from openharness.skills.prompt_index import build_skills_system_prompt


def build_runtime_system_prompt(
    settings: Settings,
    *,
    cwd: str | Path,
    latest_user_prompt: str | None = None,
) -> str:
    """Build the runtime system prompt with project instructions and memory."""
    sections = [build_system_prompt(custom_prompt=settings.system_prompt, cwd=str(cwd))]

    if settings.fast_mode:
        sections.append(
            "# Session Mode\nFast mode is enabled. Prefer concise replies, minimal tool use, and quicker progress over exhaustive exploration."
        )

    sections.append(
        "# Reasoning Settings\n"
        f"- Effort: {settings.effort}\n"
        f"- Passes: {settings.passes}\n"
        "Adjust depth and iteration count to match these settings while still completing the task."
    )

    skills_section = None
    if settings.skills.enabled:
        skills_section = build_skills_system_prompt(
            cwd,
            max_entries=settings.skills.max_index_entries,
        )
    if skills_section:
        sections.append(skills_section)

    claude_md = load_claude_md_prompt(
        cwd,
        scan_for_injection=settings.security.scan_project_instructions,
    )
    if claude_md:
        sections.append(claude_md)

    for title, path in (
        ("Issue Context", get_project_issue_file(cwd)),
        ("Pull Request Comments", get_project_pr_comments_file(cwd)),
    ):
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            if content:
                content = scan_context_content(
                    content,
                    title,
                    enabled=settings.security.scan_project_instructions,
                )
                content = truncate_context_content(content, title, max_chars=12000)
                sections.append(f"# {title}\n\n```md\n{content[:12000]}\n```")

    if settings.memory.enabled:
        memory_section = load_memory_prompt(
            cwd,
            max_entrypoint_lines=settings.memory.max_entrypoint_lines,
        )
        if memory_section:
            sections.append(memory_section)

        if latest_user_prompt:
            relevant = find_relevant_memories(
                latest_user_prompt,
                cwd,
                max_results=settings.memory.max_files,
            )
            if relevant:
                lines = ["# Relevant Memories"]
                for header in relevant:
                    content = header.path.read_text(encoding="utf-8", errors="replace").strip()
                    lines.extend(
                        [
                            "",
                            f"## {header.path.name}",
                            "```md",
                            content[:8000],
                            "```",
                        ]
                    )
                sections.append("\n".join(lines))

    return "\n\n".join(section for section in sections if section.strip())
