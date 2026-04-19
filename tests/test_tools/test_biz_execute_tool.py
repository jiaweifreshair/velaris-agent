"""Velaris 业务运行时工具测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolExecutionContext
from openharness.velaris.orchestrator import VelarisBizOrchestrator


@pytest.mark.asyncio
async def test_biz_execute_tool_runs_full_tokencost_flow(tmp_path: Path):
    registry = create_default_tool_registry()
    orchestrator = VelarisBizOrchestrator()
    context = ToolExecutionContext(
        cwd=tmp_path,
        metadata={
            "tool_registry": registry,
            "velaris_orchestrator": orchestrator,
        },
    )

    biz_execute = registry.get("biz_execute")
    assert biz_execute is not None

    result = await biz_execute.execute(
        biz_execute.input_model(
            query="我每月 AI API 花费很高，帮我做降本分析",
            constraints={"target_monthly_cost": 800},
            payload={
                "current_monthly_cost": 2000,
                "target_monthly_cost": 800,
                "suggestions": [
                    {
                        "id": "switch-mini",
                        "title": "切换到 mini 模型",
                        "estimated_saving": 700,
                        "quality_retention": 0.9,
                        "execution_speed": 0.9,
                        "effort": "low",
                    },
                    {
                        "id": "prompt-compress",
                        "title": "压缩 Prompt",
                        "estimated_saving": 300,
                        "quality_retention": 0.95,
                        "execution_speed": 0.8,
                        "effort": "low",
                    },
                ],
            },
            session_id="session-tool",
        ),
        context,
    )

    payload = json.loads(result.output)
    assert result.is_error is False
    assert set(payload.keys()) == {"audit_event_count", "envelope", "outcome", "result", "session_id"}
    assert payload["envelope"]["plan"]["scenario"] == "tokencost"
    assert payload["envelope"]["routing"]["selected_strategy"] == "local_closed_loop"
    assert payload["envelope"]["authority"]["approvals_required"] is False
    assert payload["result"]["projected_monthly_cost"] == 1000
    assert payload["envelope"]["execution"]["gate_status"] == "allowed"
    assert payload["envelope"]["tasks"][0]["status"] == "completed"
    assert payload["outcome"]["success"] is True


@pytest.mark.asyncio
async def test_biz_execute_tool_runs_full_lifegoal_flow(tmp_path: Path):
    registry = create_default_tool_registry()
    orchestrator = VelarisBizOrchestrator()
    context = ToolExecutionContext(
        cwd=tmp_path,
        metadata={
            "tool_registry": registry,
            "velaris_orchestrator": orchestrator,
        },
    )

    biz_execute = registry.get("biz_execute")
    assert biz_execute is not None

    result = await biz_execute.execute(
        biz_execute.input_model(
            query="我收到了两个 offer，一个薪资更高，一个成长更强，帮我做人生目标决策",
            payload={
                "domain": "career",
                "risk_tolerance": "moderate",
                "constraints": ["一年内希望带团队", "不希望长期 996"],
                "options": [
                    {
                        "id": "offer-a",
                        "label": "Offer A：高薪成熟岗",
                        "dimensions": {
                            "growth": 0.56,
                            "income": 0.93,
                            "fulfillment": 0.61,
                            "stability": 0.82,
                            "balance": 0.38,
                        },
                    },
                    {
                        "id": "offer-b",
                        "label": "Offer B：成长型核心岗",
                        "dimensions": {
                            "growth": 0.95,
                            "income": 0.71,
                            "fulfillment": 0.9,
                            "stability": 0.68,
                            "balance": 0.79,
                        },
                    },
                ],
            },
            session_id="session-lifegoal",
        ),
        context,
    )

    payload = json.loads(result.output)
    assert result.is_error is False
    assert set(payload.keys()) == {"audit_event_count", "envelope", "outcome", "result", "session_id"}
    assert payload["envelope"]["plan"]["scenario"] == "lifegoal"
    assert payload["envelope"]["routing"]["selected_strategy"] == "local_closed_loop"
    assert payload["envelope"]["routing"]["stop_profile"] == "balanced"
    assert payload["result"]["domain"] == "career"
    assert payload["result"]["recommended"]["id"] == "offer-b"
    assert payload["envelope"]["execution"]["gate_status"] == "degraded"
    assert payload["envelope"]["tasks"][0]["status"] == "completed"
    assert payload["outcome"]["success"] is True
