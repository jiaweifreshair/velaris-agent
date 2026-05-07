"""DecisionCostTracker 测试 — 成本追踪与 ROI 报告。"""

from __future__ import annotations

import pytest

from velaris_agent.velaris.cost_tracker import (
    CostRecord,
    DecisionCostTracker,
)


# ── 1. CostRecord 测试 ──────────────────────────────────────

class TestCostRecord:
    """CostRecord 数据类测试。"""

    def test_token_total(self):
        r = CostRecord(
            execution_id="exec-001",
            scenario="travel",
            model_tier="standard",
            token_input=500,
            token_output=300,
            latency_ms=1200.0,
            timestamp="2026-05-06T12:00:00+00:00",
        )
        assert r.token_total == 800

    def test_cost_estimate_standard(self):
        r = CostRecord(
            execution_id="exec-001",
            scenario="travel",
            model_tier="standard",
            token_input=1000,
            token_output=500,
            latency_ms=1000.0,
            timestamp="2026-05-06T12:00:00+00:00",
        )
        # standard: rate = 0.3, cost = 1500 * 0.3 / 1000 = 0.45
        assert r.cost_estimate == pytest.approx(0.45)

    def test_cost_estimate_premium(self):
        r = CostRecord(
            execution_id="exec-001",
            scenario="robotclaw",
            model_tier="premium",
            token_input=2000,
            token_output=1000,
            latency_ms=2000.0,
            timestamp="2026-05-06T12:00:00+00:00",
        )
        # premium: rate = 1.0, cost = 3000 * 1.0 / 1000 = 3.0
        assert r.cost_estimate == pytest.approx(3.0)

    def test_cost_estimate_economy(self):
        r = CostRecord(
            execution_id="exec-001",
            scenario="general",
            model_tier="economy",
            token_input=500,
            token_output=200,
            latency_ms=500.0,
            timestamp="2026-05-06T12:00:00+00:00",
        )
        # economy: rate = 0.05, cost = 700 * 0.05 / 1000 = 0.035
        assert r.cost_estimate == pytest.approx(0.035)

    def test_zero_tokens(self):
        r = CostRecord(
            execution_id="exec-001",
            scenario="general",
            model_tier="standard",
            token_input=0,
            token_output=0,
            latency_ms=0.0,
            timestamp="2026-05-06T12:00:00+00:00",
        )
        assert r.token_total == 0
        assert r.cost_estimate == 0.0


# ── 2. Track 基础功能 ──────────────────────────────────────

class TestTrack:
    """track() 记录成本。"""

    def test_track_returns_record(self):
        tracker = DecisionCostTracker()
        record = tracker.track(
            execution_id="exec-001",
            scenario="travel",
            token_input=500,
            token_output=300,
            model_tier="standard",
            latency_ms=1200.0,
        )
        assert isinstance(record, CostRecord)
        assert record.execution_id == "exec-001"
        assert record.scenario == "travel"
        assert record.token_input == 500
        assert record.token_output == 300
        assert record.model_tier == "standard"

    def test_track_negative_tokens_clamped(self):
        tracker = DecisionCostTracker()
        record = tracker.track(
            execution_id="exec-002",
            scenario="general",
            token_input=-100,
            token_output=-50,
        )
        assert record.token_input == 0
        assert record.token_output == 0

    def test_track_with_metadata(self):
        tracker = DecisionCostTracker()
        record = tracker.track(
            execution_id="exec-003",
            scenario="robotclaw",
            token_input=1000,
            token_output=500,
            metadata={"quality_score": 0.85},
        )
        assert record.metadata["quality_score"] == 0.85

    def test_track_auto_timestamp(self):
        tracker = DecisionCostTracker()
        record = tracker.track(
            execution_id="exec-004",
            scenario="general",
            token_input=100,
            token_output=50,
        )
        assert "2026" in record.timestamp  # 2026 年

    def test_multiple_tracks(self):
        tracker = DecisionCostTracker()
        for i in range(5):
            tracker.track(
                execution_id=f"exec-{i:03d}",
                scenario="travel",
                token_input=100 * (i + 1),
                token_output=50 * (i + 1),
            )
        assert tracker.record_count == 5


# ── 3. ROI 报告 ─────────────────────────────────────────────

class TestROI:
    """roi() 报告计算。"""

    def test_roi_empty(self):
        tracker = DecisionCostTracker()
        report = tracker.roi("travel")
        assert report.total_executions == 0
        assert report.total_token_input == 0
        assert report.cost_efficiency == 0.0

    def test_roi_single_scenario(self):
        tracker = DecisionCostTracker()
        tracker.track("exec-001", "travel", token_input=1000, token_output=500, model_tier="standard")
        tracker.track("exec-002", "travel", token_input=800, token_output=400, model_tier="standard")
        # 混入其他场景
        tracker.track("exec-003", "general", token_input=200, token_output=100, model_tier="economy")

        report = tracker.roi("travel")
        assert report.scenario == "travel"
        assert report.total_executions == 2
        assert report.total_token_input == 1800
        assert report.total_token_output == 900

    def test_roi_all_scenarios(self):
        tracker = DecisionCostTracker()
        tracker.track("exec-001", "travel", token_input=1000, token_output=500)
        tracker.track("exec-002", "general", token_input=200, token_output=100)

        report = tracker.roi()  # scenario=None
        assert report.scenario == "all"
        assert report.total_executions == 2

    def test_roi_with_quality_scores(self):
        tracker = DecisionCostTracker()
        tracker.track("exec-001", "travel", token_input=1000, token_output=500,
                      metadata={"quality_score": 0.9})
        tracker.track("exec-002", "travel", token_input=800, token_output=400,
                      metadata={"quality_score": 0.8})

        report = tracker.roi("travel")
        assert report.quality_score_avg == pytest.approx(0.85)

    def test_roi_cost_efficiency(self):
        tracker = DecisionCostTracker()
        tracker.track("exec-001", "travel", token_input=1000, token_output=500, model_tier="standard")
        # cost = 1500 * 0.3 / 1000 = 0.45, efficiency = 500 / 0.45 ≈ 1111.11
        report = tracker.roi("travel")
        assert report.cost_efficiency > 0

    def test_roi_to_dict(self):
        tracker = DecisionCostTracker()
        tracker.track("exec-001", "travel", token_input=1000, token_output=500)
        report = tracker.roi("travel")
        d = report.to_dict()
        assert "scenario" in d
        assert "total_executions" in d
        assert "cost_efficiency" in d


