"""召回历史决策工具 - 检索与当前查询相似的历史决策摘要。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class RecallDecisionsInput(BaseModel):
    """召回历史决策工具入参。"""

    user_id: str = Field(description="用户 ID")
    scenario: str = Field(
        description="业务场景或人生领域, 如 travel / tokencost / robotclaw / career"
    )
    query: str = Field(description="当前查询文本, 用于相似度匹配")
    limit: int = Field(default=5, ge=1, le=20, description="返回结果数量上限")


class RecallDecisionsTool(BaseTool):
    """检索与当前查询相似的历史决策记录。

    返回摘要信息 (非完整记录), 包含查询、推荐、用户选择和满意度,
    帮助 Agent 参考历史经验做出更好的决策。
    """

    name = "recall_decisions"
    description = (
        "Recall similar historical decisions for a user in a given scenario. "
        "Returns summaries of past decisions including recommendations, "
        "user choices, and satisfaction scores."
    )
    input_model = RecallDecisionsInput

    def is_read_only(self, arguments: RecallDecisionsInput) -> bool:
        """只读操作, 不修改任何数据。"""
        del arguments
        return True

    async def execute(
        self, arguments: RecallDecisionsInput, context: ToolExecutionContext
    ) -> ToolResult:
        """执行历史决策检索。"""
        try:
            from velaris_agent.persistence.factory import build_decision_memory

            base_dir = context.metadata.get("decision_memory_dir")
            postgres_dsn = context.metadata.get("postgres_dsn", "")
            memory = build_decision_memory(
                postgres_dsn=postgres_dsn,
                base_dir=base_dir,
            )

            records = memory.recall_similar(
                user_id=arguments.user_id,
                scenario=arguments.scenario,
                query=arguments.query,
                limit=arguments.limit,
            )

            # 返回摘要而非完整记录, 减少 token 消耗
            summaries: list[dict[str, Any]] = []
            for r in records:
                summary: dict[str, Any] = {
                    "decision_id": r.decision_id,
                    "query": r.query[:200],
                    "recommended": {
                        "id": r.recommended.get("id", ""),
                        "label": r.recommended.get("label", ""),
                    } if r.recommended else None,
                    "user_choice": {
                        "id": r.user_choice.get("id", ""),
                        "label": r.user_choice.get("label", ""),
                    } if r.user_choice else None,
                    "user_feedback": r.user_feedback,
                    "weights_used": r.weights_used,
                    "created_at": r.created_at.isoformat(),
                }
                summaries.append(summary)

            result: dict[str, Any] = {
                "user_id": arguments.user_id,
                "scenario": arguments.scenario,
                "query": arguments.query,
                "total_found": len(summaries),
                "decisions": summaries,
            }
            return ToolResult(output=json.dumps(result, ensure_ascii=False))

        except Exception as e:
            return ToolResult(
                output=f"召回历史决策失败: {e}", is_error=True
            )
