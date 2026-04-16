"""Phase 3 多目标求解器拆分测试。"""

from __future__ import annotations

from velaris_agent.decision.context import DecisionExecutionContext
from velaris_agent.decision.operators.feasibility_op import FeasibilityOp
from velaris_agent.decision.operators.intent_op import IntentOp
from velaris_agent.decision.operators.normalization_op import NormalizationOp
from velaris_agent.decision.operators.option_discovery_op import OptionDiscoveryOp
from velaris_agent.decision.operators.pareto_frontier_op import ParetoFrontierOp


def _build_procurement_context(
    *,
    options: list[dict[str, object]],
    decision_weights: dict[str, float] | None = None,
    budget_max: int = 250000,
    require_compliance: bool = True,
    max_delivery_days: int | None = None,
) -> DecisionExecutionContext:
    """构造最小采购上下文，复用在算子级红绿测试中。"""

    return DecisionExecutionContext(
        scenario="procurement",
        query="比较供应商并输出推荐。",
        payload={
            "budget_max": budget_max,
            "require_compliance": require_compliance,
            "max_delivery_days": max_delivery_days,
            "decision_weights": decision_weights or {},
            "options": options,
        },
        constraints={},
        decision_weights=decision_weights or {},
    )


def test_normalization_op_only_outputs_normalized_options() -> None:
    """NormalizationOp 只负责 schema 标准化，不能再直接裁剪可行域。"""

    context = _build_procurement_context(
        budget_max=130000,
        max_delivery_days=10,
        options=[
            {
                "id": "vendor-a",
                "label": "供应商 A",
                "price_cny": 118000,
                "delivery_days": 9,
                "quality_score": 0.90,
                "compliance_score": 0.98,
                "risk_score": 0.10,
                "available": True,
            },
            {
                "id": "vendor-b",
                "label": "供应商 B",
                "price_cny": 145000,
                "delivery_days": 12,
                "quality_score": 0.86,
                "compliance_score": 0.82,
                "risk_score": 0.14,
                "available": True,
            },
        ],
    )

    context = IntentOp().run(context)
    context = OptionDiscoveryOp().run(context)
    context = NormalizationOp().run(context)

    assert [item.option_id for item in context.normalized_options] == ["vendor-a", "vendor-b"]
    assert context.accepted_options == []
    assert context.rejected_options == []


def test_feasibility_op_owns_hard_constraint_filtering() -> None:
    """FeasibilityOp 负责预算、交付与合规硬约束的统一过滤。"""

    context = _build_procurement_context(
        budget_max=130000,
        max_delivery_days=10,
        options=[
            {
                "id": "vendor-a",
                "label": "供应商 A",
                "price_cny": 118000,
                "delivery_days": 9,
                "quality_score": 0.90,
                "compliance_score": 0.98,
                "risk_score": 0.10,
                "available": True,
            },
            {
                "id": "vendor-b",
                "label": "供应商 B",
                "price_cny": 145000,
                "delivery_days": 12,
                "quality_score": 0.86,
                "compliance_score": 0.82,
                "risk_score": 0.14,
                "available": True,
            },
        ],
    )

    context = IntentOp().run(context)
    context = OptionDiscoveryOp().run(context)
    context = NormalizationOp().run(context)
    context = FeasibilityOp().run(context)

    assert [item.option_id for item in context.accepted_options] == ["vendor-a"]
    assert [item.option_id for item in context.rejected_options] == ["vendor-b"]
    assert context.rejection_reasons["vendor-b"] == [
        "budget_exceeded",
        "delivery_exceeds_limit",
        "compliance_below_threshold",
    ]


def test_pareto_frontier_op_keeps_only_non_dominated_feasible_options() -> None:
    """ParetoFrontierOp 只保留非支配可行方案，并记录 dominated tail。"""

    context = _build_procurement_context(
        options=[
            {
                "id": "cheap-fast",
                "label": "低价快交付",
                "price_cny": 100000,
                "delivery_days": 5,
                "quality_score": 0.80,
                "compliance_score": 0.95,
                "risk_score": 0.20,
                "available": True,
            },
            {
                "id": "premium-safe",
                "label": "高质量低风险",
                "price_cny": 170000,
                "delivery_days": 7,
                "quality_score": 0.95,
                "compliance_score": 0.98,
                "risk_score": 0.10,
                "available": True,
            },
            {
                "id": "dominated-mid",
                "label": "被支配方案",
                "price_cny": 175000,
                "delivery_days": 8,
                "quality_score": 0.90,
                "compliance_score": 0.96,
                "risk_score": 0.12,
                "available": True,
            },
        ],
    )

    context = IntentOp().run(context)
    context = OptionDiscoveryOp().run(context)
    context = NormalizationOp().run(context)
    context = FeasibilityOp().run(context)
    context = ParetoFrontierOp().run(context)

    assert [item.option_id for item in context.pareto_frontier] == [
        "cheap-fast",
        "premium-safe",
    ]
    assert [item.option_id for item in context.dominated_options] == ["dominated-mid"]
    assert [item["option_id"] for item in context.frontier_metrics] == [
        "cheap-fast",
        "premium-safe",
    ]
    assert context.frontier_metrics[1]["dominated_option_ids"] == ["dominated-mid"]
