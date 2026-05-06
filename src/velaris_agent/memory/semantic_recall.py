"""SemanticRecallEngine — 语义召回引擎。

基于向量嵌入的语义召回，替代 DecisionMemory 的 keyword-only 匹配。

设计原则：
1. 可插拔：支持不同的 EmbeddingProvider（本地/远程/占位）
2. 渐进降级：无向量索引时自动 fallback 到 keyword 匹配
3. 最小侵入：与 DecisionMemory 集成而非替换
4. 可扩展：预留 HNSW / VikingVectorDB 适配接口

核心 API：
- index(record): 索引决策记录到向量空间
- recall(query, scenario, top_k): 语义召回
- recall_by_embedding(embedding, top_k): 直接用 embedding 召回
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from velaris_agent.memory.types import DecisionRecord


# ── Embedding Provider Protocol ─────────────────────────────

class EmbeddingProvider(Protocol):
    """向量嵌入提供者协议。"""

    def embed(self, text: str) -> list[float]:
        """将文本转为向量嵌入。"""
        ...

    def dimension(self) -> int:
        """返回嵌入维度。"""
        ...


# ── 简单占位 Embedding ──────────────────────────────────────

class SimpleHashEmbedding:
    """基于哈希的简单嵌入，用于测试和开发。

    不适合生产——仅用于验证 SemanticRecallEngine 的流程。
    生产环境应替换为 sentence-transformers / OpenAI Ada 等。
    """

    def __init__(self, dim: int = 128) -> None:
        self._dim = dim

    def embed(self, text: str) -> list[float]:
        """生成基于文本哈希的伪向量。"""
        # 简单哈希：每个字符影响对应维度
        vec = [0.0] * self._dim
        for i, ch in enumerate(text):
            idx = (ord(ch) + i) % self._dim
            vec[idx] += math.sin(ord(ch) * 0.1 + i * 0.01)
        # 归一化
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def dimension(self) -> int:
        return self._dim


# ── 数据类 ──────────────────────────────────────────────────

@dataclass(frozen=True)
class IndexedRecord:
    """已索引的决策记录引用。"""

    decision_id: str
    user_id: str
    scenario: str
    query: str
    embedding: list[float]
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecallResult:
    """召回结果。"""

    record: DecisionRecord
    score: float              # 语义相似度 [0, 1]
    method: str               # "semantic" 或 "keyword_fallback"
    debug_info: dict[str, Any] = field(default_factory=dict)


# ── 余弦相似度 ──────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度。"""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── SemanticRecallEngine ────────────────────────────────────

