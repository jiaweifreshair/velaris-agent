"""Tests for router.py + ScenarioRegistry 集成。"""

from __future__ import annotations

from pathlib import Path

import pytest

from velaris_agent.scenarios.registry import ScenarioRegistry
from velaris_agent.velaris.router import PolicyRouter


class TestRouterRegistryIntegration:
    """验证 PolicyRouter 使用 registry 查询场景元数据。"""

    @pytest.fixture()
    def router(self) -> PolicyRouter:
        """创建使用默认 registry 的 PolicyRouter。"""
        return PolicyRouter()

    def test_router_uses_registry_risk_level_tokencost(self, router: PolicyRouter) -> None:
        """tokencost 场景 risk_level=low，路由应为低风险。"""
        plan = {
            "scenario": "tokencost",
            "capabilities": ["usage_analyze"],
            "governance": {"requires_audit": False},
        }
        decision = router.route(plan, query="token cost analysis")
        # tokencost 低风险，应走低风险路由
        assert decision.stop_profile in ("fast_fail", "balanced")

    def test_router_uses_registry_risk_level_robotclaw(self, router: PolicyRouter) -> None:
        """robotclaw 场景 risk_level=high，路由应为高风险。"""
        plan = {
            "scenario": "robotclaw",
            "capabilities": ["intent_order", "vehicle_match"],
            "governance": {"requires_audit": True},
        }
        decision = router.route(plan, query="dispatch proposal")
        # robotclaw 高风险+需审计，应走 strict_approval
        assert decision.stop_profile == "strict_approval"

    def test_router_uses_registry_risk_level_procurement(self, router: PolicyRouter) -> None:
        """procurement 场景 risk_level=high。"""
        plan = {
            "scenario": "procurement",
            "capabilities": ["intent_parse"],
            "governance": {"requires_audit": True},
        }
        decision = router.route(plan, query="采购比价")
        assert decision.stop_profile == "strict_approval"

    def test_router_uses_registry_for_external_side_effects(self, router: PolicyRouter) -> None:
        """高风险场景默认有外部副作用。"""
        plan = {
            "scenario": "robotclaw",
            "capabilities": ["contract_form"],
            "governance": {"requires_audit": True},
        }
        decision = router.route(plan, query="dispatch")
        # robotclaw 有外部副作用 + 审计，应路由到 delegated_robotclaw
        assert decision.selected_strategy in ("delegated_robotclaw", "hybrid_robotclaw_claudecode")

    def test_router_with_custom_registry(self, tmp_path: Path) -> None:
        """PolicyRouter 可以注入自定义 registry。"""

        # 创建自定义 registry
        reg = ScenarioRegistry(scenarios_dir=tmp_path)
        router = PolicyRouter(scenario_registry=reg)
        assert router._registry is reg

    def test_router_travel_simple_task(self, router: PolicyRouter) -> None:
        """travel 场景 risk_level=medium, 应走简单/中等路由。"""
        plan = {
            "scenario": "travel",
            "capabilities": ["intent_parse", "option_score"],
            "governance": {"requires_audit": False},
        }
        decision = router.route(plan, query="订机票")
        assert decision.selected_route.mode in ("local", "delegated")
