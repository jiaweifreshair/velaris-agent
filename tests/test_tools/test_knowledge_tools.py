"""知识库与自进化工具测试。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.knowledge_ingest_tool import KnowledgeIngestInput, KnowledgeIngestTool
from openharness.tools.knowledge_lint_tool import KnowledgeLintInput, KnowledgeLintTool
from openharness.tools.knowledge_query_tool import KnowledgeQueryInput, KnowledgeQueryTool
from openharness.tools.save_decision_tool import SaveDecisionInput, SaveDecisionTool
from openharness.tools.self_evolution_review_tool import (
    SelfEvolutionReviewInput,
    SelfEvolutionReviewTool,
)
from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.memory.types import DecisionRecord


def _ctx(tmp_path: Path) -> ToolExecutionContext:
    """构造同时包含决策记忆与知识库路径的执行上下文。"""
    return ToolExecutionContext(
        cwd=tmp_path,
        metadata={
            "decision_memory_dir": str(tmp_path / "decisions"),
            "knowledge_base_dir": str(tmp_path / "knowledge"),
            "evolution_report_dir": str(tmp_path / "evolution-reports"),
            "evolution_review_interval": 2,
        },
    )


@pytest.mark.asyncio
async def test_knowledge_ingest_query_lint_tools(tmp_path: Path) -> None:
    """知识库工具应支持 ingest/query/lint 三步闭环。"""
    context = _ctx(tmp_path)

    ingest_result = await KnowledgeIngestTool().execute(
        KnowledgeIngestInput(
            user_id="u-kb",
            title="Hermes 自进化拆解",
            content="前后台分离 review + 分层记忆 + 技能沉淀。",
            source_uri="https://example.com/hermes",
            tags=["agent", "evolution"],
        ),
        context,
    )
    assert ingest_result.is_error is False
    ingest_data = json.loads(ingest_result.output)
    assert ingest_data["status"] == "ingested"

    query_result = await KnowledgeQueryTool().execute(
        KnowledgeQueryInput(user_id="u-kb", query="分层记忆", limit=5),
        context,
    )
    assert query_result.is_error is False
    query_data = json.loads(query_result.output)
    assert query_data["total_found"] >= 1

    lint_result = await KnowledgeLintTool().execute(
        KnowledgeLintInput(user_id="u-kb"),
        context,
    )
    assert lint_result.is_error is False
    lint_data = json.loads(lint_result.output)
    assert "issues" in lint_data


def _seed_decisions_for_evolution(tmp_path: Path) -> None:
    """写入两条历史样本，为自进化测试准备数据。"""
    memory = DecisionMemory(base_dir=tmp_path / "decisions")
    now = datetime.now(timezone.utc)
    memory.save(
        DecisionRecord(
            decision_id="dec-seed-1",
            user_id="u-evo",
            scenario="travel",
            query="北京去上海",
            options_discovered=[{"id": "fast"}, {"id": "cheap"}],
            recommended={"id": "cheap", "label": "便宜方案"},
            user_choice={"id": "fast", "label": "快速方案"},
            user_feedback=3.0,
            scores=[
                {"id": "cheap", "scores": {"price": 0.9, "comfort": 0.3}},
                {"id": "fast", "scores": {"price": 0.3, "comfort": 0.9}},
            ],
            created_at=now,
        )
    )
    memory.save(
        DecisionRecord(
            decision_id="dec-seed-2",
            user_id="u-evo",
            scenario="travel",
            query="上海回北京",
            options_discovered=[{"id": "fast"}, {"id": "cheap"}],
            recommended={"id": "cheap", "label": "便宜方案"},
            user_choice={"id": "fast", "label": "快速方案"},
            user_feedback=2.9,
            scores=[
                {"id": "cheap", "scores": {"price": 0.9, "comfort": 0.3}},
                {"id": "fast", "scores": {"price": 0.2, "comfort": 0.9}},
            ],
            created_at=now,
        )
    )


@pytest.mark.asyncio
async def test_self_evolution_review_tool_and_save_trigger(tmp_path: Path) -> None:
    """自进化工具和 save_decision 自动触发应返回结构化结果。"""
    context = _ctx(tmp_path)
    _seed_decisions_for_evolution(tmp_path)

    review_result = await SelfEvolutionReviewTool().execute(
        SelfEvolutionReviewInput(
            user_id="u-evo",
            scenario="travel",
            window=20,
            persist_report=True,
        ),
        context,
    )
    assert review_result.is_error is False
    review_data = json.loads(review_result.output)
    assert review_data["sample_size"] >= 2
    assert "actions" in review_data

    save_result = await SaveDecisionTool().execute(
        SaveDecisionInput(
            user_id="u-save",
            scenario="travel",
            query="机票方案选择",
            recommended={"id": "cheap", "label": "便宜方案"},
            alternatives=[{"id": "fast", "label": "快速方案"}],
            options_discovered=[{"id": "cheap"}, {"id": "fast"}],
            weights_used={"price": 0.6, "comfort": 0.4},
            explanation="预算优先",
        ),
        context,
    )
    assert save_result.is_error is False
    first = json.loads(save_result.output)
    assert first["self_evolution"]["triggered"] is False

    save_result_2 = await SaveDecisionTool().execute(
        SaveDecisionInput(
            user_id="u-save",
            scenario="travel",
            query="高铁方案选择",
            recommended={"id": "cheap", "label": "便宜方案"},
            alternatives=[{"id": "fast", "label": "快速方案"}],
            options_discovered=[{"id": "cheap"}, {"id": "fast"}],
            weights_used={"price": 0.6, "comfort": 0.4},
            explanation="预算优先",
        ),
        context,
    )
    second = json.loads(save_result_2.output)
    assert second["self_evolution"]["triggered"] is True
    assert second["self_evolution"]["queued"] is False


@pytest.mark.asyncio
async def test_save_decision_queues_self_evolution_when_postgres_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """启用 PostgreSQL 且命中 review interval 时，应入队而不是同步执行自进化。"""

    context = ToolExecutionContext(
        cwd=tmp_path,
        metadata={
            "decision_memory_dir": str(tmp_path / "decisions"),
            "knowledge_base_dir": str(tmp_path / "knowledge"),
            "evolution_report_dir": str(tmp_path / "evolution-reports"),
            "evolution_review_interval": 2,
            "postgres_dsn": "postgresql://user:pass@localhost:5432/velaris",
        },
    )
    memory = DecisionMemory(base_dir=tmp_path / "decisions")
    queued_calls: list[dict[str, object]] = []

    class _FakeQueue:
        """记录入队参数的伪队列。"""

        def enqueue(
            self,
            job_type: str,
            idempotency_key: str,
            payload: dict[str, object],
        ) -> str:
            """记录一次 enqueue 调用，并返回稳定的 job_id。"""

            queued_calls.append(
                {
                    "job_type": job_type,
                    "idempotency_key": idempotency_key,
                    "payload": dict(payload),
                }
            )
            return "job-self-evo-001"

    def fake_build_decision_memory(postgres_dsn: str = "", base_dir: str | Path | None = None):
        """复用文件后端，避免测试依赖真实 PostgreSQL。"""

        assert postgres_dsn == "postgresql://user:pass@localhost:5432/velaris"
        assert base_dir == str(tmp_path / "decisions")
        return memory

    def fake_build_job_queue(postgres_dsn: str = "") -> _FakeQueue | None:
        """在传入 PostgreSQL DSN 时返回伪队列。"""

        assert postgres_dsn == "postgresql://user:pass@localhost:5432/velaris"
        return _FakeQueue()

    def fail_review(*args, **kwargs):
        """若同步 review 被调用，直接让测试失败。"""

        raise AssertionError("save_decision 不应在启用队列时同步执行 SelfEvolutionEngine.review")

    monkeypatch.setattr(
        "velaris_agent.persistence.factory.build_decision_memory",
        fake_build_decision_memory,
    )
    monkeypatch.setattr(
        "velaris_agent.persistence.factory.build_job_queue",
        fake_build_job_queue,
    )
    monkeypatch.setattr(
        "velaris_agent.evolution.self_evolution.SelfEvolutionEngine.review",
        fail_review,
    )

    tool = SaveDecisionTool()
    first = json.loads(
        (
            await tool.execute(
                SaveDecisionInput(
                    user_id="u-save",
                    scenario="travel",
                    query="机票方案选择",
                    recommended={"id": "cheap", "label": "便宜方案"},
                    alternatives=[{"id": "fast", "label": "快速方案"}],
                    options_discovered=[{"id": "cheap"}, {"id": "fast"}],
                    weights_used={"price": 0.6, "comfort": 0.4},
                    explanation="预算优先",
                ),
                context,
            )
        ).output
    )
    assert first["self_evolution"]["triggered"] is False
    assert first["self_evolution"]["queued"] is False

    second_result = await tool.execute(
        SaveDecisionInput(
            user_id="u-save",
            scenario="travel",
            query="高铁方案选择",
            recommended={"id": "cheap", "label": "便宜方案"},
            alternatives=[{"id": "fast", "label": "快速方案"}],
            options_discovered=[{"id": "cheap"}, {"id": "fast"}],
            weights_used={"price": 0.6, "comfort": 0.4},
            explanation="预算优先",
        ),
        context,
    )
    assert second_result.is_error is False

    second = json.loads(second_result.output)
    assert second["self_evolution"]["triggered"] is False
    assert second["self_evolution"]["queued"] is True
    assert second["self_evolution"]["job_id"] == "job-self-evo-001"
    assert queued_calls and queued_calls[0]["job_type"] == "self_evolution_review"
