"""SkillHub 内部演示台支持。

这个模块把三件事收拢到一处：
1. 预装本次 demo 需要的真实 SkillHub skills；
2. 提供给 CLI / 前端的 demo case 元数据；
3. 生成可保存到 smart-travel-workspace 的 markdown 演示页。
"""

from __future__ import annotations
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openharness.coordinator.skill_routing import resolve_agent_for_skill, resolve_skills_for_agent
from openharness.skills.hub import HubLockFile, OptionalSkillSource, install_skill
from openharness.skills.loader import get_user_skills_dir
from openharness.skills.skillhub_source import INTERNAL_SKILL_SLUGS, PUBLIC_SKILL_SLUGS, SkillHubSource

logger = logging.getLogger(__name__)

# 默认把演示页写到 smart-travel-workspace，方便和图产物放在一起审阅。
DEFAULT_DEMO_OUTPUT = Path(
    "/Users/apus/Documents/UGit/smart-travel-workspace/output/"
    "skillhub-domain-agent-demo-page.md"
)


@dataclass(frozen=True)
class SkillHubDemoCase:
    """一个可展示给内部演示台的 demo case。"""

    case_id: str
    title: str
    query: str
    skill_slugs: tuple[str, ...]
    route_agents: tuple[str, ...]
    description: str
    internal_only: bool = False


_DEMO_CASES: tuple[SkillHubDemoCase, ...] = (
    SkillHubDemoCase(
        case_id="local-life",
        title="送机前买花",
        query="帮我在机场附近找 3 家美团花店，预算 300，送机前 30 分钟能取。",
        skill_slugs=("meituan", "meituan-hot-trend", "meituan-coupon-auto"),
        route_agents=("local-life-agent",),
        description="真实美团技能负责商家与优惠信息检索，演示本地生活域如何被 domain agent 接住。",
    ),
    SkillHubDemoCase(
        case_id="coupon",
        title="优惠券聚合",
        query="帮我找外卖和通用电商优惠券，优先高额券。",
        skill_slugs=("coupon", "coupons", "obtain-coupons-all-in-one", "obtain-takeout-coupon"),
        route_agents=("coupon-agent",),
        description="公开 coupon 技能展示优惠券域基础入口，作为后续券类扩展的起点。",
        internal_only=False,
    ),
    SkillHubDemoCase(
        case_id="travel-bundle",
        title="航班 + 酒店 bundle",
        query="北京到上海出差三天，给我航班和酒店的联合推荐。",
        skill_slugs=("tripgenie", "stayforge-api", "cabin", "flight-search-fast"),
        route_agents=("travel-agent", "flight-agent"),
        description="旅行场景会同时落到酒店 / 航班域，演示协调层先编排，再交给 domain agents。",
    ),
    SkillHubDemoCase(
        case_id="internal-hotel-coupon",
        title="内部酒店优惠",
        query="上海出差，要找一家酒店，同时看看内部优惠券能不能压低总价。",
        skill_slugs=("tuniu-hotel", "coupons"),
        route_agents=("travel-agent", "coupon-agent"),
        description="仅 internal demo 显示：内部酒店与优惠券技能不能默认暴露给公开路径。",
        internal_only=True,
    ),
)


def skillhub_demo_cases(*, include_internal: bool = False) -> list[SkillHubDemoCase]:
    """返回当前 demo 要展示的 case 列表。"""

    if include_internal:
        return list(_DEMO_CASES)
    visible_cases: list[SkillHubDemoCase] = []
    for case in _DEMO_CASES:
        if case.internal_only:
            continue
        visible_cases.append(
            SkillHubDemoCase(
                case_id=case.case_id,
                title=case.title,
                query=case.query,
                skill_slugs=tuple(_visible_skill_slugs(case.skill_slugs, include_internal=False)),
                route_agents=case.route_agents,
                description=case.description,
                internal_only=case.internal_only,
            )
        )
    return visible_cases


def skillhub_demo_case_payloads(*, include_internal: bool = False) -> list[dict[str, Any]]:
    """把 demo case 变成前端可序列化的 payload。"""

    payloads: list[dict[str, Any]] = []
    for case in skillhub_demo_cases(include_internal=include_internal):
        payload = asdict(case)
        payload["skill_slugs"] = _visible_skill_slugs(case.skill_slugs, include_internal=include_internal)
        payload["route_agents"] = list(case.route_agents)
        payloads.append(payload)
    return payloads


def _visible_skill_slugs(skill_slugs: tuple[str, ...], *, include_internal: bool) -> list[str]:
    """按演示模式筛掉不应公开的 skill slug。"""

    if include_internal:
        return list(skill_slugs)
    return [slug for slug in skill_slugs if slug not in INTERNAL_SKILL_SLUGS]


def skillhub_demo_install_targets(*, include_internal: bool = False) -> list[str]:
    """返回 demo 需要预装的 SkillHub slugs。"""

    if include_internal:
        return sorted(PUBLIC_SKILL_SLUGS | INTERNAL_SKILL_SLUGS)
    return sorted(PUBLIC_SKILL_SLUGS)


def _demo_sources(*, include_internal: bool = False) -> list:
    """构造 demo 安装时使用的真实 SkillHub source 列表。"""

    optional_dir = get_user_skills_dir()
    return [SkillHubSource(internal_mode=include_internal), OptionalSkillSource(optional_dir)]


