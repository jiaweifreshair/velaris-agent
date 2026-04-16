"""Explanation operator。"""

from __future__ import annotations

from velaris_agent.decision.context import DecisionExecutionContext, OperatorTraceRecord
from velaris_agent.decision.operators.base import OperatorSpec


class ExplanationOp:
    """为推荐结果生成解释和最终 trace。"""

    spec = OperatorSpec("explanation")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        """根据 recommended option 汇总 explanation 与 evidence refs。"""

        recommended = next(
            (
                item
                for item in context.ranked_options
                if item.option_id == context.recommended_option_id
            ),
            None,
        )
        if recommended is None:
            context.explanation = "没有供应商同时满足预算、交付与合规约束。"
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

        evidence_refs: list[str] = []
        for metric in recommended.metrics:
            evidence_refs.extend(metric.evidence_refs)
        frontier_size = len(context.pareto_frontier)
        context.explanation = (
            f"推荐 {recommended.label}，因为它位于 Pareto 前沿（共 {frontier_size} 个候选点），"
            f"并在当前权重下成为 operating point。"
        )
        context.operator_traces.append(
            OperatorTraceRecord(
                operator_id=self.spec.operator_id,
                operator_version=self.spec.operator_version,
                input_schema_version=self.spec.input_schema_version,
                output_schema_version=self.spec.output_schema_version,
                confidence=1.0,
                evidence_refs=list(dict.fromkeys(evidence_refs)),
            )
        )
        return context
