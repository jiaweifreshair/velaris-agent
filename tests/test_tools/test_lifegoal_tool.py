"""人生目标决策工具测试。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolExecutionContext
from openharness.tools.lifegoal_tool import LifeGoalTool, LifeGoalToolInput
from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.memory.types import DecisionRecord


def _seed_career_preferences(decision_dir: Path) -> None:
    """预置职业领域历史偏好。

    这些样本被设计成“用户持续放弃高薪推荐，转而选择成长更好的选项”，
    用来验证 lifegoal 工具会真正读到 career 维度的个性化权重。
    """
    memory = DecisionMemory(base_dir=decision_dir)
    scores = [
        {
            "id": "high-pay",
            "scores": {
                "income": 0.95,
                "growth": 0.5,
                "fulfillment": 0.52,
                "stability": 0.82,
                "work_life_balance": 0.35,
            },
        },
        {
            "id": "growth-first",
            "scores": {
                "income": 0.68,
                "growth": 0.94,
                "fulfillment": 0.87,
                "stability": 0.64,
                "work_life_balance": 0.76,
            },
        },
    ]

    for index in range(4):
        memory.save(
            DecisionRecord(
                decision_id=f"career-pref-{index:03d}",
                user_id="life-user",
                scenario="career",
                query="两个 offer 怎么选",
                recommended={"id": "high-pay", "label": "高薪路径"},
                user_choice={"id": "growth-first", "label": "成长路径"},
                user_feedback=4.7,
                scores=scores,
                weights_used={
                    "income": 0.25,
                    "growth": 0.25,
                    "fulfillment": 0.2,
                    "stability": 0.15,
                    "work_life_balance": 0.15,
                },
                created_at=datetime.now(timezone.utc),
            )
        )


def test_default_registry_contains_lifegoal_demo_tools():
    """默认工具注册表必须包含人生目标 demo 所需的核心工具。"""
    registry = create_default_tool_registry()

    assert registry.get("lifegoal_decide") is not None
    assert registry.get("decision_score") is not None
    assert registry.get("recall_preferences") is not None
    assert registry.get("recall_decisions") is not None
    assert registry.get("save_decision") is not None


@pytest.mark.asyncio
async def test_lifegoal_tool_uses_personalized_career_weights(tmp_path: Path):
    """职业领域存在历史偏好时，lifegoal 工具应使用 career 维度的个性化权重。"""
    decision_dir = tmp_path / "decisions"
    _seed_career_preferences(decision_dir)
    context = ToolExecutionContext(
        cwd=tmp_path,
        metadata={"decision_memory_dir": str(decision_dir)},
    )

    result = await LifeGoalTool().execute(
        LifeGoalToolInput(
            domain="career",
            user_id="life-user",
            risk_tolerance="moderate",
            constraints=["希望 2 年内进入管理岗"],
            options=[
                {
                    "id": "offer-a",
                    "label": "Offer A",
                    "dimensions": {
                        "income": 0.93,
                        "growth": 0.56,
                        "fulfillment": 0.6,
                        "stability": 0.84,
                        "work_life_balance": 0.38,
                    },
                },
                {
                    "id": "offer-b",
                    "label": "Offer B",
                    "dimensions": {
                        "income": 0.72,
                        "growth": 0.95,
                        "fulfillment": 0.9,
                        "stability": 0.67,
                        "work_life_balance": 0.78,
                    },
                },
            ],
        ),
        context,
    )

    assert result.is_error is False

    payload = json.loads(result.output)
    assert payload["recommended"]["id"] == "offer-b"
    assert "growth" in payload["weights_used"]
    assert "income" in payload["weights_used"]
    assert "quality" not in payload["weights_used"]
