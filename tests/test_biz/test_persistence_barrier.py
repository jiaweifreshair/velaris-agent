"""PreExecutionPersistenceBarrier 测试。"""

from __future__ import annotations

import pytest

from velaris_agent.velaris.execution_contract import (
    BizExecutionRecord,
    DecisionExecutionRequest,
    GovernanceGateDecision,
)


class _FakeSessionRepository:
    """最小 session 仓储假对象。"""

    def __init__(self) -> None:
        self.records = []

    def upsert(self, record):
        self.records.append(record)
        return record


class _FakeExecutionRepository:
    """最小 execution 仓储假对象。"""

    def __init__(self) -> None:
        self.records = []

    def create(self, record, *, snapshot_json=None):
        self.records.append((record, snapshot_json or {}))
        return record


class _FailingExecutionRepository:
    """模拟 execution 持久化失败。"""

    def create(self, record, *, snapshot_json=None):
        del record, snapshot_json
        raise ConnectionError("postgres connect failed with token=abcd1234")


def test_persistence_barrier_persists_session_and_marks_degraded_audit_pending() -> None:
    """中风险 degraded 路径应先集中落库，并把 audit_status 置为 pending。"""

    from velaris_agent.velaris.persistence_barrier import PreExecutionPersistenceBarrier

    barrier = PreExecutionPersistenceBarrier(
        session_repository=_FakeSessionRepository(),
        execution_repository=_FakeExecutionRepository(),
    )
    request = DecisionExecutionRequest(
        query="执行采购比价",
        payload={"contact_email": "ceo@example.com"},
        constraints={"risk_level": "medium"},
        scenario_hint="procurement",
        session_id="session-barrier",
    )
    execution = BizExecutionRecord(
        execution_id="exec-barrier",
        session_id="session-barrier",
        scenario="procurement",
        execution_status="planned",
        gate_status="degraded",
        effective_risk_level="medium",
        degraded_mode=True,
        audit_status="not_required",
        structural_complete=False,
        constraint_complete=False,
        goal_complete=False,
        created_at="2026-04-18T20:20:00+08:00",
        updated_at="2026-04-18T20:20:00+08:00",
    )
    gate_decision = GovernanceGateDecision(
        gate_status="degraded",
        effective_risk_level="medium",
        requires_forced_audit=True,
        degraded_mode=True,
        reason="scenario profile requires audited degraded execution",
    )

    result = barrier.persist(
        request=request,
        execution=execution,
        gate_decision=gate_decision,
        session_snapshot={"cwd": "/workspace/velaris-agent"},
        execution_snapshot={"plan": {"scenario": "procurement"}},
    )

    assert result.session_record is not None
    assert result.session_record.binding_mode == "attached"
    assert result.execution_record.audit_status == "pending"
    assert result.execution_record.degraded_mode is True
    assert result.audit_event_count == 0


def test_persistence_barrier_fail_closed_on_repository_error() -> None:
    """集中落库失败时必须在 scenario 之前 fail-closed 并给出基础设施分类。"""

    from velaris_agent.velaris.persistence_barrier import (
        PreExecutionPersistenceBarrier,
        PreExecutionPersistenceError,
    )

    barrier = PreExecutionPersistenceBarrier(
        session_repository=_FakeSessionRepository(),
        execution_repository=_FailingExecutionRepository(),
    )
    request = DecisionExecutionRequest(
        query="执行采购比价",
        payload={},
        constraints={"risk_level": "low"},
        scenario_hint="procurement",
        session_id="session-barrier-fail",
    )
    execution = BizExecutionRecord(
        execution_id="exec-barrier-fail",
        session_id="session-barrier-fail",
        scenario="procurement",
        execution_status="planned",
        gate_status="allowed",
        effective_risk_level="low",
        degraded_mode=False,
        audit_status="not_required",
        structural_complete=False,
        constraint_complete=False,
        goal_complete=False,
        created_at="2026-04-18T20:21:00+08:00",
        updated_at="2026-04-18T20:21:00+08:00",
    )
    gate_decision = GovernanceGateDecision(
        gate_status="allowed",
        effective_risk_level="low",
        requires_forced_audit=False,
        degraded_mode=False,
        reason="safe to proceed",
    )

    with pytest.raises(PreExecutionPersistenceError) as exc_info:
        barrier.persist(
            request=request,
            execution=execution,
            gate_decision=gate_decision,
        )

    assert exc_info.value.classification.error_code == "infrastructure_unavailable"
    assert exc_info.value.classification.stage == "execution_create"
    assert exc_info.value.classification.retryable is True
