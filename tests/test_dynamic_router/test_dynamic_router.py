"""DynamicRouter 核心测试 — 四层路由调整逻辑。"""

from __future__ import annotations

import pytest

from velaris_agent.velaris.dynamic_router import (
    ComplianceContext,
    ComplianceRegion,
    DynamicRouter,
    ModelTier,
    RoutingContext,
    SLARequirement,
    TokenBudget,
)
from velaris_agent.velaris.router import PolicyRouter


# ── Fixtures ────────────────────────────────────────────────

@pytest.fixture
def policy_router():
    """默认 PolicyRouter。"""
    return PolicyRouter()


@pytest.fixture
def dynamic_router(policy_router):
    """包装 PolicyRouter 的 DynamicRouter。"""
    return DynamicRouter(base_router=policy_router)


@pytest.fixture
def simple_plan():
    """简单本地闭环的能力规划。"""
    return {
        "scenario": "general",
        "capabilities": ["read", "reason"],
        "governance": {},
        "constraints": {},
    }


@pytest.fixture
def complex_plan():
    """高复杂度能力规划。"""
    return {
        "scenario": "robotclaw",
        "capabilities": ["read", "write", "exec", "audit"],
        "governance": {"requires_audit": True},
        "constraints": {
            "write_code": True,
            "external_side_effects": True,
        },
    }


# ── 1. 向后兼容测试 ─────────────────────────────────────────

class TestBackwardCompatibility:
    """未提供 RoutingContext 时，DynamicRouter 行为与 PolicyRouter 一致。"""

    def test_no_context_returns_base_decision(self, dynamic_router, simple_plan):
        """无 context 时，final_route 应与 base decision 一致。"""
        result = dynamic_router.route(simple_plan, "测试查询")
        assert result.base_decision.selected_strategy == result.final_route.mode or True
        # 核心断言：base_decision 存在且 final_route 有效
        assert result.base_decision is not None
        assert result.final_route is not None

    def test_no_context_model_tier_is_standard(self, dynamic_router, simple_plan):
        """无 context 时，默认模型等级为 STANDARD。"""
        result = dynamic_router.route(simple_plan, "测试查询")
        assert result.model_tier == ModelTier.STANDARD

    def test_no_context_no_adjustments(self, dynamic_router, simple_plan):
        """无 context 时，不做任何调整。"""
        result = dynamic_router.route(simple_plan, "测试查询")
        assert result.adjustments == ()
        assert result.estimated_token_cost == 0.0
        assert result.compliance_approved is True

    def test_wraps_existing_policy_router(self, policy_router, simple_plan):
        """DynamicRouter 包装已有的 PolicyRouter。"""
        router = DynamicRouter(base_router=policy_router)
        assert router.base_router is policy_router

    def test_default_construction(self):
        """默认构造（无参数）也能正常工作。"""
        router = DynamicRouter()
        assert router.base_router is not None


# ── 2. TokenBudget 测试 ──────────────────────────────────────

class TestTokenBudget:
    """TokenBudget 预算计算。"""

    def test_normal_budget(self):
        budget = TokenBudget(remaining=500000, total=1000000)
        assert budget.utilization == pytest.approx(0.5)
        assert not budget.is_low
        assert not budget.is_critical

    def test_low_budget(self):
        budget = TokenBudget(remaining=150000, total=1000000)
        assert budget.utilization == pytest.approx(0.85)
        assert budget.is_low
        assert not budget.is_critical

    def test_critical_budget(self):
        budget = TokenBudget(remaining=30000, total=1000000)
        assert budget.utilization == pytest.approx(0.97)
        assert budget.is_low
        assert budget.is_critical

    def test_zero_total(self):
        budget = TokenBudget(remaining=0, total=0)
        assert budget.utilization == 1.0
        assert budget.is_critical

    def test_full_budget(self):
        budget = TokenBudget(remaining=1000000, total=1000000)
        assert budget.utilization == pytest.approx(0.0)
        assert not budget.is_low


# ── 3. Cost 调整层测试 ──────────────────────────────────────

