"""决策记忆存储与检索测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.memory.types import DecisionRecord


def _make_record(
    decision_id: str = "dec-test001",
    user_id: str = "u1",
    scenario: str = "travel",
    query: str = "北京到上海机票",
    recommended: dict | None = None,
    user_choice: dict | None = None,
    user_feedback: float | None = None,
    options_discovered: list | None = None,
    scores: list | None = None,
) -> DecisionRecord:
    """构造测试用 DecisionRecord。"""
    return DecisionRecord(
        decision_id=decision_id,
        user_id=user_id,
        scenario=scenario,
        query=query,
        intent={"origin": "北京", "destination": "上海"},
        options_discovered=options_discovered or [],
        options_after_filter=[],
        scores=scores or [],
        weights_used={"price": 0.4, "time": 0.35, "comfort": 0.25},
        tools_called=["search_flights"],
        recommended=recommended or {"id": "opt-a", "label": "航班A"},
        alternatives=[{"id": "opt-b", "label": "航班B"}],
        explanation="航班A性价比最高",
        user_choice=user_choice,
        user_feedback=user_feedback,
        created_at=datetime.now(timezone.utc),
    )


def test_save_and_get(tmp_path: Path):
    """保存 DecisionRecord 后能按 ID 取回, 字段完整。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    record = _make_record()
    saved_id = mem.save(record)

    assert saved_id == "dec-test001"

    got = mem.get(saved_id)
    assert got is not None
    assert got.decision_id == record.decision_id
    assert got.user_id == record.user_id
    assert got.scenario == record.scenario
    assert got.query == record.query
    assert got.recommended == record.recommended
    assert got.explanation == "航班A性价比最高"
    assert got.weights_used == {"price": 0.4, "time": 0.35, "comfort": 0.25}


def test_get_nonexistent(tmp_path: Path):
    """获取不存在的记录返回 None。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    assert mem.get("dec-nonexistent") is None


def test_list_by_user(tmp_path: Path):
    """按用户过滤历史决策, 支持场景筛选。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")

    # 用户 A: 2条 travel, 1条 tokencost
    mem.save(_make_record(decision_id="dec-a1", user_id="uA", scenario="travel", query="北京飞上海"))
    mem.save(_make_record(decision_id="dec-a2", user_id="uA", scenario="travel", query="广州飞深圳"))
    mem.save(_make_record(decision_id="dec-a3", user_id="uA", scenario="tokencost", query="选模型"))

    # 用户 B: 1条 travel
    mem.save(_make_record(decision_id="dec-b1", user_id="uB", scenario="travel", query="成都飞重庆"))

    # 不指定场景: 用户A全部3条
    all_a = mem.list_by_user("uA")
    assert len(all_a) == 3

    # 指定场景: 用户A travel 2条
    travel_a = mem.list_by_user("uA", scenario="travel")
    assert len(travel_a) == 2

    # 用户B: 1条
    all_b = mem.list_by_user("uB")
    assert len(all_b) == 1


def test_count_by_user(tmp_path: Path):
    """按用户统计应支持场景过滤。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    mem.save(_make_record(decision_id="dec-c1", user_id="uA", scenario="travel"))
    mem.save(_make_record(decision_id="dec-c2", user_id="uA", scenario="travel"))
    mem.save(_make_record(decision_id="dec-c3", user_id="uA", scenario="tokencost"))
    mem.save(_make_record(decision_id="dec-c4", user_id="uB", scenario="travel"))

    assert mem.count_by_user("uA") == 3
    assert mem.count_by_user("uA", scenario="travel") == 2
    assert mem.count_by_user("uB", scenario="travel") == 1


def test_save_same_decision_id_replaces_index_entry(tmp_path: Path):
    """重复保存同一决策应覆盖旧索引, 且最近优先顺序应以最后一次保存为准。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")

    mem.save(
        _make_record(
            decision_id="dec-old",
            user_id="uA",
            scenario="travel",
            query="第一次保存",
        )
    )
    mem.save(
        _make_record(
            decision_id="dec-new",
            user_id="uA",
            scenario="travel",
            query="第二条记录",
        )
    )
    mem.save(
        _make_record(
            decision_id="dec-old",
            user_id="uA",
            scenario="travel",
            query="第一次保存-更新后",
        )
    )

    results = mem.list_by_user("uA", scenario="travel")
    assert [item.decision_id for item in results] == ["dec-old", "dec-new"]
    assert mem.count_by_user("uA", scenario="travel") == 2
    assert mem.get("dec-old").query == "第一次保存-更新后"


