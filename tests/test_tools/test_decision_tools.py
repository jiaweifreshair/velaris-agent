"""决策相关工具测试 (4个新工具)。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.decision_score_tool import DecisionScoreInput, DecisionScoreTool
from openharness.tools.recall_decisions_tool import RecallDecisionsInput, RecallDecisionsTool
from openharness.tools.recall_preferences_tool import RecallPreferencesInput, RecallPreferencesTool
from openharness.tools.save_decision_tool import SaveDecisionInput, SaveDecisionTool
from velaris_agent.memory.types import DecisionRecord
from velaris_agent.persistence.factory import build_decision_memory
from velaris_agent.persistence.schema import bootstrap_sqlite_schema
from velaris_agent.persistence.sqlite_helpers import get_project_database_path


def _ctx(tmp_path: Path) -> ToolExecutionContext:
    """构造带 decision_memory_dir 的执行上下文。"""

    bootstrap_sqlite_schema(get_project_database_path(tmp_path))
    return ToolExecutionContext(
        cwd=tmp_path,
        metadata={"decision_memory_dir": str(tmp_path / "decisions")},
    )


def _seed_records(tmp_path: Path, count: int = 3):
    """在 tmp_path 下预写入一批决策记录。"""

    mem = build_decision_memory(base_dir=tmp_path / "decisions", cwd=tmp_path)
    for i in range(count):
        rec = DecisionRecord(
            decision_id=f"dec-seed{i:03d}",
            user_id="u-test",
            scenario="travel",
            query=f"北京到上海 查询{i}",
            recommended={"id": f"opt-{i}", "label": f"选项{i}"},
            user_choice={"id": f"opt-{i}", "label": f"选项{i}"},
            user_feedback=4.0 + i * 0.2,
            scores=[
                {"id": f"opt-{i}", "scores": {"price": 0.8, "time": 0.6, "comfort": 0.5}},
            ],
            weights_used={"price": 0.4, "time": 0.35, "comfort": 0.25},
            created_at=datetime.now(timezone.utc),
        )
        mem.save(rec)
    return mem


# --- RecallPreferencesTool ---


@pytest.mark.asyncio
async def test_recall_preferences_tool_returns_weights(tmp_path: Path):
    """偏好召回工具: 有历史时返回权重和行为指标。"""
    _seed_records(tmp_path, count=5)
    ctx = _ctx(tmp_path)

    result = await RecallPreferencesTool().execute(
        RecallPreferencesInput(user_id="u-test", scenario="travel"),
        ctx,
    )
    assert result.is_error is False

    data = json.loads(result.output)
    assert data["user_id"] == "u-test"
    assert data["scenario"] == "travel"
    assert "price" in data["weights"]
    assert data["total_decisions"] == 5
    assert data["confidence"] > 0


@pytest.mark.asyncio
async def test_recall_preferences_tool_new_user(tmp_path: Path):
    """偏好召回工具: 新用户返回默认权重, confidence=0。"""
    ctx = _ctx(tmp_path)

    result = await RecallPreferencesTool().execute(
        RecallPreferencesInput(user_id="brand-new", scenario="travel"),
        ctx,
    )
    assert result.is_error is False

    data = json.loads(result.output)
    assert data["total_decisions"] == 0
    assert data["confidence"] == 0


# --- RecallDecisionsTool ---


@pytest.mark.asyncio
async def test_recall_decisions_tool_returns_similar(tmp_path: Path):
    """历史决策召回工具: 返回匹配的摘要。"""
    _seed_records(tmp_path, count=3)
    ctx = _ctx(tmp_path)

    result = await RecallDecisionsTool().execute(
        RecallDecisionsInput(
            user_id="u-test",
            scenario="travel",
            query="北京到上海",
            limit=5,
        ),
        ctx,
    )
    assert result.is_error is False

    data = json.loads(result.output)
    assert data["total_found"] >= 1
    assert "decisions" in data
    # 摘要包含关键字段
    first = data["decisions"][0]
    assert "decision_id" in first
    assert "query" in first
    assert "user_feedback" in first


@pytest.mark.asyncio
async def test_recall_decisions_tool_empty(tmp_path: Path):
    """历史决策召回工具: 无匹配时返回空列表。"""
    ctx = _ctx(tmp_path)

    result = await RecallDecisionsTool().execute(
        RecallDecisionsInput(
            user_id="nobody",
            scenario="travel",
            query="完全无关的查询",
        ),
        ctx,
    )
    assert result.is_error is False

    data = json.loads(result.output)
    assert data["total_found"] == 0


# --- SaveDecisionTool ---


@pytest.mark.asyncio
async def test_save_decision_tool_persists(tmp_path: Path):
    """决策保存工具: 保存后能通过 DecisionMemory 读取。"""
    ctx = _ctx(tmp_path)

    result = await SaveDecisionTool().execute(
        SaveDecisionInput(
            user_id="u-save",
            scenario="tokencost",
            query="选择最便宜的模型",
            recommended={"id": "gpt-4o-mini", "label": "GPT-4o Mini"},
            alternatives=[{"id": "gpt-4o", "label": "GPT-4o"}],
            weights_used={"cost": 0.5, "quality": 0.35, "speed": 0.15},
            explanation="GPT-4o Mini 成本最低且质量足够",
            tools_called=["model_search"],
        ),
        ctx,
    )
    assert result.is_error is False

    data = json.loads(result.output)
    assert data["status"] == "saved"
    decision_id = data["decision_id"]
    assert decision_id.startswith("dec-")

    # 验证持久化
    mem = build_decision_memory(base_dir=tmp_path / "decisions", cwd=tmp_path)
    record = mem.get(decision_id)
    assert record is not None
    assert record.user_id == "u-save"
    assert record.scenario == "tokencost"
    assert record.recommended["id"] == "gpt-4o-mini"


# --- DecisionScoreTool ---


@pytest.mark.asyncio
async def test_decision_score_tool_with_explicit_weights(tmp_path: Path):
    """评分工具: 使用显式权重排序。"""
    ctx = _ctx(tmp_path)

    options = [
        {"id": "a", "label": "选项A", "scores": {"price": 0.9, "quality": 0.3}},
        {"id": "b", "label": "选项B", "scores": {"price": 0.4, "quality": 0.8}},
    ]

    # price 权重高 -> 选项A应排第一
    result = await DecisionScoreTool().execute(
        DecisionScoreInput(
            options=options,
            weights={"price": 0.8, "quality": 0.2},
        ),
        ctx,
    )
    assert result.is_error is False

    data = json.loads(result.output)
    assert data["personalized"] is False
    ranked = data["ranked_options"]
    assert ranked[0]["id"] == "a"
    assert ranked[1]["id"] == "b"


@pytest.mark.asyncio
async def test_decision_score_tool_with_personalized_weights(tmp_path: Path):
    """评分工具: 有用户历史时使用个性化权重。"""
    # 先 seed 历史数据
    _seed_records(tmp_path, count=5)
    ctx = _ctx(tmp_path)

    options = [
        {"id": "x", "label": "X", "scores": {"price": 0.7, "time": 0.5, "comfort": 0.3}},
        {"id": "y", "label": "Y", "scores": {"price": 0.4, "time": 0.8, "comfort": 0.9}},
    ]

    result = await DecisionScoreTool().execute(
        DecisionScoreInput(
            options=options,
            user_id="u-test",
            scenario="travel",
        ),
        ctx,
    )
    assert result.is_error is False

    data = json.loads(result.output)
    # 有历史数据 -> 应使用个性化权重
    assert data["personalized"] is True
    assert "note" in data
    assert len(data["ranked_options"]) == 2


@pytest.mark.asyncio
async def test_decision_score_tool_no_weights_error(tmp_path: Path):
    """评分工具: 无权重且无用户历史时返回错误。"""
    ctx = _ctx(tmp_path)

    result = await DecisionScoreTool().execute(
        DecisionScoreInput(
            options=[{"id": "a", "scores": {"x": 0.5}}],
            # 不提供 weights, 也不提供 user_id
        ),
        ctx,
    )
    assert result.is_error is True
    assert "权重" in result.output or "weights" in result.output.lower()
