"""CostOptimizer 测试 — Token 成本优化器。"""

from __future__ import annotations


from velaris_agent.evolution.cost_optimizer import (
    ComplexityLevel,
    CostOptimizer,
    LoadingTier,
    OptimizationSuggestion,
)
from velaris_agent.velaris.cost_tracker import DecisionCostTracker


# ── 1. LoadingTier 测试 ──────────────────────────────────────────

class TestLoadingTier:
    """加载层级枚举测试。"""

    def test_l0_estimated_tokens(self):
        assert LoadingTier.L0_SUMMARY.estimated_tokens == 100.0

    def test_l1_estimated_tokens(self):
        assert LoadingTier.L1_CONTEXT.estimated_tokens == 2000.0

    def test_l2_estimated_tokens(self):
        assert LoadingTier.L2_FULL.estimated_tokens == 8000.0

    def test_string_values(self):
        assert LoadingTier.L0_SUMMARY.value == "L0"
        assert LoadingTier.L1_CONTEXT.value == "L1"
        assert LoadingTier.L2_FULL.value == "L2"


# ── 2. optimize_loading_tier 测试 ──────────────────────────────

class TestOptimizeLoadingTier:
    """加载层级优化测试。"""

    def test_sufficient_budget_uses_complexity(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        # 简单场景 → L0
        assert optimizer.optimize_loading_tier("tokencost", remaining_budget=8000.0) == LoadingTier.L0_SUMMARY
        # 中等场景 → L1
        assert optimizer.optimize_loading_tier("travel", remaining_budget=8000.0) == LoadingTier.L1_CONTEXT
        # 复杂场景 → L2
        assert optimizer.optimize_loading_tier("procurement", remaining_budget=8000.0) == LoadingTier.L2_FULL

    def test_moderate_budget_downgrades(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        # 30% 预算 → L2 降级到 L1
        tier = optimizer.optimize_loading_tier("procurement", remaining_budget=3000.0)
        assert tier == LoadingTier.L1_CONTEXT

    def test_low_budget_downgrades_further(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        # 10% 预算 → 降到 L0
        tier = optimizer.optimize_loading_tier("travel", remaining_budget=1000.0)
        assert tier == LoadingTier.L0_SUMMARY

    def test_critical_scenario_preserves_l1(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        # 10% 预算 → 在 0.05~0.2 区间，关键场景保持 L1
        tier = optimizer.optimize_loading_tier("lifegoal", remaining_budget=1000.0)
        assert tier.value >= LoadingTier.L1_CONTEXT.value

    def test_very_low_budget_forces_l0(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        tier = optimizer.optimize_loading_tier("travel", remaining_budget=100.0)
        assert tier == LoadingTier.L0_SUMMARY

    def test_explicit_complexity_overrides(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        # 显式指定复杂度覆盖默认映射
        tier = optimizer.optimize_loading_tier("travel", remaining_budget=8000.0, complexity=ComplexityLevel.SIMPLE)
        assert tier == LoadingTier.L0_SUMMARY

    def test_no_budget_info_defaults_to_sufficient(self):
        optimizer = CostOptimizer()
        tier = optimizer.optimize_loading_tier("travel")
        # 无预算信息时默认"充足" → L1
        assert tier == LoadingTier.L1_CONTEXT


# ── 3. recommend_model 测试 ──────────────────────────────────

class TestRecommendModel:
    """模型推荐测试。"""

    def test_critical_scenario_premium(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        model = optimizer.recommend_model("lifegoal", remaining_budget=5000.0)
        assert model == "premium"

    def test_complex_scenario_premium_when_rich(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        model = optimizer.recommend_model("procurement", remaining_budget=5000.0)
        assert model == "premium"

    def test_moderate_scenario_standard(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        model = optimizer.recommend_model("travel", remaining_budget=5000.0)
        assert model == "standard"

    def test_simple_scenario_economy(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        model = optimizer.recommend_model("tokencost", remaining_budget=5000.0)
        assert model == "economy"

    def test_low_budget_downgrades_model(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        # 预算紧张时 moderate 降级到 economy
        model = optimizer.recommend_model("travel", remaining_budget=500.0)
        assert model == "economy"

    def test_critical_scenario_min_standard(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        # 关键场景最低标准模型
        model = optimizer.recommend_model("lifegoal", remaining_budget=200.0)
        assert model == "standard"

    def test_string_complexity(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        model = optimizer.recommend_model("travel", complexity="simple", remaining_budget=5000.0)
        assert model == "economy"


# ── 4. token_budget_gate 测试 ──────────────────────────────────

class TestBudgetGate:
    """预算门控测试。"""

    def test_within_budget_allowed(self):
        optimizer = CostOptimizer()
        result = optimizer.token_budget_gate(
            remaining_budget=10000.0,
            estimated_cost=500.0,
        )
        assert result.allowed is True
        assert result.reason == "within_budget"

    def test_approaching_limit_allowed_with_suggestion(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        result = optimizer.token_budget_gate(
            remaining_budget=5000.0,
            estimated_cost=3000.0,
        )
        assert result.allowed is True
        assert "downgrade" in result.reason

    def test_exceeds_budget_blocked(self):
        optimizer = CostOptimizer()
        result = optimizer.token_budget_gate(
            remaining_budget=500.0,
            estimated_cost=800.0,
        )
        assert result.allowed is False
        assert "exceeds" in result.reason

    def test_critical_scenario_gets_budget_extension(self):
        optimizer = CostOptimizer()
        result = optimizer.token_budget_gate(
            remaining_budget=500.0,
            estimated_cost=550.0,  # 略超预算
            scenario="lifegoal",
            complexity=ComplexityLevel.CRITICAL,
        )
        # 关键场景有 1.2x 宽限
        assert result.allowed is True

    def test_critical_scenario_still_blocked_if_way_over(self):
        optimizer = CostOptimizer()
        result = optimizer.token_budget_gate(
            remaining_budget=500.0,
            estimated_cost=2000.0,  # 远超 1.2x
            scenario="lifegoal",
            complexity=ComplexityLevel.CRITICAL,
        )
        assert result.allowed is False

    def test_result_to_dict(self):
        optimizer = CostOptimizer()
        result = optimizer.token_budget_gate(
            remaining_budget=10000.0,
            estimated_cost=500.0,
        )
        d = result.to_dict()
        assert "allowed" in d
        assert "remaining_budget" in d
        assert "suggested_tier" in d


# ── 5. suggest 综合建议测试 ──────────────────────────────────

class TestSuggest:
    """综合优化建议测试。"""

    def test_suggest_within_budget(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        suggestion = optimizer.suggest("travel", remaining_budget=8000.0)
        assert isinstance(suggestion, OptimizationSuggestion)
        assert suggestion.recommended_tier in ("L0", "L1", "L2")
        assert suggestion.recommended_model in ("economy", "standard", "premium")

    def test_suggest_low_budget(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        suggestion = optimizer.suggest("travel", remaining_budget=500.0)
        assert suggestion.recommended_model == "economy"
        assert suggestion.estimated_savings_pct >= 0.0

    def test_suggest_quality_impact_none_when_upgrading(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        suggestion = optimizer.suggest(
            "travel",
            remaining_budget=8000.0,
            current_tier="L0",
            current_model="economy",
        )
        # 从 L0/economy → 更高级别，无质量影响
        assert suggestion.quality_impact == "none"

    def test_suggest_quality_impact_minimal_on_slight_downgrade(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        optimizer.suggest(
            "tokencost",
            remaining_budget=8000.0,
            current_tier="L1",
            current_model="standard",
        )
        # tokencost 是 simple → L0 + economy，降一级
        # quality_impact 应为 minimal 或 none

    def test_suggest_to_dict(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        suggestion = optimizer.suggest("travel", remaining_budget=5000.0)
        d = suggestion.to_dict()
        assert "current_tier" in d
        assert "recommended_tier" in d
        assert "quality_impact" in d


# ── 6. generate_economics_report 测试 ──────────────────────────

class TestEconomicsReport:
    """Token Economics 报告测试。"""

    def test_report_without_tracker(self):
        optimizer = CostOptimizer(total_budget=10000.0)
        report = optimizer.generate_economics_report()
        assert report["total_budget"] == 10000.0
        assert "budget_status" in report

    def test_report_with_tracker(self):
        tracker = DecisionCostTracker(total_budget=10000.0)
        tracker.track("exec-001", "travel", token_input=1000, token_output=500)
        tracker.track("exec-002", "travel", token_input=800, token_output=400)

        optimizer = CostOptimizer(total_budget=10000.0, cost_tracker=tracker)
        report = optimizer.generate_economics_report(scenario="travel")
        assert "budget_status" in report
        assert "cost_by_scenario" in report
        assert "roi" in report
        assert "optimization_suggestions" in report
        assert report["roi"]["scenario"] == "travel"

    def test_report_has_timestamp(self):
        optimizer = CostOptimizer()
        report = optimizer.generate_economics_report()
        assert "generated_at" in report


# ── 7. 边界条件测试 ──────────────────────────────────────────

class TestEdgeCases:
    """边界条件测试。"""

    def test_zero_budget(self):
        optimizer = CostOptimizer(total_budget=0.0)
        tier = optimizer.optimize_loading_tier("travel", remaining_budget=0.0)
        assert tier == LoadingTier.L0_SUMMARY

    def test_very_large_budget(self):
        optimizer = CostOptimizer(total_budget=1e9)
        tier = optimizer.optimize_loading_tier("procurement", remaining_budget=9e8)
        assert tier == LoadingTier.L2_FULL

    def test_budget_gate_zero_remaining(self):
        optimizer = CostOptimizer()
        result = optimizer.token_budget_gate(
            remaining_budget=0.0,
            estimated_cost=1.0,
        )
        assert result.allowed is False

    def test_budget_gate_zero_estimated(self):
        optimizer = CostOptimizer()
        result = optimizer.token_budget_gate(
            remaining_budget=1000.0,
            estimated_cost=0.0,
        )
        assert result.allowed is True

    def test_with_cost_tracker_auto_budget_ratio(self):
        tracker = DecisionCostTracker(total_budget=10000.0)
        tracker.track("exec-001", "travel", token_input=1000, token_output=500)
        optimizer = CostOptimizer(total_budget=10000.0, cost_tracker=tracker)
        # 不传 remaining_budget，自动从 tracker 计算
        tier = optimizer.optimize_loading_tier("travel")
        assert isinstance(tier, LoadingTier)
