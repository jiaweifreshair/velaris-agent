"""偏好学习器测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.memory.preference_learner import (
    DEFAULT_WEIGHTS,
    PreferenceLearner,
)
from velaris_agent.memory.types import DecisionRecord


def _make_record(
    decision_id: str,
    user_id: str = "u1",
    scenario: str = "travel",
    query: str = "测试查询",
    recommended_id: str = "opt-a",
    chosen_id: str | None = None,
    feedback: float | None = None,
    scores: list | None = None,
) -> DecisionRecord:
    """快速构造一条决策记录。"""
    chosen_id = chosen_id or recommended_id
    return DecisionRecord(
        decision_id=decision_id,
        user_id=user_id,
        scenario=scenario,
        query=query,
        recommended={"id": recommended_id, "label": f"选项{recommended_id}"},
        user_choice={"id": chosen_id, "label": f"选项{chosen_id}"},
        user_feedback=feedback,
        scores=scores or [
            {"id": "opt-a", "scores": {"price": 0.8, "time": 0.6, "comfort": 0.5}},
            {"id": "opt-b", "scores": {"price": 0.3, "time": 0.9, "comfort": 0.9}},
        ],
        weights_used={"price": 0.4, "time": 0.35, "comfort": 0.25},
        created_at=datetime.now(timezone.utc),
    )


def test_no_history_returns_defaults(tmp_path: Path):
    """新用户获得场景默认权重, confidence=0。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    learner = PreferenceLearner(mem)

    prefs = learner.compute_preferences("new-user", "travel")
    assert prefs.total_decisions == 0
    assert prefs.confidence == 0.0
    assert prefs.weights == DEFAULT_WEIGHTS["travel"]


def test_no_history_unknown_scenario(tmp_path: Path):
    """未知场景使用 fallback 默认权重。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    learner = PreferenceLearner(mem)

    prefs = learner.compute_preferences("u1", "unknown_scenario")
    assert prefs.total_decisions == 0
    assert set(prefs.weights.keys()) == {"quality", "cost", "speed"}


def test_no_history_career_domain_returns_lifegoal_defaults(tmp_path: Path):
    """人生目标领域在无历史时应返回领域默认权重。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    learner = PreferenceLearner(mem)

    prefs = learner.compute_preferences("career-user", "career")
    assert prefs.total_decisions == 0
    assert prefs.confidence == 0.0
    assert prefs.weights == DEFAULT_WEIGHTS["career"]


def test_learns_from_choices(tmp_path: Path):
    """用户总选 opt-b (comfort 更好) 而非推荐的 opt-a (price 更好) -> comfort 权重增大。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    learner = PreferenceLearner(mem)

    default_comfort = DEFAULT_WEIGHTS["travel"]["comfort"]

    # 保存多条记录: 推荐 opt-a 但用户选 opt-b
    for i in range(10):
        rec = _make_record(
            decision_id=f"dec-{i:03d}",
            recommended_id="opt-a",
            chosen_id="opt-b",
            feedback=4.0,
        )
        mem.save(rec)

    prefs = learner.compute_preferences("u1", "travel")

    # comfort 权重应该高于默认值 (用户持续选comfort更高的选项)
    assert prefs.weights["comfort"] > default_comfort
    assert prefs.total_decisions == 10


def test_accepted_recommendations_stable(tmp_path: Path):
    """用户总接受推荐 -> 权重不应剧烈偏离默认值。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    learner = PreferenceLearner(mem)

    default_w = DEFAULT_WEIGHTS["travel"]

    for i in range(10):
        rec = _make_record(
            decision_id=f"dec-{i:03d}",
            recommended_id="opt-a",
            chosen_id="opt-a",  # 接受推荐
            feedback=4.5,
        )
        mem.save(rec)

    prefs = learner.compute_preferences("u1", "travel")

    # 权重应接近默认值 (允许混合后的轻微偏移)
    for dim in default_w:
        assert abs(prefs.weights[dim] - default_w[dim]) < 0.15, (
            f"{dim}: {prefs.weights[dim]} 偏离默认值 {default_w[dim]} 过多"
        )

    # 接受推荐率应为 100%
    assert prefs.accepted_recommendation_rate == 1.0


def test_confidence_increases_with_samples(tmp_path: Path):
    """决策数量越多, confidence 越高。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    learner = PreferenceLearner(mem)

    confidences = []
    for i in range(15):
        rec = _make_record(decision_id=f"dec-{i:03d}", feedback=4.0)
        mem.save(rec)
        prefs = learner.compute_preferences("u1", "travel")
        confidences.append(prefs.confidence)

    # confidence 应单调递增
    for j in range(1, len(confidences)):
        assert confidences[j] >= confidences[j - 1], (
            f"confidence 在第 {j} 条后下降: {confidences[j]} < {confidences[j-1]}"
        )

    # 最终 confidence 应明显高于初始值
    assert confidences[-1] > confidences[0]
    assert confidences[-1] > 0.5


def test_pattern_detection(tmp_path: Path):
    """用户总选 price 最优 -> 检测到偏好模式。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    learner = PreferenceLearner(mem)

    # opt-cheap: price最高; opt-comfy: comfort最高
    scores = [
        {"id": "opt-cheap", "scores": {"price": 1.0, "time": 0.4, "comfort": 0.3}},
        {"id": "opt-comfy", "scores": {"price": 0.3, "time": 0.5, "comfort": 1.0}},
    ]

    for i in range(10):
        rec = _make_record(
            decision_id=f"dec-{i:03d}",
            recommended_id="opt-comfy",
            chosen_id="opt-cheap",  # 总选最便宜的
            feedback=4.0,
            scores=scores,
        )
        mem.save(rec)

    prefs = learner.compute_preferences("u1", "travel")

    # 应检测到 price 偏好模式
    assert any("price" in p for p in prefs.common_patterns), (
        f"未检测到 price 偏好模式, patterns: {prefs.common_patterns}"
    )


def test_weights_sum_to_one(tmp_path: Path):
    """无论学习结果如何, 权重总和应为 1.0。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    learner = PreferenceLearner(mem)

    for i in range(5):
        rec = _make_record(
            decision_id=f"dec-{i:03d}",
            recommended_id="opt-a",
            chosen_id="opt-b",
            feedback=3.0,
        )
        mem.save(rec)

    prefs = learner.compute_preferences("u1", "travel")
    total = sum(prefs.weights.values())
    assert total == pytest.approx(1.0, abs=0.01), f"权重总和 {total} != 1.0"
