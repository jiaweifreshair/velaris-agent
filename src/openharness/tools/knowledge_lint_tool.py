"""知识库健康检查工具。"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class KnowledgeLintInput(BaseModel):
    """知识库健康检查入参。"""

    user_id: str = Field(default="default", description="用户 ID，用于定位个人知识库")


class KnowledgeLintTool(BaseTool):
    """扫描个人知识库的断链和孤岛页面问题。"""

    name = "knowledge_lint"
    description = (
        "Run health checks on the personal knowledge base. "
        "Detects broken wiki links and orphan documents."
    )
    input_model = KnowledgeLintInput

    def is_read_only(self, arguments: KnowledgeLintInput) -> bool:
        """健康检查不落盘。"""
        del arguments
        return True

    async def execute(
        self, arguments: KnowledgeLintInput, context: ToolExecutionContext
    ) -> ToolResult:
        """执行知识库健康检查。"""
        try:
            from velaris_agent.knowledge.base import PersonalKnowledgeBase

            base_dir = context.metadata.get("knowledge_base_dir")
            kb = PersonalKnowledgeBase(base_dir=base_dir, namespace=arguments.user_id)
            report = kb.lint()
            payload = {
                "generated_at": report.generated_at.isoformat(),
                "total_docs": report.total_docs,
                "issues": [issue.model_dump(mode="json") for issue in report.issues],
            }
            return ToolResult(output=json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            return ToolResult(output=f"知识库健康检查失败: {exc}", is_error=True)
