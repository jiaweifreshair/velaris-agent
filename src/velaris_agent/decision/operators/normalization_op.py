"""Procurement normalization operator。"""

from __future__ import annotations

from velaris_agent.decision.context import DecisionExecutionContext, OperatorTraceRecord
from velaris_agent.decision.operators.base import OperatorSpec
from velaris_agent.memory.types import DecisionOptionMetric, DecisionOptionSchema


class NormalizationOp:
    """把原始 procurement options 映射成统一 schema。

    这个算子只负责字段标准化，不再承担硬约束过滤，
    以便后续由独立的 FeasibilityOp 管理可行域。
    """

    spec = OperatorSpec("normalization")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        """输出 normalized options，并清空上一阶段遗留的 feasibility 状态。"""

        normalized: list[DecisionOptionSchema] = []

        for option in context.raw_options:
            evidence_refs = [str(item) for item in option.get("evidence_refs", [])]
            normalized_option = DecisionOptionSchema(
                option_id=str(option["id"]),
                scenario=context.scenario,
                label=str(option["label"]),
                metrics=[
                    DecisionOptionMetric(
                        metric_id="cost",
                        raw_value=option["price_cny"],
                        normalized_score=0.0,
                        evidence_refs=list(evidence_refs),
                    ),
                    DecisionOptionMetric(
                        metric_id="quality",
                        raw_value=option["quality_score"],
                        normalized_score=float(option["quality_score"]),
                        evidence_refs=list(evidence_refs),
                    ),
                    DecisionOptionMetric(
                        metric_id="delivery",
                        raw_value=option["delivery_days"],
                        normalized_score=0.0,
                        evidence_refs=list(evidence_refs),
                    ),
                    DecisionOptionMetric(
                        metric_id="compliance",
                        raw_value=option["compliance_score"],
                        normalized_score=float(option["compliance_score"]),
                        evidence_refs=list(evidence_refs),
                    ),
                    DecisionOptionMetric(
                        metric_id="risk",
                        raw_value=option["risk_score"],
                        normalized_score=1 - float(option["risk_score"]),
                        evidence_refs=list(evidence_refs),
                    ),
                ],
                metadata={
                    "raw_option": dict(option),
                    "available": bool(option.get("available", True)),
                },
            )
            normalized.append(normalized_option)

        context.normalized_options = normalized
        context.accepted_options = []
        context.rejected_options = []
        context.rejection_reasons = {}
        context.pareto_frontier = []
        context.dominated_options = []
        context.frontier_metrics = []
        context.operating_point_summary = {}
        context.ranked_options = []
        context.recommended_option_id = None
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