def _installed_skill_names() -> set[str]:
    """读取当前 hub lock，返回已经安装的 skill 名字集合。"""

    lock = HubLockFile()
    list_installed = getattr(lock, "list_installed", None)
    if not callable(list_installed):
        return set()
    try:
        return {entry.name for entry in list_installed()}
    except Exception:
        return set()


async def ensure_skillhub_demo_skills_installed(
    *,
    include_internal: bool = False,
    force: bool = False,
) -> list[str]:
    """确保 demo 需要的真实 SkillHub skills 已经装到本地。

    返回本次实际发生安装 / 更新的 slug 列表。
    """

    sources = _demo_sources(include_internal=include_internal)
    installed_now: list[str] = []
    installed_names = _installed_skill_names()

    for slug in skillhub_demo_install_targets(include_internal=include_internal):
        skill_dir = get_user_skills_dir() / slug
        if not force and slug in installed_names and skill_dir.exists():
            continue
        try:
            await install_skill(slug, sources, force=force)
        except RuntimeError as exc:
            message = str(exc)
            # 公开 demo 会遇到被安全扫描拦住的技能；这类能力保持“不可公开”，
            # 但不应阻断其余真实技能的安装与演示页生成。
            if "blocked by security scan" in message:
                logger.warning("Skip blocked SkillHub skill %s: %s", slug, message)
                continue
            raise
        installed_now.append(slug)

    return installed_now


def build_skillhub_demo_frontend_config(
    *,
    include_internal: bool = False,
    selected_case_index: int = 0,
) -> dict[str, Any]:
    """构造传给前端的 demo 配置。"""

    cases = skillhub_demo_case_payloads(include_internal=include_internal)
    if cases:
        selected_case_index = max(0, min(selected_case_index, len(cases) - 1))
    else:
        selected_case_index = 0

    return {
        "demo_mode": "skillhub",
        "demo_case_index": selected_case_index,
        "demo_cases": cases,
    }


def build_skillhub_demo_prompt(
    *,
    selected_case_index: int = 0,
    include_internal: bool = False,
) -> str:
    """返回进入 demo 时要自动塞给模型的初始 query。"""

    cases = skillhub_demo_cases(include_internal=include_internal)
    if not cases:
        return ""
    selected_case_index = max(0, min(selected_case_index, len(cases) - 1))
    return cases[selected_case_index].query


def build_skillhub_demo_report(
    *,
    include_internal: bool = False,
    selected_case_index: int = 0,
    installed_slugs: list[str] | None = None,
) -> str:
    """生成可写到 smart-travel-workspace 的 markdown 演示页。"""

    cases = skillhub_demo_cases(include_internal=include_internal)
    if cases:
        selected_case_index = max(0, min(selected_case_index, len(cases) - 1))
    else:
        selected_case_index = 0

    installed = _installed_skill_names()
    # 既保留 lock.json 里已经存在的安装状态，也合并本次 ensure 新装的 slug，
    # 这样报告不会把“已有安装”误判成未安装。
    if installed_slugs:
        installed.update(installed_slugs)
    lines: list[str] = [
        "# SkillHub 内部演示台",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- include_internal: {include_internal}",
        f"- selected_case: {selected_case_index + 1 if cases else 0}",
        "",
        "## Domain Agent Map",
    ]

    for agent_name in ("local-life-agent", "coupon-agent", "travel-agent", "flight-agent"):
        skill_slugs = resolve_skills_for_agent(agent_name, internal_mode=include_internal)
        visible = ", ".join(f"`{slug}`" for slug in skill_slugs) or "（空）"
        lines.append(f"- `{agent_name}`: {visible}")

    lines.extend(["", "## Installed SkillHub Skills"])
    for slug in skillhub_demo_install_targets(include_internal=include_internal):
        state = "installed" if slug in installed else "not installed"
        owner = resolve_agent_for_skill(slug, internal_mode=include_internal) or "unrouted"
        lines.append(f"- `{slug}` → `{owner}` ({state})")

    lines.extend(["", "## Demo Cases"])
    for index, case in enumerate(cases, start=1):
        marker = " ← selected" if index - 1 == selected_case_index else ""
        visible_skill_slugs = _visible_skill_slugs(case.skill_slugs, include_internal=include_internal)
        lines.append(f"### {index}. {case.title}{marker}")
        lines.append(f"- case_id: `{case.case_id}`")
        lines.append(f"- query: {case.query}")
        lines.append(f"- route_agents: {', '.join(f'`{agent}`' for agent in case.route_agents)}")
        lines.append(f"- skills: {', '.join(f'`{slug}`' for slug in visible_skill_slugs)}")
        lines.append(f"- internal_only: {'yes' if case.internal_only else 'no'}")
        lines.append(f"- description: {case.description}")
        lines.append("")

    lines.extend(
        [
            "## How To Use",
            "",
            "- 启动 `velaris demo skillhub` 进入这个内部演示台。",
            "- 数字键 1 / 2 / 3 / 4 可切换不同案例。",
            "- 默认会先安装对应的真实 SkillHub skills，再把 query 交给对应 domain agent。",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_skillhub_demo_report(
    output_path: Path | str = DEFAULT_DEMO_OUTPUT,
    *,
    include_internal: bool = False,
    selected_case_index: int = 0,
    installed_slugs: list[str] | None = None,
) -> Path:
    """把 demo 报告写入 markdown 文件。"""

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        build_skillhub_demo_report(
            include_internal=include_internal,
            selected_case_index=selected_case_index,
            installed_slugs=installed_slugs,
        ),
        encoding="utf-8",
    )
    return target
