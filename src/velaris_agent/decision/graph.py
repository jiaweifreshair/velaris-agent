"""Decision graph executor。"""

from __future__ import annotations

from typing import Any

from velaris_agent.decision.context import DecisionExecutionContext, DecisionGraphResult
from velaris_agent.decision.operators.base import DecisionOperator
from velaris_agent.decision.operators.bias_audit_op import BiasAuditOp
from velaris_agent.decision.operators.explanation_op import ExplanationOp
from velaris_agent.decision.operators.feasibility_op import FeasibilityOp
from velaris_agent.decision.operators.intent_op import IntentOp
from velaris_agent.decision.operators.negotiation_op import NegotiationOp
from velaris_agent.decision.operators.normalization_op import NormalizationOp
from velaris_agent.decision.operators.option_discovery_op import OptionDiscoveryOp
from velaris_agent.decision.operators.optimization_op import OptimizationOp
from velaris_agent.decision.operators.registry import build_default_operator_registry
from velaris_agent.decision.operators.stakeholder_op import StakeholderOp


def build_default_operators_for_scenario(scenario: str) -> list[DecisionOperator]:
    """按 registry 组装默认 operator 链。"""

    registry = build_default_operator_registry()
    operator_map = {
        "intent": IntentOp,
        "option_discovery": OptionDiscoveryOp,
        "normalization": NormalizationOp,
        "stakeholder": StakeholderOp,
        "feasibility": FeasibilityOp,
        "optimization": OptimizationOp,
        "negotiation": NegotiationOp,
        "bias_audit": BiasAuditOp,
        "explanation": ExplanationOp,
    }
    return [operator_map[spec.operator_id]() for spec in registry.get_graph(scenario)]


def execute_decision_graph(
    *,
    scenario: str,
    query: str,
    payload: dict[str, Any],
    constraints: dict[str, Any] | None = None,
) -> DecisionGraphResult:
    """执行 procurement decision graph。"""

    context = DecisionExecutionContext(
        scenario=scenario,
        query=query,
        payload=payload,
        constraints=constraints or {},
        decision_weights=_extract_decision_weights(payload),
    )
    for operator in build_default_operators_for_scenario(scenario):
        context = operator.run(context)
    return DecisionGraphResult(
        scenario=context.scenario,
        ranked_options=context.ranked_options,
        accepted_option_ids=[item.option_id for item in context.accepted_options],
        rejected_option_ids=[item.option_id for item in context.rejected_options],
        rejection_reasons=context.rejection_reasons,
        pareto_frontier_ids=[item.option_id for item in context.pareto_frontier],
        dominated_option_ids=[item.option_id for item in context.dominated_options],
        frontier_metrics=context.frontier_metrics,
        operating_point_summary=dict(context.operating_point_summary),
        recommended_option_id=context.recommended_option_id,
        explanation=context.explanation,
        warnings=context.warnings,
        operator_traces=context.operator_traces,
    )


def _extract_decision_weights(payload: dict[str, Any]) -> dict[str, float]:
    """从 graph payload 中提取显式传入的排序权重。"""

    raw_weights = payload.get("decision_weights")
    if not isinstance(raw_weights, dict):
        return {}

    normalized: dict[str, float] = {}
    for key, value in raw_weights.items():
        try:
            normalized[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return normalized