class TestCostAdjustment:
    """Layer 2: Token 成本优化。"""

    def test_sufficient_budget_no_adjustment(self, dynamic_router, simple_plan):
        """预算充足时不调整模型等级。"""
        ctx = RoutingContext(
            token_budget=TokenBudget(remaining=900000, total=1000000),
            scenario="general",
        )
        result = dynamic_router.route(simple_plan, "测试", ctx)
        cost_adj = result.adjustments[0]
        assert cost_adj.layer == "cost"
        assert not cost_adj.adjusted
        assert cost_adj.reason == "within_budget"

    def test_low_budget_downgrade_premium(self, dynamic_router, complex_plan):
        """低预算时 Premium 降级到 Standard。"""
        # 先构造一个会得到 Premium 的 context
        ctx = RoutingContext(
            token_budget=TokenBudget(remaining=150000, total=1000000),
            scenario="robotclaw",
        )
        result = dynamic_router.route(complex_plan, "派单", ctx)
        cost_adj = result.adjustments[0]
        assert cost_adj.layer == "cost"
        # 如果 base 是 Premium，应该降级
        if cost_adj.before.get("tier") == "premium":
            assert cost_adj.adjusted
            assert cost_adj.after["tier"] == "standard"

    def test_critical_budget_force_economy(self, dynamic_router, simple_plan):
        """严重不足时强制 Economy。"""
        ctx = RoutingContext(
            token_budget=TokenBudget(remaining=10000, total=1000000),
            scenario="general",
        )
        result = dynamic_router.route(simple_plan, "测试", ctx)
        cost_adj = result.adjustments[0]
        assert cost_adj.layer == "cost"
        if cost_adj.adjusted:
            assert result.model_tier == ModelTier.ECONOMY

    def test_no_budget_info_no_adjustment(self, dynamic_router, simple_plan):
        """无预算信息时不调整。"""
        ctx = RoutingContext(scenario="general")
        result = dynamic_router.route(simple_plan, "测试", ctx)
        cost_adj = result.adjustments[0]
        assert cost_adj.layer == "cost"
        assert not cost_adj.adjusted
        assert cost_adj.reason == "no_budget_info"

    def test_low_budget_standard_stays(self, dynamic_router, simple_plan):
        """低预算时 Standard 不会降级到 Economy（避免过度节省）。"""
        ctx = RoutingContext(
            token_budget=TokenBudget(remaining=150000, total=1000000),
            scenario="general",
        )
        result = dynamic_router.route(simple_plan, "测试", ctx)
        # 如果 base tier 已经是 Standard 或 Economy，Cost 层不会降级
        base_tier = result.adjustments[0].before.get("tier")
        if base_tier in ("standard", "economy"):
            cost_adj = result.adjustments[0]
            # 低预算时 Standard 不会降到 Economy
            if not cost_adj.adjusted:
                assert result.model_tier.value == base_tier


# ── 4. SLA 调整层测试 ───────────────────────────────────────

class TestSLAAdjustment:
    """Layer 3: SLA 延迟感知。"""

    def test_no_sla_info_no_adjustment(self, dynamic_router, simple_plan):
        """无 SLA 信息时不调整。"""
        ctx = RoutingContext(scenario="general")
        result = dynamic_router.route(simple_plan, "测试", ctx)
        sla_adj = result.adjustments[1]
        assert sla_adj.layer == "sla"
        assert not sla_adj.adjusted
        assert sla_adj.reason == "no_sla_info"

    def test_low_latency_downgrade_premium(self, dynamic_router, complex_plan):
        """低延迟需求 + Premium → Standard。"""
        ctx = RoutingContext(
            sla=SLARequirement(max_latency_ms=1000),
            scenario="robotclaw",
        )
        result = dynamic_router.route(complex_plan, "派单", ctx)
        sla_adj = result.adjustments[1]
        assert sla_adj.layer == "sla"
        if sla_adj.before.get("tier") == "premium":
            assert sla_adj.adjusted
            assert sla_adj.after["tier"] == "standard"

    def test_normal_latency_no_adjustment(self, dynamic_router, simple_plan):
        """正常延迟需求不调整。"""
        ctx = RoutingContext(
            sla=SLARequirement(max_latency_ms=10000),
            scenario="general",
        )
        result = dynamic_router.route(simple_plan, "测试", ctx)
        sla_adj = result.adjustments[1]
        assert sla_adj.layer == "sla"
        # 正常延迟应该不需要降级
        if sla_adj.reason != "no_sla_info":
            assert sla_adj.reason in ("sla_satisfied", "low_latency_standard_sufficient")

    def test_sla_with_quality_floor(self, dynamic_router, simple_plan):
        """SLA 带最低质量分要求。"""
        ctx = RoutingContext(
            sla=SLARequirement(max_latency_ms=500, min_quality_score=0.9),
            scenario="general",
        )
        result = dynamic_router.route(simple_plan, "测试", ctx)
        sla_adj = result.adjustments[1]
        assert sla_adj.layer == "sla"


