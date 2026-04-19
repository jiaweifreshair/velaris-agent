"""Velaris 领域业务工具注册表测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolExecutionContext


@pytest.mark.asyncio
async def test_travel_plan_recommends_travel_tool_and_registry_executes(tmp_path: Path):
    registry = create_default_tool_registry()
    context = ToolExecutionContext(cwd=tmp_path, metadata={"tool_registry": registry})

    biz_plan = registry.get("biz_plan")
    travel_tool = registry.get("travel_recommend")
    travel_compare_tool = registry.get("travel_compare")
    if travel_tool is None:
        pytest.skip("未提供 travel_recommend_tool，跳过商旅领域注册表集成测试")

    plan_result = await biz_plan.execute(
        biz_plan.input_model(
            query="下周去上海出差，帮我做商旅推荐",
            constraints={"budget_max": 3000, "direct_only": True},
        ),
        context,
    )
    plan = json.loads(plan_result.output)
    assert plan["recommended_tools"][1] == "travel_recommend"
    assert "travel_compare" in plan["recommended_tools"]
    assert travel_compare_tool is not None

    run_result = await travel_tool.execute(
        travel_tool.input_model(
            budget_max=3000,
            direct_only=True,
            options=[
                {
                    "id": "travel-a",
                    "label": "直飞方案",
                    "price": 1500,
                    "duration_minutes": 150,
                    "comfort": 0.78,
                    "direct": True,
                },
                {
                    "id": "travel-b",
                    "label": "转机方案",
                    "price": 1100,
                    "duration_minutes": 350,
                    "comfort": 0.52,
                    "direct": False,
                },
            ],
        ),
        context,
    )
    payload = json.loads(run_result.output)
    assert payload["recommended"]["id"] == "travel-a"
    assert payload["status"] == "requires_confirmation"


@pytest.mark.asyncio
async def test_tokencost_plan_recommends_tokencost_tool_and_registry_executes(tmp_path: Path):
    registry = create_default_tool_registry()
    context = ToolExecutionContext(cwd=tmp_path, metadata={"tool_registry": registry})

    biz_plan = registry.get("biz_plan")
    tokencost_tool = registry.get("tokencost_analyze")
    if tokencost_tool is None:
        pytest.skip("未提供 tokencost_analyze_tool，跳过 tokencost 领域注册表集成测试")

    plan_result = await biz_plan.execute(
        biz_plan.input_model(
            query="我每月 OpenAI 成本 2000 美元，想降到 800",
            constraints={"target_monthly_cost": 800},
        ),
        context,
    )
    plan = json.loads(plan_result.output)
    assert plan["recommended_tools"][1] == "tokencost_analyze"

    run_result = await tokencost_tool.execute(
        tokencost_tool.input_model(
            current_monthly_cost=2000,
            target_monthly_cost=800,
            suggestions=[
                {
                    "id": "switch-tier",
                    "title": "分层路由",
                    "estimated_saving": 900,
                    "quality_retention": 0.88,
                    "execution_speed": 0.9,
                    "effort": "medium",
                },
                {
                    "id": "cache-enable",
                    "title": "缓存命中",
                    "estimated_saving": 250,
                    "quality_retention": 0.97,
                    "execution_speed": 0.75,
                    "effort": "low",
                },
            ],
        ),
        context,
    )
    payload = json.loads(run_result.output)
    assert payload["projected_monthly_cost"] == 850


@pytest.mark.asyncio
async def test_robotclaw_plan_recommends_dispatch_tool_and_registry_executes(tmp_path: Path):
    registry = create_default_tool_registry()
    context = ToolExecutionContext(cwd=tmp_path, metadata={"tool_registry": registry})

    biz_plan = registry.get("biz_plan")
    robotclaw_tool = registry.get("robotclaw_dispatch")
    if robotclaw_tool is None:
        pytest.skip("未提供 robotclaw_dispatch_tool，跳过 robotclaw 领域注册表集成测试")

    plan_result = await biz_plan.execute(
        biz_plan.input_model(
            query="为 robotaxi 派单生成服务提案并形成交易合约",
            constraints={"requires_audit": True},
        ),
        context,
    )
    plan = json.loads(plan_result.output)
    assert plan["recommended_tools"][1] == "robotclaw_dispatch"

    run_result = await robotclaw_tool.execute(
        robotclaw_tool.input_model(
            max_budget_cny=200000,
            proposals=[
                {
                    "id": "dispatch-a",
                    "price_cny": 180000,
                    "eta_minutes": 22,
                    "safety_score": 0.95,
                    "compliance_score": 0.95,
                    "available": True,
                },
                {
                    "id": "dispatch-b",
                    "price_cny": 100000,
                    "eta_minutes": 18,
                    "safety_score": 0.68,
                    "compliance_score": 0.82,
                    "available": True,
                },
            ],
        ),
        context,
    )
    payload = json.loads(run_result.output)
    assert payload["recommended"]["id"] == "dispatch-a"
