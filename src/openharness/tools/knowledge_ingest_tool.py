"""知识库摄取工具。"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class KnowledgeIngestInput(BaseModel):
    """知识库摄取工具入参。"""

    user_id: str = Field(default="default", description="用户 ID，用于隔离个人知识库 namespace")
    title: str = Field(description="知识条目标题")
    content: str = Field(description="原始内容（Markdown 或纯文本）")
    source_uri: str | None = Field(default=None, description="来源链接")
    tags: list[str] = Field(default_factory=list, description="标签列表")


class KnowledgeIngestTool(BaseTool):
    """把原始内容摄取为个人知识库条目。"""

    name = "knowledge_ingest"
    description = (
        "Ingest a document into the personal knowledge base. "
        "Stores raw content and compiles a structured wiki page."
    )
    input_model = KnowledgeIngestInput

    def is_read_only(self, arguments: KnowledgeIngestInput) -> bool:
        """摄取会写入本地文件。"""
        del arguments
        return False

    async def execute(
        self, arguments: KnowledgeIngestInput, context: ToolExecutionContext
    ) -> ToolResult:
        """执行知识摄取。"""
        try:
            from velaris_agent.knowledge.base import PersonalKnowledgeBase

            base_dir = context.metadata.get("knowledge_base_dir")
            kb = PersonalKnowledgeBase(base_dir=base_dir, namespace=arguments.user_id)
            doc = kb.ingest(
                title=arguments.title,
                content=arguments.content,
                source_uri=arguments.source_uri,
                tags=arguments.tags,
            )
            payload = {
                "status": "ingested",
                "doc_id": doc.doc_id,
                "title": doc.title,
                "summary": doc.summary,
                "tags": doc.tags,
                "raw_relpath": doc.raw_relpath,
                "wiki_relpath": doc.wiki_relpath,
                "knowledge_base_dir": str(kb.base_dir),
            }
            return ToolResult(output=json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            return ToolResult(output=f"知识摄取失败: {exc}", is_error=True)