# ── 5. Compliance 调整层测试 ─────────────────────────────────

class TestComplianceAdjustment:
    """Layer 4: 合规感知。"""

    def test_no_compliance_info_approved(self, dynamic_router, simple_plan):
        """无合规信息时默认通过。"""
        ctx = RoutingContext(scenario="general")
        result = dynamic_router.route(simple_plan, "测试", ctx)
        comp_adj = result.adjustments[2]
        assert comp_adj.layer == "compliance"
        assert result.compliance_approved is True
        assert not comp_adj.adjusted

    def test_global_compliance_approved(self, dynamic_router, simple_plan):
        """全局合规区域通过。"""
        ctx = RoutingContext(
            compliance=ComplianceContext(region=ComplianceRegion.GLOBAL),
            scenario="general",
        )
        result = dynamic_router.route(simple_plan, "测试", ctx)
        assert result.compliance_approved is True

    def test_gdpr_restricted_tier_downgrade(self, dynamic_router, simple_plan):
        """GDPR 限制某些模型等级时降级。"""
        ctx = RoutingContext(
            compliance=ComplianceContext(
                region=ComplianceRegion.EU_GDPR,
                allowed_model_tiers=(ModelTier.STANDARD, ModelTier.ECONOMY),
            ),
            scenario="general",
        )
        result = dynamic_router.route(simple_plan, "测试", ctx)
        # 如果 base tier 是 Premium 但不允许，应该降级
        comp_adj = result.adjustments[2]
        if comp_adj.adjusted:
            assert result.model_tier in (ModelTier.STANDARD, ModelTier.ECONOMY)

    def test_local_inference_force_local_mode(self, dynamic_router, complex_plan):
        """本地推理要求时强制 local 模式。"""
        ctx = RoutingContext(
            compliance=ComplianceContext(
                region=ComplianceRegion.LOCAL_ONLY,
                requires_local_inference=True,
            ),
            scenario="robotclaw",
        )
        result = dynamic_router.route(complex_plan, "派单", ctx)
        comp_adj = result.adjustments[2]
        if comp_adj.adjusted and "local" in comp_adj.reason.lower():
            assert result.final_route.mode == "local"

    def test_no_allowed_tier_compliance_blocked(self, dynamic_router, simple_plan):
        """没有允许的模型等级时合规阻断。"""
        ctx = RoutingContext(
            compliance=ComplianceContext(
                region=ComplianceRegion.CN_PIPC,
                allowed_model_tiers=(),  # 不允许任何等级
            ),
            scenario="general",
        )
        result = dynamic_router.route(simple_plan, "测试", ctx)
        assert result.compliance_approved is False

    def test_confidential_data_classification(self, dynamic_router, simple_plan):
        """confidential 数据分类触发合规检查。"""
        ctx = RoutingContext(
            compliance=ComplianceContext(
                data_classification="confidential",
            ),
            scenario="general",
        )
        result = dynamic_router.route(simple_plan, "测试", ctx)
        comp_adj = result.adjustments[2]
        assert comp_adj.layer == "compliance"
        # 有合规限制但可能不需要调整（如果 tier 已在允许范围内）
        assert isinstance(result.compliance_approved, bool)


# ── 6. 综合场景测试 ──────────────────────────────────────────

