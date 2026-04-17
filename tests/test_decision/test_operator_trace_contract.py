"""Decision operator trace contract tests."""

from __future__ import annotations

from velaris_agent.decision.operators.registry import build_default_operator_registry


def test_operator_trace_record_contains_phase2_contract_fields() -> None:
    """Operator spec 应暴露 Phase 2 trace contract 的版本字段。"""

    registry = build_default_operator_registry()
    spec = registry.get_graph("procurement")[0]

    assert spec.operator_version == "v1"
    assert spec.input_schema_version == "v1"
    assert spec.output_schema_version == "v1"
