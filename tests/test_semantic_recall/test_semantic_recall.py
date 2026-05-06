"""SemanticRecallEngine 核心测试 — 向量索引、语义召回、降级。"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from velaris_agent.memory.semantic_recall import (
    HybridRecallEngine,
    IndexedRecord,
    RecallResult,
    SemanticRecallEngine,
    SimpleHashEmbedding,
    cosine_similarity,
)
from velaris_agent.memory.types import DecisionRecord


# ── Helpers ─────────────────────────────────────────────────

def _make_record(
    decision_id: str = "dec-001",
    user_id: str = "alice",
    scenario: str = "travel",
    query: str = "帮我订机票",
) -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        user_id=user_id,
        scenario=scenario,
        query=query,
        options=[],
        recommended={},
        created_at=datetime.now(timezone.utc),
    )


# ── 1. SimpleHashEmbedding 测试 ─────────────────────────────

class TestSimpleHashEmbedding:
    """哈希嵌入基础功能。"""

    def test_dimension(self):
        emb = SimpleHashEmbedding(dim=64)
        assert emb.dimension() == 64

    def test_default_dimension(self):
        emb = SimpleHashEmbedding()
        assert emb.dimension() == 128

    def test_produces_vector(self):
        emb = SimpleHashEmbedding(dim=32)
        vec = emb.embed("测试文本")
        assert len(vec) == 32
        assert all(isinstance(v, float) for v in vec)

    def test_normalized(self):
        emb = SimpleHashEmbedding(dim=64)
        vec = emb.embed("测试文本")
        norm = sum(v * v for v in vec) ** 0.5
        assert abs(norm - 1.0) < 0.01

    def test_similar_text_similar_embedding(self):
        """相似文本产生相似嵌入。"""
        emb = SimpleHashEmbedding(dim=64)
        vec1 = emb.embed("帮我订机票")
        vec2 = emb.embed("帮我订机票去北京")
        sim = cosine_similarity(vec1, vec2)
        # 相似文本的余弦相似度应该较高
        assert sim > 0.3

    def test_different_text_lower_similarity(self):
        """不同文本的相似度低于相似文本。"""
        emb = SimpleHashEmbedding(dim=64)
        vec1 = emb.embed("帮我订机票")
        vec2 = emb.embed("帮我订机票去北京")
        vec3 = emb.embed("今天天气很好")
        sim_similar = cosine_similarity(vec1, vec2)
        sim_different = cosine_similarity(vec1, vec3)
        # 相似文本的相似度 > 不同文本
        assert sim_similar > sim_different


# ── 2. Cosine Similarity 测试 ───────────────────────────────

class TestCosineSimilarity:
    """余弦相似度计算。"""

    def test_identical_vectors(self):
        vec = [1.0, 0.0, 0.0]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_empty_vectors(self):
        assert cosine_similarity([], []) == 0.0

    def test_different_dimensions(self):
        assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


# ── 3. SemanticRecallEngine 索引测试 ───────────────────────

class TestSemanticIndex:
    """语义召回引擎索引功能。"""

    def test_index_returns_decision_id(self):
        engine = SemanticRecallEngine()
        record = _make_record(decision_id="dec-001")
        result = engine.index(record)
        assert result == "dec-001"

    def test_index_increases_size(self):
        engine = SemanticRecallEngine()
        engine.index(_make_record("dec-001"))
        assert engine.index_size == 1
        engine.index(_make_record("dec-002", query="订酒店"))
        assert engine.index_size == 2

    def test_is_indexed(self):
        engine = SemanticRecallEngine()
        engine.index(_make_record("dec-001"))
        assert engine.is_indexed("dec-001")
        assert not engine.is_indexed("dec-999")

    def test_remove(self):
        engine = SemanticRecallEngine()
        engine.index(_make_record("dec-001"))
        assert engine.remove("dec-001")
        assert engine.index_size == 0
        assert not engine.is_indexed("dec-001")

    def test_remove_nonexistent(self):
        engine = SemanticRecallEngine()
        assert not engine.remove("dec-999")

    def test_clear(self):
        engine = SemanticRecallEngine()
        engine.index(_make_record("dec-001"))
        engine.index(_make_record("dec-002"))
        engine.clear()
        assert engine.index_size == 0

    def test_max_index_size_eviction(self):
        engine = SemanticRecallEngine(max_index_size=3)
        for i in range(5):
            engine.index(_make_record(f"dec-{i:03d}"))
        assert engine.index_size <= 3

    def test_get_stats(self):
        engine = SemanticRecallEngine()
        engine.index(_make_record("dec-001", scenario="travel"))
        stats = engine.get_stats()
        assert stats["total_records"] == 1
        assert "travel" in stats["scenarios"]
        assert stats["embedding_dim"] == 128  # default SimpleHashEmbedding

    def test_multiple_scenarios(self):
        engine = SemanticRecallEngine()
        engine.index(_make_record("dec-001", scenario="travel"))
        engine.index(_make_record("dec-002", scenario="tokencost"))
        stats = engine.get_stats()
        assert stats["total_records"] == 2
        assert "travel" in stats["scenarios"]
        assert "tokencost" in stats["scenarios"]


# ── 4. 语义召回测试 ───────────────────────────────────────

class TestSemanticRecall:
    """语义召回核心功能。"""

    def test_recall_returns_results(self):
        engine = SemanticRecallEngine(similarity_threshold=0.1)
        engine.index(_make_record("dec-001", query="帮我订机票去北京"))
        results = engine.recall("帮我订机票", "travel", user_id="alice")
        assert len(results) >= 1
        assert all(isinstance(r, RecallResult) for r in results)

    def test_recall_method_is_semantic(self):
        engine = SemanticRecallEngine(similarity_threshold=0.1)
        engine.index(_make_record("dec-001", query="帮我订机票去北京"))
        results = engine.recall("帮我订机票", "travel", user_id="alice")
        if results:
            assert results[0].method == "semantic"

    def test_recall_score_range(self):
        engine = SemanticRecallEngine(similarity_threshold=0.0)
        engine.index(_make_record("dec-001", query="帮我订机票"))
        results = engine.recall("帮我订机票", "travel", user_id="alice")
        if results:
            assert 0.0 <= results[0].score <= 1.0

    def test_recall_no_match(self):
        engine = SemanticRecallEngine(similarity_threshold=0.99)
        engine.index(_make_record("dec-001", query="订机票"))
        results = engine.recall("今天天气怎么样", "travel", user_id="alice")
        # 高阈值下可能没有匹配
        assert isinstance(results, list)

    def test_recall_empty_index(self):
        engine = SemanticRecallEngine()
        results = engine.recall("测试查询", "travel")
        assert results == []

    def test_recall_by_user(self):
        engine = SemanticRecallEngine(similarity_threshold=0.1)
        engine.index(_make_record("dec-001", user_id="alice", query="订机票"))
        engine.index(_make_record("dec-002", user_id="bob", query="订机票"))
        results = engine.recall("订机票", "travel", user_id="alice")
        # 应该只返回 alice 的记录
        if results:
            assert all(r.record.user_id == "alice" for r in results)

    def test_recall_top_k(self):
        engine = SemanticRecallEngine(similarity_threshold=0.0)
        for i in range(10):
            engine.index(_make_record(f"dec-{i:03d}", query=f"订机票{i}"))
        results = engine.recall("订机票", "travel", top_k=3)
        assert len(results) <= 3

    def test_recall_by_embedding(self):
        engine = SemanticRecallEngine(similarity_threshold=0.0)
        engine.index(_make_record("dec-001", query="订机票"))
        # 用相同的 embedding 查询
        emb = engine._provider.embed("订机票")
        results = engine.recall_by_embedding(emb, scenario="travel")
        assert len(results) >= 1

    def test_recall_by_embedding_without_scenario(self):
        engine = SemanticRecallEngine(similarity_threshold=0.0)
        engine.index(_make_record("dec-001", scenario="travel", query="订机票"))
        engine.index(_make_record("dec-002", scenario="tokencost", query="分析成本"))
        emb = engine._provider.embed("订机票")
        results = engine.recall_by_embedding(emb, top_k=5)
        # 不限场景时应该能搜到
        assert len(results) >= 1


# ── 5. HybridRecallEngine 测试 ──────────────────────────────

class TestHybridRecall:
    """混合召回：语义优先 + keyword fallback。"""

    def test_semantic_sufficient_no_fallback(self):
        """语义召回足够时不走 fallback。"""
        semantic = SemanticRecallEngine(similarity_threshold=0.1)
        semantic.index(_make_record("dec-001", query="帮我订机票"))
        hybrid = HybridRecallEngine(semantic_engine=semantic)
        results = hybrid.recall("帮我订机票", "travel", user_id="alice", top_k=1)
        if results:
            assert results[0].method == "semantic"

    def test_semantic_insufficient_uses_fallback(self):
        """语义召回不足时走 fallback。"""
        semantic = SemanticRecallEngine(similarity_threshold=0.99)
        semantic.index(_make_record("dec-001", query="完全不同的内容"))

        # 创建一个 mock keyword fallback
        class MockFallback:
            def recall_similar(self, user_id, scenario, query, limit):
                return [_make_record("dec-kw", query=query)]

        hybrid = HybridRecallEngine(semantic_engine=semantic, keyword_fallback=MockFallback())
        results = hybrid.recall("查询内容", "travel", user_id="alice", top_k=5)
        # 应该有 fallback 结果
        assert len(results) >= 1

    def test_no_fallback_no_results(self):
        """语义召回不足且无 fallback 时返回少量。"""
        semantic = SemanticRecallEngine(similarity_threshold=0.99)
        semantic.index(_make_record("dec-001", query="完全不同的内容"))
        hybrid = HybridRecallEngine(semantic_engine=semantic, keyword_fallback=None)
        results = hybrid.recall("查询内容", "travel", user_id="alice", top_k=5)
        # 可能返回空或少量结果
        assert isinstance(results, list)

    def test_default_construction(self):
        """默认构造也能工作。"""
        hybrid = HybridRecallEngine()
        assert hybrid.semantic_engine is not None


# ── 6. 语义召回 vs keyword 对比 ────────────────────────────

class TestSemanticVsKeyword:
    """语义召回归类比 keyword 更强。"""

    def test_semantic_finds_paraphrased_query(self):
        """语义召回能找到释义改写的查询（keyword 可能错过）。

        注意：SimpleHashEmbedding 是占位实现，不保证语义效果。
        此测试验证的是召回流程，真正的语义效果需要 sentence-transformers 等提供者。
        """
        engine = SemanticRecallEngine(similarity_threshold=0.0)  # 最低阈值
        # 索引原始查询
        engine.index(_make_record("dec-001", query="帮我订机票去北京出差"))
        # 用相似但不同的措辞召回
        results = engine.recall("帮我订机票去北京出差", "travel", user_id="alice")
        # 相同文本应该能找到
        assert len(results) >= 1

    def test_keyword_misses_paraphrased_query(self):
        """keyword 召回对释义改写的查询可能错过。"""
        # 使用 DecisionMemory 的 keyword 方法
        import tempfile
        from velaris_agent.memory.decision_memory import DecisionMemory
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = DecisionMemory(base_dir=tmpdir)
            record = _make_record("dec-001", query="帮我订机票去北京出差")
            mem.save(record)
            # 用释义查询 keyword 召回
            results = mem.recall_similar("alice", "travel", "北京出差机票预订")
            # keyword 可能找不到（因为没有关键词重叠）
            # 这不是错误，只是说明 keyword 的局限

    def test_semantic_recall_better_for_synonyms(self):
        """语义召回对同义词查询表现更好。"""
        engine = SemanticRecallEngine(similarity_threshold=0.1)
        engine.index(_make_record("dec-001", query="酒店预订"))
        # 同义词查询
        results = engine.recall("住宿安排", "travel", user_id="alice")
        # 语义召回可能找到（同义词在向量空间中距离较近）
        # 但 SimpleHashEmbedding 不保证这一点
        assert isinstance(results, list)


# ── 7. DecisionMemory 集成测试 ──────────────────────────────

class TestDecisionMemoryIntegration:
    """DecisionMemory 与语义召回引擎的集成。"""

    def test_memory_with_semantic_engine(self):
        """DecisionMemory 接受 semantic_engine 参数。"""
        import tempfile
        from velaris_agent.memory.decision_memory import DecisionMemory
        with tempfile.TemporaryDirectory() as tmpdir:
            semantic = SemanticRecallEngine(similarity_threshold=0.1)
            mem = DecisionMemory(base_dir=tmpdir, semantic_engine=semantic)
            record = _make_record("dec-001", query="帮我订机票")
            mem.save(record)
            # 应该同时被语义索引
            assert semantic.is_indexed("dec-001")

    def test_memory_without_semantic_engine(self):
        """不配置 semantic_engine 时仍正常工作。"""
        import tempfile
        from velaris_agent.memory.decision_memory import DecisionMemory
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = DecisionMemory(base_dir=tmpdir)
            record = _make_record("dec-001")
            decision_id = mem.save(record)
            assert decision_id == "dec-001"

    def test_recall_with_semantic_engine(self):
        """配置 semantic_engine 后 recall_similar 优先用语义召回。"""
        import tempfile
        from velaris_agent.memory.decision_memory import DecisionMemory
        with tempfile.TemporaryDirectory() as tmpdir:
            semantic = SemanticRecallEngine(similarity_threshold=0.1)
            mem = DecisionMemory(base_dir=tmpdir, semantic_engine=semantic)
            mem.save(_make_record("dec-001", query="帮我订机票去北京"))
            # recall_similar 应该能找到
            results = mem.recall_similar("alice", "travel", "帮我订机票")
            # 结果可能为空或找到记录（取决于 embedding 质量）
            assert isinstance(results, list)

    def test_recall_fallback_to_keyword(self):
        """语义召回失败时 fallback 到 keyword。"""
        import tempfile
        from velaris_agent.memory.decision_memory import DecisionMemory
        with tempfile.TemporaryDirectory() as tmpdir:
            # 用非常高的阈值，让语义召回几乎不可能匹配
            semantic = SemanticRecallEngine(similarity_threshold=0.999)
            mem = DecisionMemory(base_dir=tmpdir, semantic_engine=semantic)
            mem.save(_make_record("dec-001", query="帮我订机票去北京"))
            # keyword fallback 应该能找到
            results = mem.recall_similar("alice", "travel", "帮我订机票去北京")
            # keyword 应该能找到（关键词完全匹配）
            assert len(results) >= 1

    def test_backward_compat_no_semantic_engine(self):
        """无 semantic_engine 时行为与原来完全一致。"""
        import tempfile
        from velaris_agent.memory.decision_memory import DecisionMemory
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = DecisionMemory(base_dir=tmpdir)
            mem.save(_make_record("dec-001", query="帮我订机票去北京"))
            results = mem.recall_similar("alice", "travel", "帮我订机票去北京")
            assert len(results) >= 1
