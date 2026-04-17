"""Procurement intent operator。"""

from __future__ import annotations

from velaris_agent.decision.context import DecisionExecutionContext, OperatorTraceRecord
from velaris_agent.decision.operators.base import OperatorSpec


class IntentOp:
    """解析 procurement 的最小意图槽位。"""

    spec = OperatorSpec("intent")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        """从 payload 中提取预算、合规与交付约束。"""

        context.intent = {
            "query": context.query,
            "budget_max": context.payload.get("budget_max"),
            "require_compliance": bool(
                context.payload.get("require_compliance", True)
            ),
            "max_delivery_days": context.payload.get("max_delivery_days"),
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
