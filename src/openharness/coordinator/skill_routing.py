"""领域 skill 到 domain agent 的路由表。

这个模块只做“谁负责哪类 skill”的稳定映射，避免协调层把所有 supplier skill
都摊平成平台能力。domain agent 负责同域 skill 调度，shared decision core 负责
跨域 bundle 决策。
"""

from __future__ import annotations

# 本仓库当前只打通这四个领域；后续扩展新领域时，优先在这里扩映射。
DOMAIN_SKILL_MAP: dict[str, tuple[str, ...]] = {
    "local-life-agent": (
        "meituan",
        "meituan-hot-trend",
        "meituan-coupon-auto",
    ),
    "coupon-agent": (
        "coupon",
        "coupons",
        "obtain-coupons-all-in-one",
        "obtain-takeout-coupon",
    ),
    "travel-agent": (
        "tripgenie",
        "stayforge-api",
        "tuniu-hotel",
    ),
    "flight-agent": (
        "cabin",
        "flight-search-fast",
    ),
}

# 这些 skill 属于更敏感的内部供应链能力，默认不能由公开模式路由出去。
INTERNAL_ONLY_SKILLS: frozenset[str] = frozenset(
    {
        "coupons",
        "obtain-coupons-all-in-one",
        "obtain-takeout-coupon",
        "tuniu-hotel",
    }
)


def _normalize_skill_slug(skill_name: str) -> str:
    """把 `skillhub/meituan` 这类 identifier 归一成纯 slug，方便路由判断。"""
    slug = skill_name.strip().lower()
    if "/" in slug:
        slug = slug.split("/", 1)[-1]
    return slug


def resolve_agent_for_skill(skill_name: str, *, internal_mode: bool = False) -> str | None:
    """根据 skill slug 找到应该处理它的 domain agent。

    默认模式下，内部 skill 直接返回 ``None``，避免协调层误把敏感 skill 暴露出去。
    """
    slug = _normalize_skill_slug(skill_name)
    for agent_name, skill_slugs in DOMAIN_SKILL_MAP.items():
        if slug not in skill_slugs:
            continue
        if slug in INTERNAL_ONLY_SKILLS and not internal_mode:
            return None
        return agent_name
    return None


def resolve_skills_for_agent(agent_name: str, *, internal_mode: bool = False) -> list[str]:
    """返回某个 domain agent 应该承接的 skill 列表。"""
    skill_slugs = list(DOMAIN_SKILL_MAP.get(agent_name, ()))
    if internal_mode:
        return skill_slugs
    return [slug for slug in skill_slugs if slug not in INTERNAL_ONLY_SKILLS]
