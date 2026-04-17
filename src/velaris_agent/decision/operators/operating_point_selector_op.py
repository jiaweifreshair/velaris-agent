"""Procurement operating point selector operator。"""

from __future__ import annotations

from typing import Any

from velaris_agent.decision.context import DecisionExecutionContext, OperatorTraceRecord
from velaris_agent.decision.operators.base import OperatorSpec
from velaris_agent.decision.operators.optimization_op import (
    DEFAULT_PROCUREMENT_WEIGHTS,
    merge_weights,
    score_weighted_sum,
)
from velaris_agent.memory.types import DecisionOptionSchema


class OperatingPointSelectorOp:
    """在 Pareto 前沿内部选择最终 operating point。

    这个算子只对前沿集合做 weighted-sum 选点，
    被支配方案仅作为 ranked tail 追加到结果末尾，保持 legacy 协议不丢项。
    """

    spec = OperatorSpec("operating_point_selector")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        """在 frontier 中选择推荐点，并写回完整 ranked options。"""

        frontier = list(context.pareto_frontier or context.accepted_options)
        if not frontier:
            context.ranked_options = []
            context.recommended_option_id = None
            context.operating_point_summary = {
                "selector": "weighted_sum_over_frontier",
                "frontier_option_ids": [],
                "selected_option_id": None,
                "penalties": {},
            }
            context.operator_traces.append(
                OperatorTraceRecord(
                    operator_id=self.spec.operator_id,
                    operator_version=self.spec.operator_version,
                    input_schema_version=self.spec.input_schema_version,
                    output_schema_version=self.spec.output_schema_version,
                    confidence=0.0,
                    warnings=["no_feasible_option"],
                )
            )
            return context

        merged_weights = merge_weights(
            DEFAULT_PROCUREMENT_WEIGHTS,
            context.decision_weights,
        )
        ranked_frontier = score_weighted_sum(
            options=_to_scored_input(frontier),
            weights=merged_weights,
        )
        ranked_frontier_ids = [item["id"] for item in ranked_frontier]
        ranked_frontier_map = {item["id"]: item for item in ranked_frontier}
        ranked_dominated = score_weighted_sum(
            options=_to_scored_input(context.dominated_options),
            weights=merged_weights,
        )
        ranked_dominated_ids = [item["id"] for item in ranked_dominated]
        ranked_dominated_map = {item["id"]: item for item in ranked_dominated}

        ranked_frontier_options = sorted(
            frontier,
            key=lambda item: ranked_frontier_ids.index(item.option_id),
        )
        dominated_tail_options = (
            sorted(
                context.dominated_options,
                key=lambda item: ranked_dominated_ids.index(item.option_id),
            )
            if ranked_dominated_ids
            else list(context.dominated_options)
        )
        context.ranked_options = ranked_frontier_options + dominated_tail_options
        context.recommended_option_id = ranked_frontier_ids[0]
        context.operating_point_summary = {
            "selector": "weighted_sum_over_frontier",
            "frontier_option_ids": [item.option_id for item in frontier],
            "selected_option_id": context.recommended_option_id,
            "selected_total_score": ranked_frontier_map[context.recommended_option_id][
                "total_score"
            ],
            "penalties": {
                "conflict_cost": 0.0,
                "policy_risk": 0.0,
                "uncertainty": 0.0,
                "regret_estimate": 0.0,
            },
            "weights": merged_weights,
        }
        _write_score_metadata(
            context.ranked_options,
            {**ranked_frontier_map, **ranked_dominated_map},
        )
        context.operator_traces.append(
            OperatorTraceRecord(
                operator_id=self.spec.operator_id,
                operator_version=self.spec.operator_version,
                input_schema_version=self.spec.input_schema_version,
                output_schema_version=self.spec.output_schema_version,
                confidence=1.0,
            )
        )
        return context


def _to_scored_input(options: list[DecisionOptionSchema]) -> list[dict[str, Any]]:
    """把统一 schema 转换成 weighted-sum helper 可读的输入格式。"""

    return [
        {
            "id": option.option_id,
            "label": option.label,
            "scores": {
                metric.metric_id: metric.normalized_score
                for metric in option.metrics
            },
        }
        for option in options
    ]


def _write_score_metadata(
    ranked_options: list[DecisionOptionSchema],
    scored_map: dict[str, dict[str, Any]],
) -> None:
    """把 weighted-sum 结果写回 option metadata，供 legacy adapter 继续复用。"""

    for option in ranked_options:
        scored = scored_map.get(option.option_id)
        if scored is None:
            continue
        option.metadata["total_score"] = scored["total_score"]
        option.metadata["score_breakdown"] = dict(scored["scores"])
