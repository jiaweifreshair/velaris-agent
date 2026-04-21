"""领域 skill 路由规则的单元测试。"""

from __future__ import annotations

from openharness.coordinator.skill_routing import (
    DOMAIN_SKILL_MAP,
    INTERNAL_ONLY_SKILLS,
    resolve_agent_for_skill,
    resolve_skills_for_agent,
)


def test_skill_to_agent_routes_are_stable() -> None:
    assert resolve_agent_for_skill("meituan") == "local-life-agent"
    assert resolve_agent_for_skill("skillhub/meituan") == "local-life-agent"
    assert resolve_agent_for_skill("meituan-coupon-auto") == "local-life-agent"
    assert resolve_agent_for_skill("coupon") == "coupon-agent"
    assert resolve_agent_for_skill("tripgenie") == "travel-agent"
    assert resolve_agent_for_skill("cabin") == "flight-agent"


def test_internal_only_skills_require_internal_mode() -> None:
    assert resolve_agent_for_skill("tuniu-hotel", internal_mode=False) is None
    assert resolve_agent_for_skill("tuniu-hotel", internal_mode=True) == "travel-agent"
    assert resolve_agent_for_skill("coupons", internal_mode=False) is None
    assert resolve_agent_for_skill("coupons", internal_mode=True) == "coupon-agent"


def test_resolve_skills_for_agent_filters_internal_skills() -> None:
    assert resolve_skills_for_agent("travel-agent", internal_mode=False) == [
        "tripgenie",
        "stayforge-api",
    ]
    assert resolve_skills_for_agent("travel-agent", internal_mode=True) == [
        "tripgenie",
        "stayforge-api",
        "tuniu-hotel",
    ]


def test_domain_map_has_expected_agents() -> None:
    assert set(DOMAIN_SKILL_MAP) == {
        "local-life-agent",
        "coupon-agent",
        "travel-agent",
        "flight-agent",
    }
    assert "tuniu-hotel" in INTERNAL_ONLY_SKILLS