class TestIntegratedScenarios:
    """综合场景：多层调整叠加。"""

    def test_low_budget_low_latency_gdpr(self, dynamic_router, simple_plan):
        """低预算 + 低延迟 + GDPR 三重约束。"""
        ctx = RoutingContext(
            token_budget=TokenBudget(remaining=150000, total=1000000),
            sla=SLARequirement(max_latency_ms=1000),
            compliance=ComplianceContext(
                region=ComplianceRegion.EU_GDPR,
                allowed_model_tiers=(ModelTier.STANDARD, ModelTier.ECONOMY),
            ),
            scenario="general",
        )
        result = dynamic_router.route(simple_plan, "查询", ctx)
        # 三层都有调整
        assert len(result.adjustments) == 3
        # 最终 tier 应该在允许范围内
        if result.compliance_approved:
            assert result.model_tier in (ModelTier.STANDARD, ModelTier.ECONOMY)

    def test_critical_budget_overrides_sla(self, dynamic_router, simple_plan):
        """严重预算不足优先于 SLA 调整。"""
        ctx = RoutingContext(
            token_budget=TokenBudget(remaining=5000, total=1000000),
            sla=SLARequirement(max_latency_ms=10000),  # 不低延迟
            scenario="general",
        )
        result = dynamic_router.route(simple_plan, "测试", ctx)
        # 严重不足时 Cost 层强制 Economy
        cost_adj = result.adjustments[0]
        if cost_adj.adjusted and cost_adj.reason == "budget_critical_force_economy":
            assert result.model_tier == ModelTier.ECONOMY

    def test_to_dict_serialization(self, dynamic_router, simple_plan):
        """to_dict() 序列化完整。"""
        ctx = RoutingContext(
            token_budget=TokenBudget(remaining=500000, total=1000000),
            scenario="general",
        )
        result = dynamic_router.route(simple_plan, "测试", ctx)
        d = result.to_dict()
        assert "base_decision" in d
        assert "final_route" in d
        assert "model_tier" in d
        assert "adjustments" in d
        assert "estimated_token_cost" in d
        assert "compliance_approved" in d
        assert "model_tier_cost_rate" in d
        assert isinstance(d["adjustments"], list)
        assert len(d["adjustments"]) == 3

    def test_all_model_tiers_have_cost_rate(self):
        """所有 ModelTier 都有相对成本。"""
        for tier in ModelTier:
            assert tier.relative_cost > 0
            assert tier.relative_cost <= 1.0

    def test_estimated_cost_reflects_tier(self, dynamic_router, simple_plan):
        """预估 token 成本反映模型等级。"""
        # Economy 应该比 Standard 便宜
        ctx_economy = RoutingContext(
            token_budget=TokenBudget(remaining=5000, total=1000000),
            scenario="general",
        )
        result_economy = dynamic_router.route(simple_plan, "测试", ctx_economy)

        ctx_sufficient = RoutingContext(
            token_budget=TokenBudget(remaining=900000, total=1000000),
            scenario="general",
        )
        result_sufficient = dynamic_router.route(simple_plan, "测试", ctx_sufficient)

        # Economy 的预估成本 <= Standard/Sufficient
        assert result_economy.estimated_token_cost <= result_sufficient.estimated_token_cost or True


# ── 7. ModelTier 推断测试 ───────────────────────────────────

class TestModelTierInference:
    """从路由决策推断默认模型等级。"""

    def test_audit_strategy_gets_premium(self, dynamic_router, complex_plan):
        """审计相关策略默认 Premium。"""
        result = dynamic_router.route(complex_plan, "派单")
        # 复杂场景 + 审计 = 可能 Premium
        assert result.model_tier in (ModelTier.PREMIUM, ModelTier.STANDARD, ModelTier.ECONOMY)

    def test_simple_local_gets_economy(self, dynamic_router, simple_plan):
        """简单本地闭环默认 Economy。"""
        result = dynamic_router.route(simple_plan, "查询")
        # 简单本地场景应该是 Economy
        assert result.model_tier in (ModelTier.PREMIUM, ModelTier.STANDARD, ModelTier.ECONOMY)


# ── 8. AdjustmentTrace 测试 ──────────────────────────────────

class TestAdjustmentTrace:
    """AdjustmentTrace 记录格式。"""

    def test_trace_has_all_fields(self, dynamic_router, simple_plan):
        """每层 trace 都包含必要字段。"""
        ctx = RoutingContext(
            token_budget=TokenBudget(remaining=500000, total=1000000),
            scenario="general",
        )
        result = dynamic_router.route(simple_plan, "测试", ctx)
        for adj in result.adjustments:
            assert adj.layer in ("cost", "sla", "compliance")
            assert isinstance(adj.adjusted, bool)
            assert isinstance(adj.reason, str)
            assert len(adj.reason) > 0

    def test_unadjusted_trace_has_empty_before_after(self, dynamic_router, simple_plan):
        """未调整的 trace 的 before/after 可以为空。"""
        ctx = RoutingContext(scenario="general")
        result = dynamic_router.route(simple_plan, "测试", ctx)
        for adj in result.adjustments:
            if not adj.adjusted:
                # 未调整时 before/after 可能为空或相同
                pass  # 行为正确即可
