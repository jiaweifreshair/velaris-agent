"""统一决策指标与审计模型测试。"""

from __future__ import annotations

import velaris_agent.memory.types as memory_types


def test_metrics_registry_covers_procurement_and_shared_dimensions() -> None:
    """指标注册表应同时覆盖 procurement 与现有验证场景。"""

    assert hasattr(memory_types, "get_decision_metrics_for_scenario")
    assert hasattr(memory_types, "get_decision_metric")

    procurement_metrics = {
        metric.metric_id
        for metric in memory_types.get_decision_metrics_for_scenario("procurement")
    }
    cost_metric = memory_types.get_decision_metric("cost")

    assert cost_metric is not None
    assert {"cost", "quality", "delivery", "compliance", "risk"}.issubset(procurement_metrics)
    assert {"travel", "tokencost", "robotclaw", "procurement"}.issubset(set(cost_metric.scenarios))


def test_unified_option_schema_keeps_metric_evidence_refs() -> None:
    """统一 option schema 应能承载指标值、归一化分与证据引用。"""

    assert hasattr(memory_types, "DecisionOptionMetric")
    assert hasattr(memory_types, "DecisionOptionSchema")

    option = memory_types.DecisionOptionSchema(
        option_id="vendor-a",
        scenario="procurement",
        label="供应商 A 标准方案",
        metrics=[
            memory_types.DecisionOptionMetric(
                metric_id="cost",
                raw_value=118000,
                normalized_score=0.82,
                evidence_refs=["quote://vendor-a"],
            ),
            memory_types.DecisionOptionMetric(
                metric_id="compliance",
                raw_value=0.98,
                normalized_score=0.98,
                evidence_refs=["policy://approved-vendors"],
            ),
        ],
        metadata={"vendor": "供应商 A"},
    )

    assert option.metrics[0].metric_id == "cost"
    assert option.metrics[0].evidence_refs == ["quote://vendor-a"]
    assert option.metadata["vendor"] == "供应商 A"


def test_unified_audit_schema_contains_operator_contract_fields() -> None:
    """统一 audit schema 应预留 Phase 2 算子契约字段。"""

    assert hasattr(memory_types, "DecisionAuditSchema")

    audit_event = memory_types.DecisionAuditSchema(
        session_id="session-procurement-1",
        decision_id="decision-procurement-1",
        step_name="normalization.completed",
        operator_id="procurement_compare",
        operator_version="v1",
        input_ref="decision://input/procurement-1",
        output_ref="decision://output/procurement-1",
        evidence_refs=["quote://vendor-a", "policy://approved-vendors"],
        confidence=0.93,
        trace_id="trace-procurement-1",
    )

    assert audit_event.operator_id == "procurement_compare"
    assert audit_event.operator_version == "v1"
    assert audit_event.evidence_refs == ["quote://vendor-a", "policy://approved-vendors"]
    assert audit_event.confidence == 0.93