def test_recall_similar(tmp_path: Path):
    """关键词匹配召回相似决策 (按空格分词)。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")

    # recall_similar 使用空格分词, 所以用英文/空格分隔的查询
    mem.save(_make_record(decision_id="dec-1", user_id="u1", scenario="travel", query="beijing shanghai flight cheap"))
    mem.save(_make_record(decision_id="dec-2", user_id="u1", scenario="travel", query="beijing guangzhou flight fast"))
    mem.save(_make_record(decision_id="dec-3", user_id="u1", scenario="travel", query="chengdu chongqing train"))

    # 查询包含 "beijing" 和 "flight" - 应匹配 dec-1 和 dec-2
    results = mem.recall_similar("u1", "travel", "beijing shenzhen flight")
    assert len(results) >= 2
    result_ids = {r.decision_id for r in results}
    assert "dec-1" in result_ids
    assert "dec-2" in result_ids


def test_recall_similar_handles_chinese_punctuation(tmp_path: Path):
    """中文查询即使没有空格分词，也应能通过标点清洗召回相似历史。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    mem.save(
        _make_record(
            decision_id="dec-cn-1",
            user_id="u1",
            scenario="career",
            query="两个 offer 怎么选，短期薪资和长期成长怎么平衡？",
        )
    )

    results = mem.recall_similar(
        "u1",
        "career",
        "现在有两个 offer，一个钱多一个成长更好，我该怎么选？",
    )

    assert len(results) == 1
    assert results[0].decision_id == "dec-cn-1"


def test_recall_similar_other_user_excluded(tmp_path: Path):
    """召回不返回其他用户的决策。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    mem.save(_make_record(decision_id="dec-1", user_id="u1", query="北京机票"))
    mem.save(_make_record(decision_id="dec-2", user_id="u2", query="北京机票"))

    results = mem.recall_similar("u1", "travel", "北京机票")
    assert len(results) == 1
    assert results[0].decision_id == "dec-1"


def test_update_feedback(tmp_path: Path):
    """保存记录后回填用户选择和满意度, 验证持久化。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    mem.save(_make_record(decision_id="dec-fb1"))

    updated = mem.update_feedback(
        "dec-fb1",
        user_choice={"id": "opt-b", "label": "航班B"},
        user_feedback=4.5,
        outcome_notes="用户对航班B满意",
    )
    assert updated is not None
    assert updated.user_choice == {"id": "opt-b", "label": "航班B"}
    assert updated.user_feedback == 4.5
    assert updated.outcome_notes == "用户对航班B满意"

    # 重新读取验证持久化
    reloaded = mem.get("dec-fb1")
    assert reloaded is not None
    assert reloaded.user_feedback == 4.5
    assert reloaded.user_choice == {"id": "opt-b", "label": "航班B"}


def test_update_feedback_nonexistent(tmp_path: Path):
    """回填不存在的记录返回 None。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    assert mem.update_feedback("dec-ghost", user_feedback=3.0) is None


def test_aggregate_outcomes(tmp_path: Path):
    """聚合某选项的历史满意度统计。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")

    # 3条记录都包含 opt-hotel-1, 其中2条用户选了它并给了反馈
    for i in range(3):
        rec = _make_record(
            decision_id=f"dec-agg{i}",
            user_id=f"u{i}",
            scenario="travel",
            options_discovered=[
                {"id": "opt-hotel-1", "label": "酒店A"},
                {"id": "opt-hotel-2", "label": "酒店B"},
            ],
            user_choice={"id": "opt-hotel-1"} if i < 2 else {"id": "opt-hotel-2"},
            user_feedback=4.0 if i < 2 else 3.0,
        )
        mem.save(rec)

    agg = mem.aggregate_outcomes("travel", option_field="id", option_value="opt-hotel-1")
    assert agg["times_seen"] == 3
    assert agg["times_chosen"] == 2
    assert agg["avg_satisfaction"] == 4.0
    assert agg["sample_size"] == 2
    assert agg["choice_rate"] == pytest.approx(2 / 3, abs=0.01)


def test_empty_memory(tmp_path: Path):
    """空记忆库检索返回空列表。"""
    mem = DecisionMemory(base_dir=tmp_path / "decisions")

    assert mem.list_by_user("nobody") == []
    assert mem.recall_similar("nobody", "travel", "随便搜搜") == []
    agg = mem.aggregate_outcomes("travel", option_value="nothing")
    assert agg["times_seen"] == 0
    assert agg["avg_satisfaction"] is None


def test_generate_id():
    """生成的 ID 格式正确且唯一。"""
    id1 = DecisionMemory.generate_id()
    id2 = DecisionMemory.generate_id()
    assert id1.startswith("dec-")
    assert len(id1) == 16  # "dec-" + 12 hex chars
    assert id1 != id2
