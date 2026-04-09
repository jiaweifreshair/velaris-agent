"""CLAUDE.md discovery and loading."""

from __future__ import annotations

from pathlib import Path

from openharness.security import scan_context_content, truncate_context_content


def discover_claude_md_files(cwd: str | Path) -> list[Path]:
    """发现项目指令文件，兼容 CLAUDE.md / AGENTS.md / Cursor 规则文件。"""

    current = Path(cwd).resolve()
    results: list[Path] = []
    seen: set[Path] = set()

    for directory in [current, *current.parents]:
        for candidate in (
            directory / "AGENTS.md",
            directory / "agents.md",
            directory / "CLAUDE.md",
            directory / ".claude" / "CLAUDE.md",
            directory / ".cursorrules",
        ):
            if candidate.exists() and candidate not in seen:
                results.append(candidate)
                seen.add(candidate)

        rules_dir = directory / ".claude" / "rules"
        if rules_dir.is_dir():
            for rule in sorted(rules_dir.glob("*.md")):
                if rule not in seen:
                    results.append(rule)
                    seen.add(rule)

        cursor_rules_dir = directory / ".cursor" / "rules"
        if cursor_rules_dir.is_dir():
            for pattern in ("*.md", "*.mdc"):
                for rule in sorted(cursor_rules_dir.glob(pattern)):
                    if rule not in seen:
                        results.append(rule)
                        seen.add(rule)

        if directory.parent == directory:
            break

    return results


def load_claude_md_prompt(
    cwd: str | Path,
    *,
    max_chars_per_file: int = 12000,
    scan_for_injection: bool = True,
) -> str | None:
    """把发现到的项目指令文件加载成单个提示片段，并在注入前做安全扫描。"""

    files = discover_claude_md_files(cwd)
    if not files:
        return None

    cwd_path = Path(cwd).resolve()
    lines = ["# Project Instructions"]
    for path in files:
        content = path.read_text(encoding="utf-8", errors="replace")
        label = str(path)
        try:
            label = str(path.relative_to(cwd_path))
        except ValueError:
            pass
        content = scan_context_content(content, label, enabled=scan_for_injection)
        content = truncate_context_content(
            content.strip(),
            label,
            max_chars=max_chars_per_file,
        )
        lines.extend(["", f"## {path}", "```md", content, "```"])
    return "\n".join(lines)
