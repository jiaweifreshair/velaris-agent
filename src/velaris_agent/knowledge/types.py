"""个人知识库数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeDocument(BaseModel):
    """知识文档元数据。

    该模型描述一篇知识条目的核心状态，便于在索引中稳定持久化，
    同时让 ingest/query/lint 在同一结构上协作。
    """

    doc_id: str = Field(description="知识文档唯一 ID")
    slug: str = Field(description="文档 slug，用于文件名和链接解析")
    title: str = Field(description="文档标题")
    summary: str = Field(description="文档摘要")
    source_uri: str | None = Field(default=None, description="来源链接")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    links: list[str] = Field(default_factory=list, description="文档中的 wiki 链接目标")
    raw_relpath: str = Field(description="原始资料相对路径")
    wiki_relpath: str = Field(description="Wiki 页面相对路径")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")


class KnowledgeSearchResult(BaseModel):
    """知识检索结果。"""

    doc_id: str = Field(description="文档 ID")
    title: str = Field(description="文档标题")
    score: float = Field(description="匹配得分")
    summary: str = Field(description="摘要")
    tags: list[str] = Field(default_factory=list, description="标签")
    updated_at: datetime = Field(description="最后更新时间")


class KnowledgeLintIssue(BaseModel):
    """知识库健康检查中的单条问题。"""

    issue_type: str = Field(description="问题类型，例如 broken_link/orphan_doc")
    severity: Literal["info", "warn", "error"] = Field(description="严重级别")
    page: str = Field(description="问题所在页面标题")
    message: str = Field(description="问题说明")


class KnowledgeLintReport(BaseModel):
    """知识库健康检查报告。"""

    generated_at: datetime = Field(description="报告生成时间")
    total_docs: int = Field(description="文档总数")
    issues: list[KnowledgeLintIssue] = Field(default_factory=list, description="问题列表")
