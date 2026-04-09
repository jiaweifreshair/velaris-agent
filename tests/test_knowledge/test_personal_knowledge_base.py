"""个人知识库核心能力测试。"""

from __future__ import annotations

from pathlib import Path

from velaris_agent.knowledge.base import PersonalKnowledgeBase


def test_ingest_and_search(tmp_path: Path) -> None:
    """摄取后可检索到条目，并生成 raw/wiki 文件。"""
    kb = PersonalKnowledgeBase(base_dir=tmp_path / "knowledge", namespace="user-a")
    doc = kb.ingest(
        title="Karpathy 工作流",
        content=(
            "Karpathy 提出 ingest -> query -> lint 的知识库流程。"
            "我们可以把复杂 RAG 转为可持续演进的 Markdown Wiki。"
        ),
        source_uri="https://example.com/karpathy",
        tags=["LLM", "PKM"],
    )

    assert doc.title == "Karpathy 工作流"
    assert (kb.base_dir / doc.raw_relpath).exists()
    assert (kb.base_dir / doc.wiki_relpath).exists()

    hits = kb.search(query="知识库 演进", limit=3)
    assert hits
    assert hits[0].doc_id == doc.doc_id


def test_lint_detects_broken_link(tmp_path: Path) -> None:
    """当文档包含不存在的 wiki 链接时，lint 能报告错误。"""
    kb = PersonalKnowledgeBase(base_dir=tmp_path / "knowledge", namespace="user-b")
    kb.ingest(
        title="入口页",
        content="这里引用一个不存在页面 [[Missing Page]]。",
        tags=["demo"],
    )

    report = kb.lint()
    assert report.total_docs == 1
    assert report.issues
    assert any(issue.issue_type == "broken_link" for issue in report.issues)


def test_file_insight_creates_followup_note(tmp_path: Path) -> None:
    """问答回写会生成新的知识条目。"""
    kb = PersonalKnowledgeBase(base_dir=tmp_path / "knowledge", namespace="user-c")
    insight = kb.file_insight(
        query="如何做知识库健康检查",
        answer="建议每周执行 lint，并回填结果。",
        related_pages=["入口页"],
    )
    assert insight.doc_id.startswith("doc-")
    assert (kb.base_dir / insight.wiki_relpath).exists()
