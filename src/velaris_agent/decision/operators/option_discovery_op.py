"""Procurement option discovery operator。"""

from __future__ import annotations

from velaris_agent.decision.context import DecisionExecutionContext, OperatorTraceRecord
from velaris_agent.decision.operators.base import OperatorSpec


class OptionDiscoveryOp:
    """把 payload 中的原始 options 暴露给后续算子。"""

    spec = OperatorSpec("option_discovery")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        """读取输入候选项，不在这一层做筛选。"""

        context.raw_options = list(context.payload.get("options", []))
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
