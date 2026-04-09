"""知识库检索工具。"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class KnowledgeQueryInput(BaseModel):
    """知识库检索工具入参。"""

    user_id: str = Field(default="default", description="用户 ID，用于定位个人知识库")
    query: str = Field(description="检索查询")
    limit: int = Field(default=5, ge=1, le=20, description="返回结果数量上限")
    file_answer_back: bool = Field(
        default=False,
        description="是否把 answer_draft 作为问答沉淀回知识库",
    )
    answer_draft: str | None = Field(
        default=None,
        description="回答草稿；当 file_answer_back=true 时会持久化",
    )


class KnowledgeQueryTool(BaseTool):
    """在个人知识库里检索相关条目，并支持回写问答。"""

    name = "knowledge_query"
    description = (
        "Search the personal knowledge base by semantic token overlap. "
        "Optionally file the answer draft back into wiki notes."
    )
    input_model = KnowledgeQueryInput

    def is_read_only(self, arguments: KnowledgeQueryInput) -> bool:
        """只在显式要求 file-back 时执行写操作。"""
        return not arguments.file_answer_back

    async def execute(
        self, arguments: KnowledgeQueryInput, context: ToolExecutionContext
    ) -> ToolResult:
        """执行知识检索。"""
        try:
            from velaris_agent.knowledge.base import PersonalKnowledgeBase

            base_dir = context.metadata.get("knowledge_base_dir")
            kb = PersonalKnowledgeBase(base_dir=base_dir, namespace=arguments.user_id)
            matched = kb.search(query=arguments.query, limit=arguments.limit)
            payload: dict[str, object] = {
                "query": arguments.query,
                "total_found": len(matched),
                "results": [item.model_dump(mode="json") for item in matched],
            }

            if arguments.file_answer_back and arguments.answer_draft:
                insight = kb.file_insight(
                    query=arguments.query,
                    answer=arguments.answer_draft,
                    related_pages=[item.title for item in matched[:3]],
                )
                payload["file_back"] = {
                    "status": "saved",
                    "doc_id": insight.doc_id,
                    "title": insight.title,
                }
            return ToolResult(output=json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            return ToolResult(output=f"知识检索失败: {exc}", is_error=True)
