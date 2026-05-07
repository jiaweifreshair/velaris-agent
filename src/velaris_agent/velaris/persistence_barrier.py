"""Pre-execution persistence barrier 实现。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone, datetime
from typing import Any, Protocol

from velaris_agent.persistence.sqlite_execution import SessionRecord
from velaris_agent.velaris.execution_contract import (
    BizExecutionRecord,
    DecisionExecutionRequest,
    GovernanceGateDecision,
)
from velaris_agent.velaris.failure_classifier import (
    FailureClassification,
    GateDeniedError,
    PersistenceFailureClassifier,
)
from velaris_agent.velaris.payload_redactor import PayloadRedactor


class SupportsSessionRepository(Protocol):
    """`PreExecutionPersistenceBarrier` 所需的最小 session 仓储协议。"""

    def upsert(self, record: SessionRecord) -> SessionRecord:
        """写入或覆盖 session 主记录。"""


class SupportsExecutionRepository(Protocol):
    """`PreExecutionPersistenceBarrier` 所需的最小 execution 仓储协议。"""

    def create(
        self,
        record: BizExecutionRecord,
        *,
        snapshot_json: dict[str, Any] | None = None,
    ) -> BizExecutionRecord:
        """创建 execution 主记录。"""


class SupportsAuditStore(Protocol):
    """屏障前置审计所需的最小审计仓储协议。"""

    def append_event(
        self,
        session_id: str,
        step_name: str,
        operator_id: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        """追加一条审计事件。"""


@dataclass(frozen=True)
class PreExecutionBarrierResult:
    """集中落库屏障成功后的返回结果。"""

    session_record: SessionRecord | None
    execution_record: BizExecutionRecord
    audit_event_count: int


class PreExecutionPersistenceError(RuntimeError):
    """表达屏障失败且必须 fail-closed 的标准化异常。"""

    def __init__(self, classification: FailureClassification) -> None:
        super().__init__(classification.message)
        self.classification = classification

    def to_dict(self) -> dict[str, str | bool]:
        """返回统一错误结构，便于后续 orchestrator / tool 层透传。"""

        return self.classification.to_dict()


class PreExecutionPersistenceBarrier:
    """进入真实 scenario 前的集中落库屏障。

    该组件先持久化 session / execution / 必要前置审计，
    只有屏障成功后，后续 orchestrator 才能真正放行 scenario 执行。
    """

    def __init__(
        self,
        *,
        session_repository: SupportsSessionRepository | None,
        execution_repository: SupportsExecutionRepository,
        audit_store: SupportsAuditStore | None = None,
        failure_classifier: PersistenceFailureClassifier | None = None,
        payload_redactor: PayloadRedactor | None = None,
    ) -> None:
        """绑定集中落库依赖，保持 orchestrator 主流程只做编排。"""

        self._session_repository = session_repository
        self._execution_repository = execution_repository
        self._audit_store = audit_store
        self._failure_classifier = failure_classifier or PersistenceFailureClassifier()
        self._payload_redactor = payload_redactor or PayloadRedactor()

    def persist(
        self,
        *,
        request: DecisionExecutionRequest,
        execution: BizExecutionRecord,
        gate_decision: GovernanceGateDecision,
        session_snapshot: dict[str, Any] | None = None,
        execution_snapshot: dict[str, Any] | None = None,
        source_runtime: str = "openharness",
    ) -> PreExecutionBarrierResult:
        """执行集中落库，并在失败时返回标准化 fail-closed 语义。"""

        if gate_decision.gate_status == "denied":
            classification = self._failure_classifier.classify(
                GateDeniedError(gate_decision.reason),
                stage="gate",
            )
            raise PreExecutionPersistenceError(classification)

        session_record = self._persist_session(
            request=request,
            source_runtime=source_runtime,
            session_snapshot=session_snapshot,
        )
        execution_record = self._seed_execution_record(
            execution=execution,
            gate_decision=gate_decision,
        )

        try:
            stored_execution = self._execution_repository.create(
                execution_record,
                snapshot_json=self._payload_redactor.redact_mapping(execution_snapshot or {}),
            )
        except Exception as exc:  # pragma: no cover - 由测试驱动覆盖主分支
            classification = self._failure_classifier.classify(exc, stage="execution_create")
            raise PreExecutionPersistenceError(classification) from exc

        audit_event_count = self._persist_required_audit(
            request=request,
            stored_execution=stored_execution,
            gate_decision=gate_decision,
        )

        return PreExecutionBarrierResult(
            session_record=session_record,
            execution_record=stored_execution,
            audit_event_count=audit_event_count,
        )

    def _persist_session(
        self,
        *,
        request: DecisionExecutionRequest,
        source_runtime: str,
        session_snapshot: dict[str, Any] | None,
    ) -> SessionRecord | None:
        """按需写入 session 主记录，避免 execution 先于 session 漂移。"""

        if request.session_id is None or self._session_repository is None:
            return None
        snapshot_json = self._payload_redactor.redact_mapping(session_snapshot or {})
        snapshot_json.setdefault("query", request.query)
        snapshot_json.setdefault("scenario_hint", request.scenario_hint)
        timestamp = _now_iso()
        try:
            return self._session_repository.upsert(
                SessionRecord(
                    session_id=request.session_id,
                    binding_mode="attached",
                    source_runtime=source_runtime,
                    summary=request.query[:80],
                    message_count=0,
                    created_at=timestamp,
                    updated_at=timestamp,
                    snapshot_json=snapshot_json,
                )
            )
        except Exception as exc:  # pragma: no cover - 由后续测试驱动覆盖
            classification = self._failure_classifier.classify(exc, stage="session_bind")
            raise PreExecutionPersistenceError(classification) from exc

    def _seed_execution_record(
        self,
        *,
        execution: BizExecutionRecord,
        gate_decision: GovernanceGateDecision,
    ) -> BizExecutionRecord:
        """根据 gate 决策推进 execution 的初始 audit_status。"""

        if gate_decision.gate_status == "degraded":
            audit_status = "pending"
        elif gate_decision.requires_forced_audit:
            audit_status = "persisted" if self._audit_store is not None else "failed"
        else:
            audit_status = execution.audit_status

        return BizExecutionRecord(
            execution_id=execution.execution_id,
            session_id=execution.session_id,
            scenario=execution.scenario,
            execution_status=execution.execution_status,
            gate_status=gate_decision.gate_status,
            effective_risk_level=gate_decision.effective_risk_level,
            degraded_mode=gate_decision.degraded_mode,
            audit_status=audit_status,
            structural_complete=execution.structural_complete,
            constraint_complete=execution.constraint_complete,
            goal_complete=execution.goal_complete,
            created_at=execution.created_at,
            updated_at=execution.updated_at,
            resume_cursor=execution.resume_cursor,
        )

    def _persist_required_audit(
        self,
        *,
        request: DecisionExecutionRequest,
        stored_execution: BizExecutionRecord,
        gate_decision: GovernanceGateDecision,
    ) -> int:
        """为需要同步前置审计的路径写入最小审计事件。"""

        requires_sync_audit = (
            gate_decision.requires_forced_audit
            and gate_decision.gate_status == "allowed"
            and gate_decision.effective_risk_level == "high"
        )
        if not requires_sync_audit:
            return 0
        if self._audit_store is None:
            classification = self._failure_classifier.classify(
                ConnectionError("audit store unavailable before execution"),
                stage="audit_persist",
            )
            raise PreExecutionPersistenceError(classification)
        try:
            self._audit_store.append_event(
                session_id=request.session_id or "detached-execution",
                step_name="persistence_barrier.pre_execution_audit",
                operator_id=self.__class__.__name__,
                payload={
                    "execution_id": stored_execution.execution_id,
                    "gate_status": gate_decision.gate_status,
                    "effective_risk_level": gate_decision.effective_risk_level,
                },
            )
        except Exception as exc:  # pragma: no cover - 由后续测试驱动覆盖
            classification = self._failure_classifier.classify(exc, stage="audit_persist")
            raise PreExecutionPersistenceError(classification) from exc
        return 1


def _now_iso() -> str:
    """生成 barrier 内部统一使用的 ISO 时间戳。"""

    return datetime.now(timezone.utc).isoformat()
