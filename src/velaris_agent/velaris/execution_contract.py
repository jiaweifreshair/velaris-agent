"""Velaris execution-level contract 定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class DecisionExecutionRequest:
    """从 OpenHarness 进入 Velaris 的标准化请求。"""

    query: str
    payload: JsonDict = field(default_factory=dict)
    constraints: JsonDict = field(default_factory=dict)
    scenario_hint: str | None = None
    session_id: str | None = None

    def to_dict(self) -> JsonDict:
        """返回桥接层允许传入的最小字段集合。"""

        return {
            "query": self.query,
            "payload": dict(self.payload),
            "constraints": dict(self.constraints),
            "scenario_hint": self.scenario_hint,
            "session_id": self.session_id,
        }


@dataclass
class BizExecutionRecord:
    """业务执行主实体。"""

    execution_id: str
    session_id: str | None
    scenario: str
    execution_status: str
    gate_status: str
    effective_risk_level: str
    degraded_mode: bool
    audit_status: str
    structural_complete: bool
    constraint_complete: bool
    goal_complete: bool
    created_at: str
    updated_at: str
    resume_cursor: JsonDict | None = None

    def to_dict(self) -> JsonDict:
        """返回 execution 主实体的序列化结构。"""

        return {
            "execution_id": self.execution_id,
            "session_id": self.session_id,
            "scenario": self.scenario,
            "execution_status": self.execution_status,
            "gate_status": self.gate_status,
            "effective_risk_level": self.effective_risk_level,
            "degraded_mode": self.degraded_mode,
            "audit_status": self.audit_status,
            "structural_complete": self.structural_complete,
            "constraint_complete": self.constraint_complete,
            "goal_complete": self.goal_complete,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resume_cursor": dict(self.resume_cursor or {}),
        }


@dataclass(frozen=True)
class GovernanceGateDecision:
    """执行前治理门决策。"""

    gate_status: str
    effective_risk_level: str
    requires_forced_audit: bool
    degraded_mode: bool
    reason: str

    def to_dict(self) -> JsonDict:
        """返回 gate 决策序列化结构。"""

        return {
            "gate_status": self.gate_status,
            "effective_risk_level": self.effective_risk_level,
            "requires_forced_audit": self.requires_forced_audit,
            "degraded_mode": self.degraded_mode,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AuditSummary:
    """execution 关联的审计摘要。"""

    audit_required: bool
    audit_event_count: int
    degraded_mode: bool
    audit_status: str
    last_event: str | None = None

    def to_dict(self) -> JsonDict:
        """返回审计摘要序列化结构。"""

        return {
            "audit_required": self.audit_required,
            "audit_event_count": self.audit_event_count,
            "degraded_mode": self.degraded_mode,
            "audit_status": self.audit_status,
            "last_event": self.last_event,
        }


@dataclass(frozen=True)
class DecisionExecutionEnvelope:
    """Velaris 对外统一返回的 execution 包络。"""

    execution: BizExecutionRecord
    plan: JsonDict
    routing: JsonDict
    authority: JsonDict
    gate_decision: GovernanceGateDecision
    tasks: list[JsonDict] = field(default_factory=list)
    outcome: JsonDict | None = None
    result: JsonDict = field(default_factory=dict)
    audit: AuditSummary = field(
        default_factory=lambda: AuditSummary(
            audit_required=False,
            audit_event_count=0,
            degraded_mode=False,
            audit_status="not_required",
            last_event=None,
        )
    )

    def to_dict(self) -> JsonDict:
        """返回 envelope 主 contract。"""

        return {
            "execution": self.execution.to_dict(),
            "plan": dict(self.plan),
            "routing": dict(self.routing),
            "authority": dict(self.authority),
            "gate_decision": self.gate_decision.to_dict(),
            "tasks": [dict(item) for item in self.tasks],
            "outcome": None if self.outcome is None else dict(self.outcome),
            "result": dict(self.result),
            "audit": self.audit.to_dict(),
        }

    def to_tool_payload(self) -> JsonDict:
        """返回 envelope-first 的工具输出，并补最小兼容 alias。"""

        envelope = self.to_dict()
        return {
            "envelope": envelope,
            "session_id": self.execution.session_id,
            "result": dict(self.result),
            "outcome": None if self.outcome is None else dict(self.outcome),
            "audit_event_count": self.audit.audit_event_count,
        }
