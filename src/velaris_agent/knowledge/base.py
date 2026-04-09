"""个人知识库核心实现。

设计目标：
1. 复用 Markdown 作为知识载体，避免引入额外服务依赖；
2. 采用 ingest/query/lint 三步闭环，贴合“可持续演进”的知识管理方式；
3. 文件布局清晰，可直接被人类编辑和审计。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from velaris_agent.knowledge.types import (
    KnowledgeDocument,
    KnowledgeLintIssue,
    KnowledgeLintReport,
    KnowledgeSearchResult,
)

_WIKI_LINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")


def _now() -> datetime:
    """返回 UTC 当前时间，统一索引时间语义。"""
    return datetime.now(timezone.utc)


def _slugify(text: str) -> str:
    """将标题转换为稳定 slug。

    仅保留英文字母、数字和中文字符，保证跨平台文件名安全。
    """
    lowered = text.strip().lower()
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "-", lowered, flags=re.UNICODE).strip("-")
    return cleaned or f"doc-{uuid4().hex[:8]}"


def _tokenize(text: str) -> set[str]:
    """提取检索 token，兼顾英文词与中文单字。"""
    ascii_tokens = {t for t in re.findall(r"[A-Za-z0-9_]+", text.lower()) if len(t) >= 2}
    han_tokens = set(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))
    return ascii_tokens | han_tokens


def _extract_links(content: str) -> list[str]:
    """提取 Markdown 中的 wiki 链接目标名称。"""
    return [match.strip() for match in _WIKI_LINK_RE.findall(content) if match.strip()]


class PersonalKnowledgeBase:
    """个人知识库管理器。

    存储结构：
      base_dir/
        index.json
        raw/*.md
        wiki/*.md
    """

    def __init__(
        self,
        *,
        base_dir: str | Path | None = None,
        namespace: str = "default",
    ) -> None:
        """初始化知识库目录。"""
        if base_dir is None:
            base_dir = Path.home() / ".velaris" / "knowledge"
        safe_namespace = _slugify(namespace)
        self._base_dir = Path(base_dir) / safe_namespace
        self._raw_dir = self._base_dir / "raw"
        self._wiki_dir = self._base_dir / "wiki"
        self._index_path = self._base_dir / "index.json"

        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._raw_dir.mkdir(parents=True, exist_ok=True)
        self._wiki_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        """返回当前 namespace 的根目录。"""
        return self._base_dir

    def ingest(
        self,
        *,
        title: str,
        content: str,
        source_uri: str | None = None,
        tags: Iterable[str] | None = None,
    ) -> KnowledgeDocument:
        """摄取一份原始资料并编译成 Wiki 页面。"""
        documents = self._load_documents()
        slug = _slugify(title)
        existing = self._find_by_slug(documents.values(), slug)

        now = _now()
        created_at = existing.created_at if existing else now
        doc_id = existing.doc_id if existing else f"doc-{uuid4().hex[:12]}"
        normalized_tags = sorted({_slugify(t).replace("-", "_") for t in (tags or []) if t.strip()})
        summary = self._summarize(content)
        links = _extract_links(content)

        raw_rel = Path("raw") / f"{slug}.md"
        wiki_rel = Path("wiki") / f"{slug}.md"
        raw_path = self._base_dir / raw_rel
        wiki_path = self._base_dir / wiki_rel

        raw_payload = self._render_raw(title=title, source_uri=source_uri, tags=normalized_tags, body=content)
        raw_path.write_text(raw_payload, encoding="utf-8")

        wiki_payload = self._render_wiki(
            title=title,
            summary=summary,
            source_uri=source_uri,
            tags=normalized_tags,
            links=links,
            body=content,
        )
        wiki_path.write_text(wiki_payload, encoding="utf-8")

        doc = KnowledgeDocument(
            doc_id=doc_id,
            slug=slug,
            title=title.strip() or slug,
            summary=summary,
            source_uri=source_uri.strip() if source_uri else None,
            tags=normalized_tags,
            links=links,
            raw_relpath=str(raw_rel),
            wiki_relpath=str(wiki_rel),
            created_at=created_at,
            updated_at=now,
        )
        documents[doc.doc_id] = doc
        self._save_documents(documents)
        return doc

    def search(self, *, query: str, limit: int = 5) -> list[KnowledgeSearchResult]:
        """在知识库中检索相关文档。"""
        tokens = _tokenize(query)
        if not tokens:
            return []

        scored: list[KnowledgeSearchResult] = []
        for doc in self._load_documents().values():
            wiki_path = self._base_dir / doc.wiki_relpath
            body = wiki_path.read_text(encoding="utf-8") if wiki_path.exists() else ""
            meta = f"{doc.title} {' '.join(doc.tags)} {doc.summary}".lower()
            meta_hits = sum(1 for token in tokens if token in meta)
            body_hits = sum(1 for token in tokens if token in body.lower())
            score = float(meta_hits * 2 + body_hits)
            if score <= 0:
                continue
            scored.append(
                KnowledgeSearchResult(
                    doc_id=doc.doc_id,
                    title=doc.title,
                    score=score,
                    summary=doc.summary,
                    tags=doc.tags,
                    updated_at=doc.updated_at,
                )
            )

        scored.sort(key=lambda item: (-item.score, -item.updated_at.timestamp()))
        return scored[:limit]

    def lint(self) -> KnowledgeLintReport:
        """执行知识库健康检查。"""
        docs = list(self._load_documents().values())
        by_slug = {doc.slug: doc for doc in docs}
        inbound_counts = {doc.slug: 0 for doc in docs}
        issues: list[KnowledgeLintIssue] = []

        for doc in docs:
            if not doc.summary.strip():
                issues.append(
                    KnowledgeLintIssue(
                        issue_type="missing_summary",
                        severity="warn",
                        page=doc.title,
                        message="摘要为空，建议补充高质量总结。",
                    )
                )

            existing_outbound: set[str] = set()
            for link in doc.links:
                target_slug = _slugify(link)
                if target_slug not in by_slug:
                    issues.append(
                        KnowledgeLintIssue(
                            issue_type="broken_link",
                            severity="error",
                            page=doc.title,
                            message=f"链接 [[{link}]] 指向的页面不存在。",
                        )
                    )
                    continue
                existing_outbound.add(target_slug)
                inbound_counts[target_slug] += 1

            if len(docs) > 1 and not existing_outbound and inbound_counts.get(doc.slug, 0) == 0:
                issues.append(
                    KnowledgeLintIssue(
                        issue_type="orphan_doc",
                        severity="warn",
                        page=doc.title,
                        message="当前页面既无入链也无有效出链，建议补充关联关系。",
                    )
                )

        return KnowledgeLintReport(generated_at=_now(), total_docs=len(docs), issues=issues)

    def file_insight(
        self,
        *,
        query: str,
        answer: str,
        related_pages: list[str] | None = None,
    ) -> KnowledgeDocument:
        """把一次问答沉淀为知识条目，形成“查询结果回写”闭环。"""
        lines = [answer.strip()]
        if related_pages:
            lines.append("")
            lines.append("## 关联页面")
            for page in related_pages:
                lines.append(f"- [[{page}]]")
        content = "\n".join(lines).strip() + "\n"
        title = f"问答沉淀-{query[:24].strip() or 'untitled'}"
        return self.ingest(
            title=title,
            content=content,
            tags=["qa", "insight"],
        )

    def _load_documents(self) -> dict[str, KnowledgeDocument]:
        """加载索引中的全部文档。"""
        if not self._index_path.exists():
            return {}
        try:
            payload = json.loads(self._index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

        docs_raw = payload.get("documents", [])
        if not isinstance(docs_raw, list):
            return {}

        result: dict[str, KnowledgeDocument] = {}
        for item in docs_raw:
            try:
                doc = KnowledgeDocument.model_validate(item)
            except Exception:
                continue
            result[doc.doc_id] = doc
        return result

    def _save_documents(self, documents: dict[str, KnowledgeDocument]) -> None:
        """把索引持久化到 index.json。"""
        ordered_docs = sorted(
            documents.values(),
            key=lambda item: item.updated_at,
            reverse=True,
        )
        payload = {
            "version": 1,
            "generated_at": _now().isoformat(),
            "documents": [doc.model_dump(mode="json") for doc in ordered_docs],
        }
        self._index_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _find_by_slug(
        self, documents: Iterable[KnowledgeDocument], slug: str
    ) -> KnowledgeDocument | None:
        """按 slug 查找已存在的文档。"""
        for doc in documents:
            if doc.slug == slug:
                return doc
        return None

    def _summarize(self, content: str, *, max_chars: int = 280) -> str:
        """对原文生成轻量摘要。"""
        normalized = re.sub(r"\s+", " ", content).strip()
        if not normalized:
            return "（空内容）"
        if len(normalized) <= max_chars:
            return normalized
        return normalized[:max_chars].rstrip() + "..."

    def _render_raw(
        self,
        *,
        title: str,
        source_uri: str | None,
        tags: list[str],
        body: str,
    ) -> str:
        """渲染 raw 层文档，保留原始信息。"""
        tag_line = ", ".join(tags) if tags else ""
        source_line = source_uri or ""
        return (
            "---\n"
            f"title: {title}\n"
            f"source: {source_line}\n"
            f"tags: [{tag_line}]\n"
            f"updated_at: {_now().isoformat()}\n"
            "---\n\n"
            f"{body.strip()}\n"
        )

    def _render_wiki(
        self,
        *,
        title: str,
        summary: str,
        source_uri: str | None,
        tags: list[str],
        links: list[str],
        body: str,
    ) -> str:
        """渲染 wiki 层文档，输出结构化知识视图。"""
        parts = [
            f"# {title}",
            "",
            "## 摘要",
            summary,
            "",
            "## 标签",
        ]
        if tags:
            parts.extend([f"- {tag}" for tag in tags])
        else:
            parts.append("- （暂无标签）")
        parts.extend(["", "## 来源"])
        parts.append(f"- {source_uri}" if source_uri else "- （本地输入）")
        parts.extend(["", "## 关键片段", self._summarize(body, max_chars=600), "", "## 关联页面"])
        if links:
            parts.extend([f"- [[{link}]]" for link in links])
        else:
            parts.append("- （暂无）")
        return "\n".join(parts).strip() + "\n"
