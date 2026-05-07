"""Tests for engine.py + ScenarioRegistry 集成。"""

from __future__ import annotations


import pytest

from velaris_agent.biz.engine import (
    build_capability_plan,
    get_scenario_registry,
    infer_scenario,
    run_scenario,
)


class TestInferScenarioIntegration:
    """验证 infer_scenario 通过 registry 工作。"""

    def test_travel_by_keyword(self) -> None:
        assert infer_scenario("下周去上海出差") == "travel"

    def test_tokencost_by_keyword(self) -> None:
        assert infer_scenario("模型成本优化") == "tokencost"

    def test_procurement_by_keyword(self) -> None:
        assert infer_scenario("采购比价") == "procurement"

    def test_lifegoal_by_keyword(self) -> None:
        assert infer_scenario("跳槽还是留下来") == "lifegoal"

    def test_robotclaw_by_keyword(self) -> None:
        assert infer_scenario("派单策略") == "robotclaw"

    def test_explicit_scenario_hint(self) -> None:
        assert infer_scenario("随便", scenario="travel") == "travel"

    def test_general_fallback(self) -> None:
        assert infer_scenario("hello world") == "general"


class TestBuildCapabilityPlanIntegration:
    """验证 build_capability_plan 使用 registry 数据。"""

    def test_travel_plan_uses_registry_weights(self) -> None:
        plan = build_capability_plan(query="帮我订机票")
        assert plan["scenario"] == "travel"
        # 权重应来自 SKILL.md
        assert plan["decision_weights"]["price"] == pytest.approx(0.40)
        assert plan["decision_weights"]["time"] == pytest.approx(0.35)

    def test_travel_plan_uses_registry_capabilities(self) -> None:
        plan = build_capability_plan(query="帮我订机票")
        assert "intent_parse" in plan["capabilities"]

    def test_travel_plan_uses_registry_governance(self) -> None:
        plan = build_capability_plan(query="帮我订机票")
        assert plan["governance"]["requires_audit"] is False

    def test_travel_plan_uses_registry_tools(self) -> None:
        plan = build_capability_plan(query="帮我订机票")
        assert "travel_recommend" in plan["recommended_tools"]

    def test_robotclaw_plan_strict_governance(self) -> None:
        plan = build_capability_plan(query="派单策略")
        assert plan["governance"]["requires_audit"] is True
        assert plan["governance"]["approval_mode"] == "strict"

    def test_general_plan_defaults(self) -> None:
        plan = build_capability_plan(query="随便聊聊")
        assert plan["scenario"] == "general"
        assert "biz_execute" in plan["recommended_tools"]

    def test_constraints_override_governance(self) -> None:
        plan = build_capability_plan(
            query="帮我订机票",
            constraints={"requires_audit": True},
        )
        assert plan["governance"]["requires_audit"] is True


class TestRunScenarioIntegration:
    """验证 run_scenario 使用 registry 权重。"""

    def test_run_travel_with_registry_weights(self) -> None:
        result = run_scenario(
            scenario="travel",
            payload={
                "query": "北京到上海出差",
                "user_id": "u-test",
                "session_id": "s-test",
                "options": [
                    {
                        "id": "opt-a",
                        "label": "直飞",
                        "price": 1500,
                        "duration_minutes": 140,
                        "comfort": 0.8,
                        "direct": True,
                        "supplier": "东方航空",
                    },
                ],
            },
        )
        assert result["scenario"] == "travel"
        assert result["recommended"]["id"] == "opt-a"

    def test_run_tokencost_with_registry_weights(self) -> None:
        result = run_scenario(
            scenario="tokencost",
            payload={
                "query": "模型成本分析",
                "user_id": "u-test",
                "session_id": "s-test",
                "current_monthly_cost": 1000,
                "target_monthly_cost": 500,
                "recommendations": [
                    {
                        "id": "rec-a",
                        "model": "gpt-4o-mini",
                        "estimated_saving": 300,
                        "quality_retention": 0.9,
                        "execution_speed": 0.8,
                        "effort": "low",
                    },
                ],
            },
        )
        assert result["scenario"] == "tokencost"


class TestRegistryExposure:
    """验证 registry 可以被外部获取和操作。"""

    def test_get_scenario_registry(self) -> None:
        reg = get_scenario_registry()
        assert reg is not None
        assert "travel" in reg.list_scenarios()

    def test_registry_reload(self) -> None:
        reg = get_scenario_registry()
        loaded = reg.reload()
        assert len(loaded) >= 6  # 至少6个核心场景