class SemanticRecallEngine:
    """基于向量嵌入的语义召回引擎。

    核心工作流：
    1. index(): 将 DecisionRecord 的 query 转为 embedding 并存储
    2. recall(): 将用户查询转为 embedding，检索最相似的记录
    3. recall_by_embedding(): 直接用 embedding 检索

    渐进降级：
    - 无索引记录时返回空列表
    - 语义相似度低于阈值时 fallback 到 keyword
    - embedding provider 不可用时 fallback 到 keyword
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
        similarity_threshold: float = 0.3,
        max_index_size: int = 10000,
    ) -> None:
        """初始化语义召回引擎。

        Args:
            embedding_provider: 向量嵌入提供者，None 时使用 SimpleHashEmbedding
            similarity_threshold: 语义相似度阈值，低于此值降级到 keyword
            max_index_size: 最大索引记录数
        """
        self._provider = embedding_provider or SimpleHashEmbedding()
        self._similarity_threshold = similarity_threshold
        self._max_index_size = max_index_size
        # 内存索引：decision_id → IndexedRecord
        self._index: dict[str, IndexedRecord] = {}
        # 场景索引：scenario → set(decision_id)
        self._scenario_index: dict[str, set[str]] = {}
        # 用户+场景索引：(user_id, scenario) → set(decision_id)
        self._user_scenario_index: dict[tuple[str, str], set[str]] = {}

    # ── 核心接口 ─────────────────────────────────────────────

    def index(self, record: DecisionRecord) -> str:
        """索引决策记录到向量空间。

        Args:
            record: 决策记录

        Returns:
            索引 ID（= decision_id）
        """
        # 生成 embedding
        query_text = record.query or ""
        try:
            embedding = self._provider.embed(query_text)
        except Exception:
            # embedding 生成失败，跳过索引
            return ""

        # 检查容量
        if len(self._index) >= self._max_index_size:
            # 简单策略：移除最早的记录
            self._evict_oldest()

        indexed = IndexedRecord(
            decision_id=record.decision_id,
            user_id=record.user_id,
            scenario=record.scenario,
            query=query_text,
            embedding=embedding,
            created_at=record.created_at.isoformat() if hasattr(record.created_at, "isoformat") else str(record.created_at),
        )

        self._index[record.decision_id] = indexed

        # 更新场景索引
        if record.scenario not in self._scenario_index:
            self._scenario_index[record.scenario] = set()
        self._scenario_index[record.scenario].add(record.decision_id)

        # 更新用户+场景索引
        key = (record.user_id, record.scenario)
        if key not in self._user_scenario_index:
            self._user_scenario_index[key] = set()
        self._user_scenario_index[key].add(record.decision_id)

        return record.decision_id

    def recall(
        self,
        query: str,
        scenario: str,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> list[RecallResult]:
        """语义召回：根据查询文本检索最相似的决策记录。

        Args:
            query: 查询文本
            scenario: 场景名
            user_id: 用户 ID（可选，用于过滤）
            top_k: 返回数量

        Returns:
            RecallResult 列表，按相似度降序
        """
        # 1. 生成查询 embedding
        try:
            query_embedding = self._provider.embed(query)
        except Exception:
            # embedding 失败，返回空（让调用者 fallback 到 keyword）
            return []

        # 2. 获取候选集
        candidate_ids = self._get_candidates(scenario, user_id)
        if not candidate_ids:
            return []

        # 3. 计算相似度
        scored: list[tuple[float, str]] = []
        for dec_id in candidate_ids:
            indexed = self._index.get(dec_id)
            if indexed is None:
                continue
            sim = cosine_similarity(query_embedding, indexed.embedding)
            if sim >= self._similarity_threshold:
                scored.append((sim, dec_id))

        # 4. 排序并返回 top_k
        scored.sort(key=lambda x: x[0], reverse=True)
        top_results = scored[:top_k]

        results: list[RecallResult] = []
        for score, dec_id in top_results:
            indexed = self._index[dec_id]
            # 构造最简 DecisionRecord（从索引恢复）
            record = self._indexed_to_record(indexed)
            results.append(RecallResult(
                record=record,
                score=round(score, 4),
                method="semantic",
                debug_info={
                    "query_embedding_dim": len(query_embedding),
                    "candidate_count": len(candidate_ids),
                    "above_threshold": len(scored),
                },
            ))

        return results

    def recall_by_embedding(
        self,
        embedding: list[float],
        scenario: str | None = None,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> list[RecallResult]:
        """直接用 embedding 召回。

        Args:
            embedding: 查询向量
            scenario: 场景名（可选过滤）
            user_id: 用户 ID（可选过滤）
            top_k: 返回数量

        Returns:
            RecallResult 列表
        """
        # 获取候选集
        if scenario:
            candidate_ids = self._get_candidates(scenario, user_id)
        else:
            candidate_ids = set(self._index.keys())

        if not candidate_ids:
            return []

        # 计算相似度
        scored: list[tuple[float, str]] = []
        for dec_id in candidate_ids:
            indexed = self._index.get(dec_id)
            if indexed is None:
                continue
            sim = cosine_similarity(embedding, indexed.embedding)
            if sim >= self._similarity_threshold:
                scored.append((sim, dec_id))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[RecallResult] = []
        for score, dec_id in scored[:top_k]:
            indexed = self._index[dec_id]
            record = self._indexed_to_record(indexed)
            results.append(RecallResult(
                record=record,
                score=round(score, 4),
                method="semantic",
                debug_info={"embedding_dim": len(embedding)},
            ))

        return results

    # ── 管理接口 ─────────────────────────────────────────────

    @property
    def index_size(self) -> int:
        """当前索引记录数。"""
        return len(self._index)

    def is_indexed(self, decision_id: str) -> bool:
        """检查决策记录是否已索引。"""
        return decision_id in self._index

    def remove(self, decision_id: str) -> bool:
        """从索引中移除记录。"""
        indexed = self._index.pop(decision_id, None)
        if indexed is None:
            return False
        # 清理场景索引
        scenario_set = self._scenario_index.get(indexed.scenario)
        if scenario_set:
            scenario_set.discard(decision_id)
        # 清理用户+场景索引
        key = (indexed.user_id, indexed.scenario)
        user_scenario_set = self._user_scenario_index.get(key)
        if user_scenario_set:
            user_scenario_set.discard(decision_id)
        return True

    def clear(self) -> None:
        """清空所有索引。"""
        self._index.clear()
        self._scenario_index.clear()
        self._user_scenario_index.clear()

    def get_stats(self) -> dict[str, Any]:
        """获取索引统计。"""
        return {
            "total_records": len(self._index),
            "scenarios": {k: len(v) for k, v in self._scenario_index.items()},
            "embedding_dim": self._provider.dimension(),
            "similarity_threshold": self._similarity_threshold,
            "max_index_size": self._max_index_size,
        }

    # ── 私有方法 ─────────────────────────────────────────────

    def _get_candidates(self, scenario: str, user_id: str | None = None) -> set[str]:
        """获取候选决策 ID 集合。"""
        if user_id:
            key = (user_id, scenario)
            return self._user_scenario_index.get(key, set())
        return self._scenario_index.get(scenario, set())

    def _indexed_to_record(self, indexed: IndexedRecord) -> DecisionRecord:
        """从索引记录恢复 DecisionRecord（最简版本）。"""
        return DecisionRecord(
            decision_id=indexed.decision_id,
            user_id=indexed.user_id,
            scenario=indexed.scenario,
            query=indexed.query,
            options=[],         # 索引不存储完整选项
            recommended={},     # 索引不存储推荐
            created_at=indexed.created_at or datetime.now(UTC).isoformat(),
        )

    def _evict_oldest(self) -> None:
        """移除最早的索引记录（FIFO）。"""
        if not self._index:
            return
        # 找到 created_at 最早的记录
        oldest_id = min(
            self._index.keys(),
            key=lambda k: self._index[k].created_at,
        )
        self.remove(oldest_id)


# ── HybridRecallEngine ──────────────────────────────────────

class HybridRecallEngine:
    """混合召回引擎：语义优先 + keyword fallback。

    工作流：
    1. 先用 SemanticRecallEngine 尝试语义召回
    2. 语义召回不足时，补充 keyword 召回
    3. 去重并合并结果
    """

    def __init__(
        self,
        semantic_engine: SemanticRecallEngine | None = None,
        keyword_fallback: Any | None = None,
    ) -> None:
        """初始化混合召回引擎。

        Args:
            semantic_engine: 语义召回引擎
            keyword_fallback: keyword fallback 对象（需有 recall_similar 方法）
        """
        self._semantic = semantic_engine or SemanticRecallEngine()
        self._keyword_fallback = keyword_fallback

    def recall(
        self,
        query: str,
        scenario: str,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> list[RecallResult]:
        """混合召回：语义优先 + keyword fallback。

        Args:
            query: 查询文本
            scenario: 场景名
            user_id: 用户 ID
            top_k: 返回数量

        Returns:
            RecallResult 列表
        """
        # 1. 语义召回
        semantic_results = self._semantic.recall(
            query=query, scenario=scenario, user_id=user_id, top_k=top_k,
        )

        # 2. 如果语义召回足够，直接返回
        if len(semantic_results) >= top_k:
            return semantic_results[:top_k]

        # 3. 不足时用 keyword 补充
        keyword_results = self._keyword_recall(
            query=query, scenario=scenario, user_id=user_id,
            limit=top_k - len(semantic_results),
        )

        # 4. 去重合并
        seen_ids = {r.record.decision_id for r in semantic_results}
        merged = list(semantic_results)
        for kr in keyword_results:
            if kr.record.decision_id not in seen_ids:
                merged.append(kr)
                seen_ids.add(kr.record.decision_id)

        return merged[:top_k]

    def _keyword_recall(
        self,
        query: str,
        scenario: str,
        user_id: str | None = None,
        limit: int = 5,
    ) -> list[RecallResult]:
        """使用 keyword fallback 召回。"""
        if self._keyword_fallback is None:
            return []

        try:
            records = self._keyword_fallback.recall_similar(
                user_id=user_id or "",
                scenario=scenario,
                query=query,
                limit=limit,
            )
            return [
                RecallResult(
                    record=r,
                    score=0.0,  # keyword 无法提供语义分数
                    method="keyword_fallback",
                )
                for r in records
            ]
        except Exception:
            return []

    @property
    def semantic_engine(self) -> SemanticRecallEngine:
        """获取底层语义引擎。"""
        return self._semantic
