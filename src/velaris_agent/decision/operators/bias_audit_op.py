"""Bias audit operator。"""

from __future__ import annotations

from velaris_agent.decision.context import DecisionExecutionContext, OperatorTraceRecord
from velaris_agent.decision.operators.base import OperatorSpec


class BiasAuditOp:
    """输出 Phase 2 的 no-op bias audit 结果。"""

    spec = OperatorSpec("bias_audit")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        """当前阶段仅回填结构化空摘要。"""

        context.bias_summary = {"warnings": []}
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
