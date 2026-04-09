"""Velaris 个人知识库模块。

核心能力:
- PersonalKnowledgeBase: 统一管理原始资料、Wiki 页面和索引元数据
- KnowledgeDocument: 知识文档元数据模型
- KnowledgeLintReport: 知识库健康检查报告
"""

from velaris_agent.knowledge.base import PersonalKnowledgeBase
from velaris_agent.knowledge.types import (
    KnowledgeDocument,
    KnowledgeLintIssue,
    KnowledgeLintReport,
    KnowledgeSearchResult,
)

__all__ = [
    "PersonalKnowledgeBase",
    "KnowledgeDocument",
    "KnowledgeLintIssue",
    "KnowledgeLintReport",
    "KnowledgeSearchResult",
]
