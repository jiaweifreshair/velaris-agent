"""Negotiation operator。"""

from __future__ import annotations

from velaris_agent.decision.context import DecisionExecutionContext, OperatorTraceRecord
from velaris_agent.decision.operators.base import OperatorSpec


class NegotiationOp:
    """把 stakeholder conflict 摘要稳定写入上下文。"""

    spec = OperatorSpec("negotiation")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        """记录最小 negotiation summary。"""

        context.negotiation_summary = {
            "proposals": list(
                context.stakeholder_context.get("negotiation_proposals", [])
            ),
            "conflicts": list(context.stakeholder_context.get("conflicts", [])),
        }
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
