"""自进化评估引擎测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from velaris_agent.evolution.self_evolution import SelfEvolutionEngine
from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.memory.types import DecisionRecord


def _seed_record(
    memory: DecisionMemory,
    *,
    decision_id: str,
    chosen_id: str,
    feedback: float,
    created_at: datetime,
) -> None:
    """写入一条可用于漂移分析的决策样本。"""
    memory.save(
        DecisionRecord(
            decision_id=decision_id,
            user_id="u-evo",
            scenario="travel",
            query="出差方案选择",
            options_discovered=[{"id": "fast"}, {"id": "cheap"}],
            recommended={"id": "cheap", "label": "低成本"},
            user_choice={"id": chosen_id, "label": chosen_id},
            user_feedback=feedback,
            scores=[
                {"id": "cheap", "scores": {"price": 0.9, "comfort": 0.3}},
                {"id": "fast", "scores": {"price": 0.4, "comfort": 0.9}},
            ],
            weights_used={"price": 0.6, "comfort": 0.4},
            created_at=created_at,
        )
    )


def test_self_evolution_review_generates_actions(tmp_path: Path) -> None:
    """当用户持续不采纳推荐且满意度偏低时，应生成高优先级动作。"""
    memory = DecisionMemory(base_dir=tmp_path / "decisions")
    now = datetime.now(timezone.utc)
    _seed_record(memory, decision_id="dec-001", chosen_id="fast", feedback=3.0, created_at=now)
    _seed_record(
        memory,
        decision_id="dec-002",
        chosen_id="fast",
        feedback=2.8,
        created_at=now - timedelta(days=1),
    )
    _seed_record(
        memory,
        decision_id="dec-003",
        chosen_id="fast",
        feedback=3.1,
        created_at=now - timedelta(days=2),
    )

    engine = SelfEvolutionEngine(memory=memory, report_dir=tmp_path / "reports")
    report = engine.review(user_id="u-evo", scenario="travel", window=20, persist_report=True)

    assert report.sample_size == 3
    assert report.accepted_recommendation_rate == 0.0
    assert report.average_feedback is not None and report.average_feedback < 3.5
    assert report.report_path is not None
    assert Path(report.report_path).exists()
    assert any(action.priority == "high" for action in report.actions)


def test_self_evolution_review_handles_small_samples(tmp_path: Path) -> None:
    """样本过少时返回“先收集样本”的低优先级建议。"""
    memory = DecisionMemory(base_dir=tmp_path / "decisions")
    now = datetime.now(timezone.utc)
    _seed_record(memory, decision_id="dec-101", chosen_id="cheap", feedback=4.5, created_at=now)

    report = SelfEvolutionEngine(memory=memory).review(
        user_id="u-evo",
        scenario="travel",
        window=20,
        persist_report=False,
    )
    assert report.sample_size == 1
    assert report.actions
    assert report.actions[0].action_id == "collect_more_samples"
