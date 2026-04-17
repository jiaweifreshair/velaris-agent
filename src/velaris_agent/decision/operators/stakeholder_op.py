"""Stakeholder operator。"""

from __future__ import annotations

from typing import Any

from velaris_agent.decision.context import DecisionExecutionContext, OperatorTraceRecord
from velaris_agent.decision.operators.base import OperatorSpec


class StakeholderOp:
    """注入最小 stakeholder context。

    Phase 2 的 procurement graph 先允许没有 stakeholder map，
    只保留 conflicts/proposals 的稳定占位结构，方便后续增强。
    """

    spec = OperatorSpec("stakeholder")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        """写入最小 stakeholder context。"""

        context.stakeholder_context = _normalize_stakeholder_context(
            context.payload,
            context.scenario,
        )
        stakeholder_warnings = list(context.stakeholder_context.get("warnings", []))
        context.warnings = list(
            dict.fromkeys([*context.warnings, *stakeholder_warnings])
        )
        context.operator_traces.append(
            OperatorTraceRecord(
                operator_id=self.spec.operator_id,
                operator_version=self.spec.operator_version,
                input_schema_version=self.spec.input_schema_version,
                output_schema_version=self.spec.output_schema_version,
                confidence=1.0,
                warnings=stakeholder_warnings,
            )
        )
        return context


def _normalize_stakeholder_context(
    payload: dict[str, Any],
    scenario: str,
) -> dict[str, Any]:
    """把 payload 中不同来源的 stakeholder 字段收口成统一结构。"""

    raw_context = payload.get("stakeholder_context")
    if hasattr(raw_context, "model_dump"):
        raw_context = raw_context.model_dump(mode="json")

    if isinstance(raw_context, dict):
        return {
            "scenario": raw_context.get("scenario", scenario),
            "stakeholder_ids": list(raw_context.get("stakeholder_ids", [])),
            "alignment_matrix": list(raw_context.get("alignment_matrix", [])),
            "conflicts": list(raw_context.get("conflicts", [])),
            "negotiation_proposals": list(
                raw_context.get("negotiation_proposals", [])
            ),
            "warnings": list(raw_context.get("warnings", [])),
        }

    return {
        "scenario": scenario,
        "stakeholder_ids": [],
        "alignment_matrix": [],
        "conflicts": list(payload.get("stakeholder_conflicts", [])),
        "negotiation_proposals": list(
            payload.get("negotiation_proposals", [])
        ),
        "warnings": list(payload.get("stakeholder_warnings", [])),
    }
