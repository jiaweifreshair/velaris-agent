"""决策评分工具 - 支持个性化权重的多维候选项排序。

将 biz/engine.py 的 score_options 封装为独立工具,
并增加个性化权重支持: 当提供 user_id 且有历史数据时,
自动使用偏好学习器计算的个性化权重替代显式权重。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class DecisionScoreInput(BaseModel):
    """决策评分工具入参。"""

    options: list[dict[str, Any]] = Field(
        description="候选项列表, 每项需包含 id、label 和 scores (各维度分数 0-1)"
    )
    weights: dict[str, float] = Field(
        default_factory=dict,
        description="维度权重, 如 {price: 0.4, time: 0.35, comfort: 0.25}",
    )
    user_id: str | None = Field(
        default=None,
        description="用户 ID, 提供时自动使用个性化权重 (优先于 weights 参数)",
    )
    scenario: str | None = Field(
        default=None,
        description="业务场景, 与 user_id 配合使用个性化权重",
    )


class DecisionScoreTool(BaseTool):
    """对候选项进行多维加权评分和排序。

    支持两种模式:
    1. 显式权重: 直接传入 weights 参数
    2. 个性化权重: 传入 user_id + scenario, 自动从历史决策中学习权重

    当 user_id 有历史数据且置信度 > 0 时, 个性化权重优先。
    """

    name = "decision_score"
    description = (
        "Score and rank options with multi-dimensional weights. "
        "Supports personalized weights when user_id is provided - "
        "automatically learns from historical decisions."
    )
    input_model = DecisionScoreInput

    def is_read_only(self, arguments: DecisionScoreInput) -> bool:
        """只读操作, 不修改任何数据。"""
        del arguments
        return True

    async def execute(
        self, arguments: DecisionScoreInput, context: ToolExecutionContext
    ) -> ToolResult:
        """执行评分排序。"""
        try:
            from velaris_agent.biz.engine import score_options
            from velaris_agent.persistence.factory import build_decision_memory

            effective_weights = dict(arguments.weights) if arguments.weights else {}
            personalized = False

            # 尝试使用个性化权重
            if arguments.user_id and arguments.scenario:
                try:
                    from velaris_agent.memory.preference_learner import PreferenceLearner

                    base_dir = context.metadata.get("decision_memory_dir")
                    postgres_dsn = context.metadata.get("postgres_dsn", "")
                    memory = build_decision_memory(
                        postgres_dsn=postgres_dsn,
                        base_dir=base_dir,
                    )
                    learner = PreferenceLearner(memory)

                    prefs = learner.compute_preferences(
                        arguments.user_id, arguments.scenario
                    )
                    # 仅在有历史数据 (置信度 > 0) 时使用个性化权重
                    if prefs.confidence > 0:
                        effective_weights = prefs.weights
                        personalized = True
                except Exception:
                    # 个性化权重计算失败时回退到显式权重
                    pass

            if not effective_weights:
                return ToolResult(
                    output="缺少权重: 请提供 weights 参数或有效的 user_id + scenario",
                    is_error=True,
                )

            ranked = score_options(arguments.options, effective_weights)

            result: dict[str, Any] = {
                "ranked_options": ranked,
                "weights_used": effective_weights,
                "personalized": personalized,
            }
            if personalized:
                result["note"] = (
                    f"已使用 {arguments.user_id} 在 {arguments.scenario} "
                    "场景下的个性化权重"
                )

            return ToolResult(output=json.dumps(result, ensure_ascii=False))

        except Exception as e:
            return ToolResult(
                output=f"决策评分失败: {e}", is_error=True
            )
