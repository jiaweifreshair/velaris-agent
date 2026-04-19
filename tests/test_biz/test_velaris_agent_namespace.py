"""Velaris 原生命名空间兼容测试。"""

from __future__ import annotations

from velaris_agent.biz.engine import build_capability_plan, run_scenario
from velaris_agent.velaris.orchestrator import VelarisBizOrchestrator


def test_velaris_agent_namespace_exports_biz_capabilities():
    plan = build_capability_plan(
        query="下周去上海出差，帮我做机票酒店组合推荐",
        constraints={"budget_max": 3000, "direct_only": True},
    )
    result = run_scenario(
        "travel",
        {
            "budget_max": 3000,
            "direct_only": True,
            "options": [
                {
                    "id": "travel-a",
                    "label": "直飞方案",
                    "price": 1500,
                    "duration_minutes": 150,
                    "comfort": 0.78,
                    "direct": True,
                }
            ],
        },
    )

    assert plan["scenario"] == "travel"
    assert result["recommended"]["id"] == "travel-a"


def test_velaris_agent_namespace_exports_orchestrator():
    orchestrator = VelarisBizOrchestrator()
    result = orchestrator.execute(
        query="我每月 OpenAI 成本 2000 美元，想降到 800",
        constraints={"target_monthly_cost": 800},
        payload={
            "current_monthly_cost": 2000,
            "target_monthly_cost": 800,
            "suggestions": [
                {
                    "id": "switch-tier",
                    "title": "分层路由",
                    "estimated_saving": 900,
                    "quality_retention": 0.88,
                    "execution_speed": 0.9,
                    "effort": "medium",
                }
            ],
        },
    )

    assert result["session_id"] is not None
    assert result["envelope"]["plan"]["scenario"] == "tokencost"
    assert result["envelope"]["routing"]["selected_strategy"] == "local_closed_loop"
    assert result["envelope"]["execution"]["gate_status"] == "allowed"
