#!/usr/bin/env python3
"""SkillHub 分域联调 smoke 脚本。

它会做三件事：
1. 访问真实 SkillHub，验证公开 / 内部 skill 的搜索与下载。
2. 检查 domain skill 到 domain agent 的稳定路由。
3. 生成一份可审阅的 markdown 报告，写入 smart-travel-workspace。
"""

from __future__ import annotations

import argparse
import asyncio
import platform
from datetime import datetime, timezone
from pathlib import Path

from openharness.coordinator.agent_definitions import get_builtin_agent_definitions
from openharness.coordinator.skill_routing import (
    DOMAIN_SKILL_MAP,
    resolve_agent_for_skill,
    resolve_skills_for_agent,
)
from openharness.skills.skillhub_source import SkillHubSource
from openharness.tools.skills_hub_tool import default_sources

DEFAULT_OUTPUT = Path(
    "/Users/apus/Documents/UGit/smart-travel-workspace/output/"
    "skillhub-domain-agent-smoke-report.md"
)


def _format_identifiers(items) -> str:
    """把 SkillMeta 列表格式化成便于审阅的 markdown 项目符号。"""
    if not items:
        return "- （无结果）"
    return "\n".join(f"- `{item.identifier}` — {item.name} / {item.description}" for item in items)


def _format_skills(skills: list[str]) -> str:
    """把 skill slug 列表压成一行，便于报告查看。"""
    return ", ".join(f"`{skill}`" for skill in skills) or "（无）"


async def _collect_smoke_lines() -> list[str]:
    """收集真实 SkillHub 联调结果，并返回 markdown 行列表。"""
    public_source = SkillHubSource()
    internal_source = SkillHubSource(internal_mode=True)

    lines: list[str] = []
    errors: list[str] = []

    lines.extend(
        [
            "# SkillHub Domain Agent Smoke Report",
            "",
            f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
            f"- Python: {platform.python_version()} ({platform.machine()})",
            "",
        ]
    )

    source_ids = [src.source_id() for src in default_sources()]
    lines.append("## Default Sources")
    lines.append(f"- {', '.join(source_ids) if source_ids else '（空）'}")
    if source_ids[:1] != ["skillhub"]:
        errors.append(f"default_sources() did not place skillhub first: {source_ids}")
    lines.append("")

    lines.append("## Public SkillHub Search")
    for query in ("coupon", "meituan", "tripgenie", "flight"):
        try:
            results = await public_source.search(query)
            lines.append(f"### Query: `{query}`")
            lines.append(_format_identifiers(results))
            lines.append("")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"public search failed for {query}: {exc}")
            lines.append(f"### Query: `{query}`")
            lines.append(f"- ERROR: {exc}")
            lines.append("")

    lines.append("## Internal SkillHub Search")
    for query in ("coupon", "hotel"):
        try:
            results = await internal_source.search(query)
            lines.append(f"### Query: `{query}`")
            lines.append(_format_identifiers(results))
            lines.append("")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"internal search failed for {query}: {exc}")
            lines.append(f"### Query: `{query}`")
            lines.append(f"- ERROR: {exc}")
            lines.append("")

    lines.append("## Fetch Checks")
    for slug in ("meituan", "tuniu-hotel"):
        try:
            bundle = await internal_source.fetch(slug)
            lines.append(f"### `{slug}`")
            lines.append(f"- bundle name: `{bundle.name}`")
            lines.append(f"- identifier: `{bundle.identifier}`")
            lines.append(f"- content hash: `{bundle.content_hash}`")
            lines.append(f"- files: {', '.join(sorted(bundle.files))}")
            lines.append("")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"fetch failed for {slug}: {exc}")
            lines.append(f"### `{slug}`")
            lines.append(f"- ERROR: {exc}")
            lines.append("")

    lines.append("## Routing Checks")
    routing_samples = ("meituan", "coupon", "tripgenie", "cabin", "tuniu-hotel")
    for slug in routing_samples:
        agent = resolve_agent_for_skill(slug, internal_mode=True)
        lines.append(f"- `{slug}` → `{agent}`")
    lines.append("")

    lines.append("## Domain Agent Skill Bundles")
    for agent_name in DOMAIN_SKILL_MAP:
        public_skills = resolve_skills_for_agent(agent_name, internal_mode=False)
        full_skills = resolve_skills_for_agent(agent_name, internal_mode=True)
        lines.append(f"### `{agent_name}`")
        lines.append(f"- public: {_format_skills(public_skills)}")
        lines.append(f"- internal: {_format_skills(full_skills)}")
        lines.append("")

    lines.append("## Built-in Agents")
    builtins = {agent.name: agent for agent in get_builtin_agent_definitions()}
    for agent_name in DOMAIN_SKILL_MAP:
        agent = builtins.get(agent_name)
        if agent is None:
            errors.append(f"missing builtin agent: {agent_name}")
            lines.append(f"- `{agent_name}`: MISSING")
            continue
        lines.append(f"- `{agent_name}`: skills={_format_skills(agent.skills)}")
    lines.append("")

    lines.append("## Result")
    if errors:
        lines.append("PARTIAL")
        lines.append("")
        lines.append("### Issues")
        for error in errors:
            lines.append(f"- {error}")
    else:
        lines.append("PASS")

    return lines


def _write_report(output_path: Path, lines: list[str]) -> None:
    """把 smoke 结果写到指定 markdown 文件。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _report_succeeded(lines: list[str]) -> bool:
    """根据报告最后一个非空结果行判断这次 smoke 是否成功。"""
    for line in reversed(lines):
        status = line.strip()
        if not status:
            continue
        return status == "PASS"
    return False


async def _main(output_path: Path) -> int:
    """执行 smoke 流程，并返回适合进程退出的状态码。"""
    lines = await _collect_smoke_lines()
    _write_report(output_path, lines)
    return 0 if _report_succeeded(lines) else 1


def main() -> int:
    """命令行入口：支持自定义报告路径。"""
    parser = argparse.ArgumentParser(description="Run SkillHub domain smoke checks.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Smoke 报告输出路径（markdown）",
    )
    args = parser.parse_args()
    return asyncio.run(_main(Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())
