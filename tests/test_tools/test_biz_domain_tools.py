"""Velaris 领域业务工具测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openharness.tools.robotclaw_dispatch_tool import RobotClawDispatchTool, RobotClawDispatchToolInput
from openharness.tools.tokencost_analyze_tool import TokenCostAnalyzeTool, TokenCostAnalyzeToolInput
from openharness.tools.travel_compare_tool import TravelCompareTool
from openharness.tools.travel_recommend_tool import TravelRecommendTool, TravelRecommendToolInput
from openharness.tools.base import ToolExecutionContext


@pytest.mark.asyncio
async def test_travel_recommend_tool_returns_ranked_plan(tmp_path: Path):
    result = await TravelRecommendTool().execute(
        TravelRecommendToolInput(
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
        ToolExecutionContext(cwd=tmp_path),
    )

    payload = json.loads(result.output)
    assert payload["scenario"] == "travel"
    assert payload["recommended"]["id"] == "travel-a"
    assert payload["status"] == "requires_confirmation"
    assert payload["requires_confirmation"] is True


@pytest.mark.asyncio
async def test_travel_compare_tool_supports_confirmation_flow(tmp_path: Path):
    result = await TravelCompareTool().execute(
        TravelRecommendToolInput(
            query="帮我查北京到上海的直飞机票，预算 2000 内",
            user_id="u-demo",
            session_id="session-demo",
            confirm=True,
            selected_option_id="travel-a",
            proposal_id="travel-proposal-demo",
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
        ToolExecutionContext(cwd=tmp_path),
    )

    payload = json.loads(result.output)
    assert payload["intent"] == "travel_compare"
    assert payload["status"] == "completed"
    assert payload["execution_status"] == "completed"
    assert payload["audit_trace"]["proposal_id"] == "travel-proposal-demo"


@pytest.mark.asyncio
async def test_tokencost_analyze_tool_returns_projection(tmp_path: Path):
    result = await TokenCostAnalyzeTool().execute(
        TokenCostAnalyzeToolInput(
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
        ToolExecutionContext(cwd=tmp_path),
    )

    payload = json.loads(result.output)
    assert payload["scenario"] == "tokencost"
    assert payload["recommendations"][0]["id"] == "switch-tier"
    assert payload["projected_monthly_cost"] == 850


@pytest.mark.asyncio
async def test_robotclaw_dispatch_tool_applies_safety_gate(tmp_path: Path):
    result = await RobotClawDispatchTool().execute(
        RobotClawDispatchToolInput(
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
        ToolExecutionContext(cwd=tmp_path),
    )

    payload = json.loads(result.output)
    assert payload["scenario"] == "robotclaw"
    assert payload["recommended"]["id"] == "dispatch-a"
    assert payload["contract_ready"] is True
