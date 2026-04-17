"""召回用户偏好工具 - 从历史决策中计算个性化权重和行为模式。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class RecallPreferencesInput(BaseModel):
    """召回偏好工具入参。"""

    user_id: str = Field(description="用户 ID")
    scenario: str = Field(
        description="业务场景或人生领域, 如 travel / tokencost / robotclaw / career"
    )


class RecallPreferencesTool(BaseTool):
    """从用户历史决策中计算个性化偏好画像。

    返回个性化权重、行为模式、满意度历史等信息,
    帮助 Agent 在后续决策中做出更符合用户偏好的推荐。
    """

    name = "recall_preferences"
    description = (
        "Recall a user's personalized preferences for a given scenario. "
        "Returns learned weights, behavioral patterns, and satisfaction history."
    )
    input_model = RecallPreferencesInput

    def is_read_only(self, arguments: RecallPreferencesInput) -> bool:
        """只读操作, 不修改任何数据。"""
        del arguments
        return True

    async def execute(
        self, arguments: RecallPreferencesInput, context: ToolExecutionContext
    ) -> ToolResult:
        """执行偏好召回。"""
        try:
            from velaris_agent.memory.preference_learner import PreferenceLearner
            from velaris_agent.persistence.factory import build_decision_memory

            base_dir = context.metadata.get("decision_memory_dir")
            postgres_dsn = context.metadata.get("postgres_dsn", "")
            memory = build_decision_memory(
                postgres_dsn=postgres_dsn,
                base_dir=base_dir,
            )
            learner = PreferenceLearner(memory)

            prefs = learner.compute_preferences(arguments.user_id, arguments.scenario)

            result: dict[str, Any] = {
                "user_id": prefs.user_id,
                "scenario": prefs.scenario,
                "weights": prefs.weights,
                "total_decisions": prefs.total_decisions,
                "accepted_recommendation_rate": prefs.accepted_recommendation_rate,
                "average_satisfaction": prefs.average_satisfaction,
                "common_patterns": prefs.common_patterns,
                "confidence": prefs.confidence,
                "last_updated": (
                    prefs.last_updated.isoformat() if prefs.last_updated else None
                ),
            }
            return ToolResult(output=json.dumps(result, ensure_ascii=False))

        except Exception as e:
            return ToolResult(
                output=f"召回用户偏好失败: {e}", is_error=True
            )
