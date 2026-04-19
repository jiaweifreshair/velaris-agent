"""Velaris 领域数据源 adapter 测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("openharness.tools.travel_recommend_tool")
pytest.importorskip("openharness.tools.tokencost_analyze_tool")
pytest.importorskip("openharness.tools.robotclaw_dispatch_tool")

from openharness.tools.base import ToolExecutionContext
from openharness.tools.robotclaw_dispatch_tool import RobotClawDispatchTool, RobotClawDispatchToolInput
from openharness.tools.tokencost_analyze_tool import TokenCostAnalyzeTool, TokenCostAnalyzeToolInput
from openharness.tools.travel_recommend_tool import TravelRecommendTool, TravelRecommendToolInput


@pytest.mark.asyncio
async def test_travel_tool_supports_file_source(tmp_path: Path):
    source_path = tmp_path / "travel.json"
    source_path.write_text(
        json.dumps(
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
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = await TravelRecommendTool().execute(
        TravelRecommendToolInput(
            source={"type": "file", "path": str(source_path)},
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    payload = json.loads(result.output)
    assert payload["recommended"]["id"] == "travel-a"


@pytest.mark.asyncio
async def test_tokencost_tool_supports_file_source(tmp_path: Path):
    source_path = tmp_path / "tokencost.json"
    source_path.write_text(
        json.dumps(
            {
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
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = await TokenCostAnalyzeTool().execute(
        TokenCostAnalyzeToolInput(
            source={"type": "file", "path": str(source_path)},
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    payload = json.loads(result.output)
    assert payload["projected_monthly_cost"] == 1100


@pytest.mark.asyncio
async def test_robotclaw_tool_supports_file_source(tmp_path: Path):
    source_path = tmp_path / "robotclaw.json"
    source_path.write_text(
        json.dumps(
            {
                "max_budget_cny": 200000,
                "proposals": [
                    {
                        "id": "dispatch-a",
                        "price_cny": 180000,
                        "eta_minutes": 22,
                        "safety_score": 0.95,
                        "compliance_score": 0.95,
                        "available": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = await RobotClawDispatchTool().execute(
        RobotClawDispatchToolInput(
            source={"type": "file", "path": str(source_path)},
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    payload = json.loads(result.output)
    assert payload["recommended"]["id"] == "dispatch-a"