# ── 4. Budget 状态 ──────────────────────────────────────────

class TestBudgetStatus:
    """budget_status() 预算追踪。"""

    def test_no_budget(self):
        tracker = DecisionCostTracker()
        status = tracker.budget_status()
        assert status.total_budget == 0.0
        assert status.consumed == 0.0
        assert status.utilization == 0.0

    def test_with_budget(self):
        tracker = DecisionCostTracker(total_budget=10.0)
        tracker.track("exec-001", "travel", token_input=1000, token_output=500, model_tier="standard")
        status = tracker.budget_status()
        assert status.total_budget == 10.0
        assert status.consumed > 0
        assert status.remaining < 10.0
        assert 0.0 < status.utilization < 1.0

    def test_budget_depletion_projection(self):
        tracker = DecisionCostTracker(total_budget=100.0)
        # 添加多条记录以触发预测
        for i in range(5):
            tracker.track(f"exec-{i:03d}", "travel", token_input=1000, token_output=500, model_tier="standard")
        status = tracker.budget_status()
        # 5条记录足以触发预测
        if status.consumed < 100.0:
            assert status.projected_depletion_date is not None

    def test_budget_status_to_dict(self):
        tracker = DecisionCostTracker(total_budget=1000.0)
        status = tracker.budget_status()
        d = status.to_dict()
        assert "total_budget" in d
        assert "consumed" in d
        assert "remaining" in d
        assert "utilization" in d


# ── 5. 按场景聚合 ──────────────────────────────────────────

class TestCostByScenario:
    """cost_by_scenario() 按场景聚合。"""

    def test_empty_tracker(self):
        tracker = DecisionCostTracker()
        result = tracker.cost_by_scenario()
        assert result == {}

    def test_single_scenario(self):
        tracker = DecisionCostTracker()
        tracker.track("exec-001", "travel", token_input=1000, token_output=500)
        result = tracker.cost_by_scenario()
        assert "travel" in result
        assert result["travel"]["executions"] == 1
        assert result["travel"]["total_token_input"] == 1000

    def test_multiple_scenarios(self):
        tracker = DecisionCostTracker()
        tracker.track("exec-001", "travel", token_input=1000, token_output=500)
        tracker.track("exec-002", "general", token_input=200, token_output=100)
        tracker.track("exec-003", "travel", token_input=800, token_output=400)

        result = tracker.cost_by_scenario()
        assert "travel" in result
        assert "general" in result
        assert result["travel"]["executions"] == 2
        assert result["general"]["executions"] == 1
        assert result["travel"]["total_token_input"] == 1800

    def test_quality_score_in_aggregation(self):
        tracker = DecisionCostTracker()
        tracker.track("exec-001", "travel", token_input=1000, token_output=500,
                      metadata={"quality_score": 0.9})
        result = tracker.cost_by_scenario()
        assert result["travel"]["quality_score_avg"] == pytest.approx(0.9)


# ── 6. 查询接口 ────────────────────────────────────────────

class TestQuery:
    """get_records() 查询过滤。"""

    def test_filter_by_scenario(self):
        tracker = DecisionCostTracker()
        tracker.track("exec-001", "travel", token_input=1000, token_output=500)
        tracker.track("exec-002", "general", token_input=200, token_output=100)
        tracker.track("exec-003", "travel", token_input=800, token_output=400)

        records = tracker.get_records(scenario="travel")
        assert len(records) == 2
        assert all(r.scenario == "travel" for r in records)

    def test_filter_by_model_tier(self):
        tracker = DecisionCostTracker()
        tracker.track("exec-001", "travel", token_input=1000, token_output=500, model_tier="premium")
        tracker.track("exec-002", "general", token_input=200, token_output=100, model_tier="economy")

        records = tracker.get_records(model_tier="premium")
        assert len(records) == 1
        assert records[0].model_tier == "premium"

    def test_limit(self):
        tracker = DecisionCostTracker()
        for i in range(20):
            tracker.track(f"exec-{i:03d}", "travel", token_input=100, token_output=50)

        records = tracker.get_records(limit=5)
        assert len(records) == 5

    def test_total_consumed(self):
        tracker = DecisionCostTracker()
        tracker.track("exec-001", "travel", token_input=1000, token_output=500, model_tier="standard")
        assert tracker.total_consumed > 0

    def test_reset(self):
        tracker = DecisionCostTracker()
        tracker.track("exec-001", "travel", token_input=1000, token_output=500)
        assert tracker.record_count == 1
        tracker.reset()
        assert tracker.record_count == 0
        assert tracker.total_consumed == 0.0
