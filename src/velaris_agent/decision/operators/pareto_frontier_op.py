"""Procurement pareto frontier operator。"""

from __future__ import annotations

from typing import Any

from velaris_agent.decision.context import DecisionExecutionContext, OperatorTraceRecord
from velaris_agent.decision.operators.base import OperatorSpec
from velaris_agent.memory.types import DecisionOptionSchema, get_decision_metrics_for_scenario


class ParetoFrontierOp:
    """识别可行集合中的非支配前沿。

    这个算子只比较已经通过硬约束的 accepted options，
    不会把 rejected options 拉回比较池。
    """

    spec = OperatorSpec("pareto_frontier")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        """在 accepted options 上计算 Pareto frontier 与 dominated tail。"""

        if not context.accepted_options:
            context.pareto_frontier = []
            context.dominated_options = []
            context.frontier_metrics = []
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

        comparable_metrics = {
            item.metric_id
            for item in get_decision_metrics_for_scenario(context.scenario)
        }
        frontier: list[DecisionOptionSchema] = []
        dominated: list[DecisionOptionSchema] = []
        frontier_metrics: list[dict[str, Any]] = []

        for candidate in context.accepted_options:
            dominated_by: list[str] = []
            dominates_ids: list[str] = []
            for peer in context.accepted_options:
                if peer.option_id == candidate.option_id:
                    continue
                if _dominates(peer, candidate, comparable_metrics):
                    dominated_by.append(peer.option_id)
                if _dominates(candidate, peer, comparable_metrics):
                    dominates_ids.append(peer.option_id)

            if dominated_by:
                dominated.append(candidate)
                continue

            frontier.append(candidate)
            frontier_metrics.append(
                {
                    "option_id": candidate.option_id,
                    "dominates_option_ids": dominates_ids,
                    "dominated_by_option_ids": [],
                    "dominated_option_ids": dominates_ids,
                }
            )

        context.pareto_frontier = frontier
        context.dominated_options = dominated
        context.frontier_metrics = frontier_metrics
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


def _dominates(
    lhs: DecisionOptionSchema,
    rhs: DecisionOptionSchema,
    comparable_metrics: set[str],
) -> bool:
    """判断 lhs 是否在共享比较维度上支配 rhs。"""

    lhs_scores = {
        metric.metric_id: metric.normalized_score
        for metric in lhs.metrics
        if metric.metric_id in comparable_metrics
    }
    rhs_scores = {
        metric.metric_id: metric.normalized_score
        for metric in rhs.metrics
        if metric.metric_id in comparable_metrics
    }
    shared_metrics = set(lhs_scores) & set(rhs_scores)
    if not shared_metrics:
        return False

    return all(lhs_scores[mid] >= rhs_scores[mid] for mid in shared_metrics) and any(
        lhs_scores[mid] > rhs_scores[mid] for mid in shared_metrics
    )
