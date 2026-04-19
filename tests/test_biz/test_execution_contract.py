"""Execution contract 测试。"""

from __future__ import annotations

from velaris_agent.velaris.execution_contract import (
    AuditSummary,
    BizExecutionRecord,
    DecisionExecutionEnvelope,
    DecisionExecutionRequest,
    GovernanceGateDecision,
)


def test_decision_execution_request_to_dict_keeps_bridge_boundary_fields() -> None:
    """桥接请求应只保留 UOW-1 约定的最小标准化字段。"""

    request = DecisionExecutionRequest(
        query="为 robotaxi 派单生成服务提案并形成交易合约",
        payload={"masked": True},
        constraints={"risk_level": "high"},
        scenario_hint="robotclaw",
        session_id="session-contract",
    )

    assert request.to_dict() == {
        "query": "为 robotaxi 派单生成服务提案并形成交易合约",
        "payload": {"masked": True},
        "constraints": {"risk_level": "high"},
        "scenario_hint": "robotclaw",
        "session_id": "session-contract",
    }



def test_biz_execution_record_to_dict_exposes_status_completion_and_audit_state() -> None:
    """execution 主实体应同时表达主状态、completion 派生字段与审计状态。"""

    record = BizExecutionRecord(
        execution_id="exec-001",
        session_id="session-001",
        scenario="robotclaw",
        execution_status="partially_completed",
        gate_status="degraded",
        effective_risk_level="medium",
        degraded_mode=True,
        audit_status="pending",
        structural_complete=True,
        constraint_complete=False,
        goal_complete=False,
        created_at="2026-04-18T16:00:00+08:00",
        updated_at="2026-04-18T16:00:05+08:00",
        resume_cursor={"stage": "scenario_completed"},
    )

    payload = record.to_dict()

    assert payload["execution_id"] == "exec-001"
    assert payload["execution_status"] == "partially_completed"
    assert payload["gate_status"] == "degraded"
    assert payload["effective_risk_level"] == "medium"
    assert payload["audit_status"] == "pending"
    assert payload["structural_complete"] is True
    assert payload["constraint_complete"] is False
    assert payload["goal_complete"] is False
    assert payload["resume_cursor"] == {"stage": "scenario_completed"}



def test_governance_gate_decision_to_dict_preserves_forced_audit_and_reason() -> None:
    """gate 决策应显式表达降级原因和强制审计要求。"""

    decision = GovernanceGateDecision(
        gate_status="degraded",
        effective_risk_level="medium",
        requires_forced_audit=True,
        degraded_mode=True,
        reason="scenario profile requires audited degraded execution",
    )

    assert decision.to_dict() == {
        "gate_status": "degraded",
        "effective_risk_level": "medium",
        "requires_forced_audit": True,
        "degraded_mode": True,
        "reason": "scenario profile requires audited degraded execution",
    }



def test_decision_execution_envelope_to_tool_payload_is_envelope_first_and_keeps_minimal_aliases() -> None:
    """对外工具输出应以 envelope 为主，只保留极少数兼容 alias。"""

    execution = BizExecutionRecord(
        execution_id="exec-002",
        session_id="session-002",
        scenario="procurement",
        execution_status="completed",
        gate_status="allowed",
        effective_risk_level="low",
        degraded_mode=False,
        audit_status="persisted",
        structural_complete=True,
        constraint_complete=True,
        goal_complete=True,
        created_at="2026-04-18T16:01:00+08:00",
        updated_at="2026-04-18T16:01:02+08:00",
    )
    gate_decision = GovernanceGateDecision(
        gate_status="allowed",
        effective_risk_level="low",
        requires_forced_audit=False,
        degraded_mode=False,
        reason="safe to proceed",
    )
    audit = AuditSummary(
        audit_required=False,
        audit_event_count=1,
        degraded_mode=False,
        audit_status="persisted",
        last_event="orchestrator.completed",
    )
    envelope = DecisionExecutionEnvelope(
        execution=execution,
        plan={"scenario": "procurement"},
        routing={"selected_strategy": "local_closed_loop"},
        authority={"approvals_required": False},
        gate_decision=gate_decision,
        tasks=[{"task_id": "task-001", "task_status": "completed"}],
        outcome={"success": True, "summary": "推荐完成"},
        result={"recommended": {"id": "vendor-a"}},
        audit=audit,
    )

    payload = envelope.to_tool_payload()

    assert set(payload.keys()) == {
        "envelope",
        "session_id",
        "result",
        "outcome",
        "audit_event_count",
    }
    assert payload["session_id"] == "session-002"
    assert payload["audit_event_count"] == 1
    assert payload["outcome"]["success"] is True
    assert payload["envelope"]["execution"]["execution_id"] == "exec-002"
    assert payload["envelope"]["gate_decision"]["gate_status"] == "allowed"
    assert payload["envelope"]["audit"]["audit_status"] == "persisted"
