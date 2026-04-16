"""Procurement operator graph tests."""

from __future__ import annotations

from velaris_agent.decision.graph import execute_decision_graph
from velaris_agent.decision.context import DecisionExecutionContext
from velaris_agent.decision.operators.feasibility_op import FeasibilityOp
from velaris_agent.decision.operators.intent_op import IntentOp
from velaris_agent.decision.operators.normalization_op import NormalizationOp
from velaris_agent.decision.operators.option_discovery_op import OptionDiscoveryOp


def test_procurement_front_half_builds_feasible_and_rejected_options() -> None:
    """Front-half operators 应在 feasibility 阶段区分 accepted/rejected options。"""

    context = DecisionExecutionContext(
        scenario="procurement",
        query="比较三家供应商，预算不超过 130000，必须通过合规审计。",
        payload={
            "budget_max": 130000,
            "require_compliance": True,
            "max_delivery_days": 10,
            "options": [
                {
                    "id": "vendor-a",
                    "label": "供应商 A",
                    "price_cny": 118000,
                    "delivery_days": 9,
                    "quality_score": 0.90,
                    "compliance_score": 0.98,
                    "risk_score": 0.10,
                    "available": True,
                    "evidence_refs": ["quote://vendor-a"],
                },
                {
                    "id": "vendor-b",
                    "label": "供应商 B",
                    "price_cny": 126000,
                    "delivery_days": 12,
                    "quality_score": 0.86,
                    "compliance_score": 0.82,
                    "risk_score": 0.14,
                    "available": True,
                    "evidence_refs": ["quote://vendor-b"],
                },
            ],
        },
        constraints={},
    )

    context = IntentOp().run(context)
    context = OptionDiscoveryOp().run(context)
    context = NormalizationOp().run(context)
    context = FeasibilityOp().run(context)

    assert context.intent["budget_max"] == 130000
    assert len(context.normalized_options) == 2
    assert [item.option_id for item in context.accepted_options] == ["vendor-a"]
    assert [item.option_id for item in context.rejected_options] == ["vendor-b"]
    assert context.rejection_reasons["vendor-b"] == [
        "delivery_exceeds_limit",
        "compliance_below_threshold",
    ]
    assert context.normalized_options[0].metrics[0].metric_id == "cost"
    assert [trace.operator_id for trace in context.operator_traces] == [
        "intent",
        "option_discovery",
        "normalization",
        "feasibility",
    ]


def test_procurement_graph_returns_recommendation_and_trace() -> None:
    """Full graph 应输出 recommendation、feasibility 结果与 explanation trace。"""

    result = execute_decision_graph(
        scenario="procurement",
        query="比较三家供应商，预算不超过 130000，必须通过合规审计。",
        payload={
            "budget_max": 130000,
            "require_compliance": True,
            "options": [
                {
                    "id": "vendor-a",
                    "label": "供应商 A",
                    "price_cny": 118000,
                    "delivery_days": 9,
                    "quality_score": 0.90,
                    "compliance_score": 0.98,
                    "risk_score": 0.10,
                    "available": True,
                    "evidence_refs": ["quote://vendor-a", "policy://approved-vendors"],
                },
                {
                    "id": "vendor-b",
                    "label": "供应商 B",
                    "price_cny": 145000,
                    "delivery_days": 7,
                    "quality_score": 0.91,
                    "compliance_score": 0.99,
                    "risk_score": 0.08,
                    "available": True,
                    "evidence_refs": ["quote://vendor-b"],
                },
            ],
        },
        constraints={},
    )

    assert result.recommended_option_id == "vendor-a"
    assert result.accepted_option_ids == ["vendor-a"]
    assert result.rejected_option_ids == ["vendor-b"]
    assert result.rejection_reasons["vendor-b"] == ["budget_exceeded"]
    assert result.pareto_frontier_ids == ["vendor-a"]
    assert result.dominated_option_ids == []
    assert result.operating_point_summary["selected_option_id"] == "vendor-a"
    assert [trace.operator_id for trace in result.operator_traces] == [
        "intent",
        "option_discovery",
        "normalization",
        "stakeholder",
        "feasibility",
        "pareto_frontier",
        "operating_point_selector",
        "negotiation",
        "bias_audit",
        "explanation",
    ]
    assert result.operator_traces[-1].operator_id == "explanation"
    assert result.operator_traces[-1].evidence_refs == [
        "quote://vendor-a",
        "policy://approved-vendors",
    ]
    assert "Pareto 前沿" in result.explanation


def test_procurement_graph_uses_cost_and_delivery_in_ranking() -> None:
    """成本与交付维度必须真正参与 accepted options 的排序。"""

    result = execute_decision_graph(
        scenario="procurement",
        query="比较两家供应商，预算不超过 200000，必须通过合规审计。",
        payload={
            "budget_max": 200000,
            "require_compliance": True,
            "options": [
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
                    "id": "expensive-slow",
                    "label": "高价慢交付",
                    "price_cny": 180000,
                    "delivery_days": 20,
                    "quality_score": 0.81,
                    "compliance_score": 0.95,
                    "risk_score": 0.20,
                    "available": True,
                },
            ],
        },
        constraints={},
    )

    ranked = {option.option_id: option for option in result.ranked_options}
    cheap_fast = ranked["cheap-fast"]
    expensive_slow = ranked["expensive-slow"]

    assert result.recommended_option_id == "cheap-fast"
    assert cheap_fast.metadata["score_breakdown"]["cost"] > expensive_slow.metadata["score_breakdown"]["cost"]
    assert cheap_fast.metadata["score_breakdown"]["delivery"] > expensive_slow.metadata["score_breakdown"]["delivery"]


def test_procurement_graph_honors_payload_decision_weights() -> None:
    """payload 中显式传入的 decision_weights 必须改变最终排序。"""

    result = execute_decision_graph(
        scenario="procurement",
        query="比较两家供应商，质量优先。",
        payload={
            "budget_max": 250000,
            "require_compliance": True,
            "decision_weights": {
                "cost": 0.10,
                "quality": 0.60,
                "delivery": 0.10,
                "compliance": 0.10,
                "risk": 0.10,
            },
            "options": [
                {
                    "id": "budget-choice",
                    "label": "低价方案",
                    "price_cny": 100000,
                    "delivery_days": 7,
                    "quality_score": 0.70,
                    "compliance_score": 0.95,
                    "risk_score": 0.10,
                    "available": True,
                },
                {
                    "id": "premium-choice",
                    "label": "高质量方案",
                    "price_cny": 170000,
                    "delivery_days": 7,
                    "quality_score": 0.95,
                    "compliance_score": 0.95,
                    "risk_score": 0.10,
                    "available": True,
                },
            ],
        },
        constraints={},
    )

    assert result.recommended_option_id == "premium-choice"
    assert result.pareto_frontier_ids == ["budget-choice", "premium-choice"]
    assert result.operating_point_summary["selector"] == "weighted_sum_over_frontier"
