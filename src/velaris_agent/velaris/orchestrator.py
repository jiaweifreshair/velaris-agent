"""Velaris 原生业务编排器。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from velaris_agent.biz.engine import build_capability_plan, run_scenario
from velaris_agent.memory.types import StakeholderMapModel
from velaris_agent.persistence.factory import (
    build_audit_store,
    build_execution_repository,
    build_openviking_context,
    build_outcome_store,
    build_session_repository,
    build_task_ledger,
)
from velaris_agent.velaris.authority import AuthorityService
from velaris_agent.velaris.execution_contract import (
    AuditSummary,
    BizExecutionRecord,
    DecisionExecutionEnvelope,
    DecisionExecutionRequest,
    GovernanceGateDecision,
)
from velaris_agent.velaris.failure_classifier import PersistenceFailureClassifier
from velaris_agent.velaris.outcome_store import OutcomeStore
from velaris_agent.velaris.persistence_barrier import (
    PreExecutionPersistenceBarrier,
    PreExecutionPersistenceError,
)
from velaris_agent.velaris.cost_tracker import DecisionCostTracker
from velaris_agent.velaris.dynamic_router import DynamicRouter, RoutingContext
from velaris_agent.velaris.router import PolicyRouter
from velaris_agent.velaris.task_ledger import TaskLedger


class AuditStore(Protocol):
    """编排器可接受的最小审计仓储协议。

    这里仅约束编排器真正需要的 append 能力，
    让 SQLite 仓储与未来其他实现都能以最小成本接入。
    """

    def append_event(
        self,
        session_id: str,
        step_name: str,
        operator_id: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        """追加一条审计事件。"""


class VelarisBizOrchestrator:
    """Velaris 业务场景编排器。"""

    def __init__(
        self,
        router: PolicyRouter | None = None,
        authority_service: AuthorityService | None = None,
        task_ledger: TaskLedger | None = None,
        outcome_store: OutcomeStore | None = None,
        audit_store: AuditStore | None = None,
        session_repository: Any | None = None,
        execution_repository: Any | None = None,
        persistence_barrier: PreExecutionPersistenceBarrier | None = None,
        failure_classifier: PersistenceFailureClassifier | None = None,
        openviking_context: Any | None = None,
        dynamic_router: DynamicRouter | None = None,
        cost_tracker: DecisionCostTracker | None = None,
        evolution_loop: Any | None = None,
        cwd: str | Path | None = None,
        sqlite_database_path: str | Path | None = None,
    ) -> None:
        """初始化编排器及其依赖。"""
        resolved_cwd = Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()
        # 统一将 cwd 作为编排器的运行语义输入，而不是由桥接层或调用方随意推导。
        self.cwd = resolved_cwd
        if sqlite_database_path is not None and str(sqlite_database_path).strip():
            resolved_sqlite_path = str(sqlite_database_path)
        else:
            from velaris_agent.persistence.sqlite_helpers import get_project_database_path

            resolved_sqlite_path = str(get_project_database_path(resolved_cwd))
        self.router = router or PolicyRouter()
        self.authority_service = authority_service or AuthorityService()
        self.task_ledger = task_ledger or build_task_ledger(sqlite_database_path=resolved_sqlite_path)
        self.outcome_store = outcome_store or build_outcome_store(sqlite_database_path=resolved_sqlite_path)
        self.audit_store = (
            audit_store
            if audit_store is not None
            else build_audit_store(sqlite_database_path=resolved_sqlite_path)
        )
        self.session_repository = (
            session_repository
            if session_repository is not None
            else build_session_repository(sqlite_database_path=resolved_sqlite_path)
        )
        self.execution_repository = (
            execution_repository
            if execution_repository is not None
            else build_execution_repository(sqlite_database_path=resolved_sqlite_path)
        )
        self.failure_classifier = failure_classifier or PersistenceFailureClassifier()
        self.persistence_barrier = persistence_barrier
        if self.persistence_barrier is None and self.execution_repository is not None:
            self.persistence_barrier = PreExecutionPersistenceBarrier(
                session_repository=self.session_repository,
                execution_repository=self.execution_repository,
                audit_store=self.audit_store,
                failure_classifier=self.failure_classifier,
            )
        # OpenViking 上下文管理器（可选增强，不影响现有 SQLite 主线）
        self.openviking_context = openviking_context
        # DynamicRouter 动态路由器（可选增强，不提供时使用 PolicyRouter）
        self.dynamic_router = dynamic_router
        # DecisionCostTracker 决策成本追踪器（可选增强）
        self.cost_tracker = cost_tracker
        # SkillEvolutionLoop 自进化循环（可选增强）
        self.evolution_loop = evolution_loop

    def execute_request(self, request: DecisionExecutionRequest) -> dict[str, Any]:
        """标准化 request 入口：OpenHarness 只负责提交请求并接收统一执行包络。"""

        return self.execute(
            query=request.query,
            payload=dict(request.payload),
            constraints=dict(request.constraints),
            scenario=request.scenario_hint,
            session_id=request.session_id,
        )

    def execute(
        self,
        query: str,
        payload: dict[str, Any],
        constraints: dict[str, Any] | None = None,
        scenario: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """执行一次完整的 Velaris 业务闭环。"""
        normalized_session_id = session_id.strip() if session_id and session_id.strip() else None
        resolved_session_id = normalized_session_id or f"session-{uuid4().hex[:12]}"
        request = DecisionExecutionRequest(
            query=query,
            payload=payload,
            constraints=constraints or {},
            scenario_hint=scenario,
            session_id=resolved_session_id,
        )
        stakeholder_map = _resolve_stakeholder_map(payload)
        plan = build_capability_plan(
            query=query,
            constraints=dict(request.constraints),
            scenario=scenario,
            stakeholder_map=stakeholder_map,
        )
        scenario_payload = dict(payload)
        if "stakeholder_context" in plan:
            scenario_payload["stakeholder_context"] = plan["stakeholder_context"]
        if "decision_weights" not in scenario_payload and "decision_weights" in plan:
            scenario_payload["decision_weights"] = plan["decision_weights"]
        routing = self.router.route(plan=plan, query=query)

        # DynamicRouter 增强路由（可选，提供 cost/SLA/compliance 感知）
        dynamic_decision = None
        if self.dynamic_router is not None:
            routing_context = self._build_routing_context(
                plan=plan, payload=payload, constraints=constraints or {},
            )
            # routing_context 为 None 表示无动态上下文，保持向后兼容
            dynamic_decision = self.dynamic_router.route(
                plan=plan, query=query, context=routing_context,
            )

        authority = self.authority_service.issue_plan(
            required_capabilities=routing.required_capabilities,
            governance=plan["governance"],
        )
        gate_decision = self._build_gate_decision(plan=plan, routing=routing.to_dict(), authority=authority.to_dict())
        execution = self._build_execution_record(
            session_id=resolved_session_id,
            scenario=str(plan["scenario"]),
            gate_decision=gate_decision,
        )

        if gate_decision.gate_status == "denied":
            audit_event_count = 0
            try:
                audit_event_count += self._append_audit_event(
                    session_id=resolved_session_id,
                    step_name="orchestrator.blocked",
                    payload={
                        "execution_id": execution.execution_id,
                        "scenario": plan["scenario"],
                        "selected_strategy": routing.selected_strategy,
                        "reason": gate_decision.reason,
                    },
                    required=gate_decision.requires_forced_audit,
                )
            except RuntimeError as exc:
                failure_payload = self._build_envelope(
                    execution=self._replace_execution(
                        execution,
                        execution_status="blocked",
                        audit_status="failed",
                        resume_cursor={"stage": "blocked"},
                    ),
                    plan=plan,
                    routing=routing.to_dict(),
                    authority=authority.to_dict(),
                    gate_decision=gate_decision,
                    tasks=[],
                    outcome={
                        "success": False,
                        "summary": str(exc),
                        "reason_codes": ["gate_denied"],
                    },
                    result={},
                    audit_summary=AuditSummary(
                        audit_required=gate_decision.requires_forced_audit,
                        audit_event_count=0,
                        degraded_mode=gate_decision.degraded_mode,
                        audit_status="failed",
                        last_event=None,
                    ),
                )
                raise RuntimeError(failure_payload) from exc

            return self._build_envelope(
                execution=self._replace_execution(
                    execution,
                    execution_status="blocked",
                    audit_status="persisted" if audit_event_count else "not_required",
                    resume_cursor={"stage": "blocked"},
                ),
                plan=plan,
                routing=routing.to_dict(),
                authority=authority.to_dict(),
                gate_decision=gate_decision,
                tasks=[],
                outcome={
                    "success": False,
                    "summary": gate_decision.reason,
                    "reason_codes": ["gate_denied"],
                },
                result={},
                audit_summary=AuditSummary(
                    audit_required=gate_decision.requires_forced_audit,
                    audit_event_count=audit_event_count,
                    degraded_mode=gate_decision.degraded_mode,
                    audit_status="persisted" if audit_event_count else "not_required",
                    last_event="orchestrator.blocked" if audit_event_count else None,
                ),
            )

        audit_event_count = 0
        if self.persistence_barrier is not None:
            try:
                barrier_result = self.persistence_barrier.persist(
                    request=request,
                    execution=execution,
                    gate_decision=gate_decision,
                    session_snapshot={"cwd": str(self.cwd), "query": query},
                    execution_snapshot={
                        "plan": plan,
                        "routing": routing.to_dict(),
                        "authority": authority.to_dict(),
                        "gate_decision": gate_decision.to_dict(),
                    },
                )
            except PreExecutionPersistenceError as exc:
                failure_payload = self._build_envelope(
                    execution=self._replace_execution(
                        execution,
                        execution_status="blocked",
                        audit_status="failed",
                        resume_cursor={"stage": "blocked"},
                    ),
                    plan=plan,
                    routing=routing.to_dict(),
                    authority=authority.to_dict(),
                    gate_decision=gate_decision,
                    tasks=[],
                    outcome={
                        "success": False,
                        "summary": exc.classification.message,
                        "reason_codes": [exc.classification.error_code],
                    },
                    result={"error": exc.to_dict()},
                    audit_summary=AuditSummary(
                        audit_required=gate_decision.requires_forced_audit,
                        audit_event_count=0,
                        degraded_mode=gate_decision.degraded_mode,
                        audit_status="failed",
                        last_event=None,
                    ),
                )
                raise RuntimeError(failure_payload) from exc
            execution = barrier_result.execution_record
            audit_event_count += barrier_result.audit_event_count

        # OpenViking 增强快照持久化（可选，不影响 SQLite 主线）
        self._persist_snapshot_to_viking(
            execution_id=execution.execution_id,
            snapshot={
                "plan": plan,
                "routing": routing.to_dict(),
                "authority": authority.to_dict(),
                "gate_decision": gate_decision.to_dict(),
                "session_id": resolved_session_id,
                "cwd": str(self.cwd),
                "query": query,
            },
        )

        task = self.task_ledger.create_task(
            session_id=resolved_session_id,
            runtime=routing.selected_route.runtime,
            role="biz_executor",
            objective=query,
        )
        self.task_ledger.update_status(task.task_id, "running")

        try:
            audit_event_count += self._append_audit_event(
                session_id=resolved_session_id,
                step_name="orchestrator.routed",
                payload={
                    "task_id": task.task_id,
                    "execution_id": execution.execution_id,
                    "scenario": plan["scenario"],
                    "selected_strategy": routing.selected_strategy,
                    "runtime": routing.selected_route.runtime,
                    "approvals_required": authority.approvals_required,
                },
                required=False,
            )
            scenario_result = run_scenario(plan["scenario"], scenario_payload)

            # DecisionCostTracker 记录成功执行的成本（可选增强）
            self._track_execution_cost(
                execution_id=execution.execution_id,
                scenario=str(plan["scenario"]),
                model_tier=dynamic_decision.model_tier.value if dynamic_decision else "standard",
            )

            # SkillEvolutionLoop 收集执行反馈（可选增强）
            self._collect_evolution_feedback(
                execution_id=execution.execution_id,
                scenario=str(plan["scenario"]),
                result=scenario_result,
                model_tier=dynamic_decision.model_tier.value if dynamic_decision else "standard",
            )

            audit_event_count += self._append_audit_event(
                session_id=resolved_session_id,
                step_name="orchestrator.completed",
                payload={
                    "task_id": task.task_id,
                    "execution_id": execution.execution_id,
                    "scenario": plan["scenario"],
                    "selected_strategy": routing.selected_strategy,
                    "success": True,
                    "summary": str(scenario_result.get("summary", "执行完成")),
                    "operator_trace_summary": [
                        {
                            "operator_id": item.get("operator_id"),
                            "operator_version": item.get("operator_version"),
                            "confidence": item.get("confidence"),
                        }
                        for item in scenario_result.get("operator_trace", [])
                    ],
                },
                required=False,
            )
        except Exception as exc:
            failed_task = self.task_ledger.update_status(task.task_id, "failed", error=str(exc))
            outcome = self.outcome_store.record(
                session_id=resolved_session_id,
                scenario=plan["scenario"],
                selected_strategy=routing.selected_strategy,
                success=False,
                reason_codes=routing.reason_codes,
                summary=str(exc),
                metrics={"error": str(exc)},
            )
            audit_event_count += self._append_audit_event(
                session_id=resolved_session_id,
                step_name="orchestrator.failed",
                payload={
                    "task_id": task.task_id,
                    "scenario": plan["scenario"],
                    "selected_strategy": routing.selected_strategy,
                    "error": str(exc),
                },
                required=False,
            )
            failure_execution = self._replace_execution(
                execution,
                execution_status="failed",
                audit_status=self._finalize_audit_status(
                    gate_decision=gate_decision,
                    audit_event_count=audit_event_count,
                ),
                resume_cursor={"stage": "failed"},
            )
            if self.execution_repository is not None:
                self.execution_repository.update_status(
                    failure_execution.execution_id,
                    execution_status=failure_execution.execution_status,
                    gate_status=failure_execution.gate_status,
                    effective_risk_level=failure_execution.effective_risk_level,
                    degraded_mode=failure_execution.degraded_mode,
                    audit_status=failure_execution.audit_status,
                    structural_complete=failure_execution.structural_complete,
                    constraint_complete=failure_execution.constraint_complete,
                    goal_complete=failure_execution.goal_complete,
                    resume_cursor=failure_execution.resume_cursor,
                    snapshot_json={
                        "plan": plan,
                        "routing": routing.to_dict(),
                        "authority": authority.to_dict(),
                        "gate_decision": gate_decision.to_dict(),
                        "task_id": task.task_id,
                        "outcome": outcome.to_dict(),
                    },
                    updated_at=failure_execution.updated_at,
                )
            raise RuntimeError(
                self._build_envelope(
                    execution=failure_execution,
                    plan=plan,
                    routing=routing.to_dict(),
                    authority=authority.to_dict(),
                    gate_decision=gate_decision,
                    tasks=[failed_task.to_dict() if failed_task is not None else task.to_dict()],
                    outcome=outcome.to_dict(),
                    result={},
                    audit_summary=AuditSummary(
                        audit_required=gate_decision.requires_forced_audit,
                        audit_event_count=audit_event_count,
                        degraded_mode=gate_decision.degraded_mode,
                        audit_status=failure_execution.audit_status,
                        last_event="orchestrator.failed",
                    ),
                )
            ) from exc

        completed_task = self.task_ledger.update_status(task.task_id, "completed") or task
        outcome = self.outcome_store.record(
            session_id=resolved_session_id,
            scenario=plan["scenario"],
            selected_strategy=routing.selected_strategy,
            success=True,
            reason_codes=routing.reason_codes,
            summary=str(scenario_result.get("summary", "执行完成")),
            metrics={
                "recommended_id": (scenario_result.get("recommended", {}) or {}).get("id"),
                "feasible": scenario_result.get("feasible"),
                "contract_ready": scenario_result.get("contract_ready"),
            },
        )
        final_execution_status = self._final_execution_status(gate_decision=gate_decision)
        completed_execution = self._replace_execution(
            execution,
            execution_status=final_execution_status,
            structural_complete=True,
            constraint_complete=gate_decision.gate_status == "allowed",
            goal_complete=gate_decision.gate_status == "allowed",
            audit_status=self._finalize_audit_status(
                gate_decision=gate_decision,
                audit_event_count=audit_event_count,
            ),
            resume_cursor={"stage": final_execution_status},
        )
        if self.execution_repository is not None:
            self.execution_repository.update_status(
                completed_execution.execution_id,
                execution_status=completed_execution.execution_status,
                gate_status=completed_execution.gate_status,
                effective_risk_level=completed_execution.effective_risk_level,
                degraded_mode=completed_execution.degraded_mode,
                audit_status=completed_execution.audit_status,
                structural_complete=completed_execution.structural_complete,
                constraint_complete=completed_execution.constraint_complete,
                goal_complete=completed_execution.goal_complete,
                resume_cursor=completed_execution.resume_cursor,
                snapshot_json={
                    "plan": plan,
                    "routing": routing.to_dict(),
                    "authority": authority.to_dict(),
                    "gate_decision": gate_decision.to_dict(),
                    "task_id": completed_task.task_id,
                    "result": scenario_result,
                    "outcome": outcome.to_dict(),
                },
                updated_at=completed_execution.updated_at,
            )
        return self._build_envelope(
            execution=completed_execution,
            plan=plan,
            routing=routing.to_dict(),
            authority=authority.to_dict(),
            gate_decision=gate_decision,
            tasks=[completed_task.to_dict()],
            outcome=outcome.to_dict(),
            result=scenario_result,
            audit_summary=AuditSummary(
                audit_required=gate_decision.requires_forced_audit,
                audit_event_count=audit_event_count,
                degraded_mode=gate_decision.degraded_mode,
                audit_status=completed_execution.audit_status,
                last_event="orchestrator.completed",
            ),
        )

    def _build_gate_decision(
        self,
        *,
        plan: dict[str, Any],
        routing: dict[str, Any],
        authority: dict[str, Any],
    ) -> GovernanceGateDecision:
        """根据 effective risk 生成治理门决策。"""

        effective_risk_level = self._resolve_effective_risk_level(
            plan=plan,
            routing=routing,
            authority=authority,
        )
        governance = dict(plan.get("governance", {}))
        if effective_risk_level == "high":
            return GovernanceGateDecision(
                gate_status="denied",
                effective_risk_level=effective_risk_level,
                requires_forced_audit=bool(governance.get("requires_audit", False) or authority.get("approvals_required", False)),
                degraded_mode=False,
                reason="scenario profile marked request as high risk",
            )
        if effective_risk_level == "medium":
            return GovernanceGateDecision(
                gate_status="degraded",
                effective_risk_level=effective_risk_level,
                requires_forced_audit=True,
                degraded_mode=True,
                reason="scenario profile requires audited degraded execution",
            )
        return GovernanceGateDecision(
            gate_status="allowed",
            effective_risk_level=effective_risk_level,
            requires_forced_audit=bool(governance.get("requires_audit", False)),
            degraded_mode=False,
            reason="safe to proceed",
        )

    def _resolve_effective_risk_level(
        self,
        *,
        plan: dict[str, Any],
        routing: dict[str, Any],
        authority: dict[str, Any],
    ) -> str:
        """根据 scenario profile 计算 execution 的 effective risk。

        routing 提供的是基础风险信号，但不是最终真相源。
        这里优先消费显式风险约束，其次从 ScenarioRegistry 读取场景风险等级，
        最后才回退到 routing 原始风险，避免"强审计 = 高风险"被错误硬编码。
        """

        del authority
        constraints = dict(plan.get("constraints", {}))
        explicit_risk_level = self._extract_explicit_risk_level(constraints)
        if explicit_risk_level is not None:
            return explicit_risk_level

        # 从 ScenarioRegistry 读取场景风险等级（替代硬编码字典）
        # 只要场景在注册表中注册，就直接使用其 risk_level，不再回退到 routing
        scenario = str(plan.get("scenario", "general") or "general")
        from velaris_agent.biz.engine import get_scenario_registry
        registry = get_scenario_registry()
        spec = registry.get(scenario)
        if spec is not None:
            return spec.risk_level

        base_risk_level = (
            routing.get("trace", {})
            .get("routing_context", {})
            .get("risk", {})
            .get("level", "medium")
        )
        return self._normalize_risk_level(base_risk_level)

    def _extract_explicit_risk_level(self, constraints: dict[str, Any]) -> str | None:
        """从显式约束中提取风险级别，并统一归一化。"""

        risk_level = constraints.get("risk_level")
        if risk_level is None:
            nested_risk = constraints.get("risk")
            if isinstance(nested_risk, dict):
                risk_level = nested_risk.get("level")
        if risk_level is None:
            return None
        return self._normalize_risk_level(risk_level)

    def _normalize_risk_level(self, risk_level: Any) -> str:
        """把外部风险输入收敛到 gate 能消费的 low/medium/high 三档。"""

        normalized = str(risk_level or "medium").strip().lower()
        if normalized in {"critical", "high"}:
            return "high"
        if normalized == "low":
            return "low"
        return "medium"

    def _build_execution_record(
        self,
        *,
        session_id: str,
        scenario: str,
        gate_decision: GovernanceGateDecision,
    ) -> BizExecutionRecord:
        """创建 execution 主记录的初始快照。"""

        timestamp = datetime.now(UTC).isoformat()
        return BizExecutionRecord(
            execution_id=f"exec-{uuid4().hex[:12]}",
            session_id=session_id,
            scenario=scenario,
            execution_status="blocked" if gate_decision.gate_status == "denied" else "planned",
            gate_status=gate_decision.gate_status,
            effective_risk_level=gate_decision.effective_risk_level,
            degraded_mode=gate_decision.degraded_mode,
            audit_status="not_required",
            structural_complete=False,
            constraint_complete=False,
            goal_complete=False,
            created_at=timestamp,
            updated_at=timestamp,
            resume_cursor={"stage": "planned"},
        )

    def _replace_execution(
        self,
        execution: BizExecutionRecord,
        *,
        execution_status: str,
        audit_status: str,
        structural_complete: bool | None = None,
        constraint_complete: bool | None = None,
        goal_complete: bool | None = None,
        resume_cursor: dict[str, Any] | None = None,
    ) -> BizExecutionRecord:
        """返回更新后的 execution 快照，避免原对象被原地修改。"""

        return BizExecutionRecord(
            execution_id=execution.execution_id,
            session_id=execution.session_id,
            scenario=execution.scenario,
            execution_status=execution_status,
            gate_status=execution.gate_status,
            effective_risk_level=execution.effective_risk_level,
            degraded_mode=execution.degraded_mode,
            audit_status=audit_status,
            structural_complete=execution.structural_complete if structural_complete is None else structural_complete,
            constraint_complete=execution.constraint_complete if constraint_complete is None else constraint_complete,
            goal_complete=execution.goal_complete if goal_complete is None else goal_complete,
            created_at=execution.created_at,
            updated_at=datetime.now(UTC).isoformat(),
            resume_cursor=dict(execution.resume_cursor or {}) if resume_cursor is None else dict(resume_cursor),
        )

    def _final_execution_status(self, gate_decision: GovernanceGateDecision) -> str:
        """根据 gate 结果映射最终 execution_status。"""

        if gate_decision.gate_status == "degraded":
            return "partially_completed"
        return "completed"

    def _finalize_audit_status(
        self,
        *,
        gate_decision: GovernanceGateDecision,
        audit_event_count: int,
    ) -> str:
        """根据 gate 与审计写入结果收束 audit_status。"""

        if gate_decision.gate_status == "degraded":
            if self.audit_store is None:
                return "pending"
            return "persisted" if audit_event_count > 0 else "failed"
        if gate_decision.requires_forced_audit:
            return "persisted" if audit_event_count > 0 else "failed"
        return "not_required"

    def _build_envelope(
        self,
        *,
        execution: BizExecutionRecord,
        plan: dict[str, Any],
        routing: dict[str, Any],
        authority: dict[str, Any],
        gate_decision: GovernanceGateDecision,
        tasks: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
        result: dict[str, Any],
        audit_summary: AuditSummary,
    ) -> dict[str, Any]:
        """组装统一 envelope-first 输出并补最小兼容 alias。"""

        envelope = DecisionExecutionEnvelope(
            execution=execution,
            plan=plan,
            routing=routing,
            authority=authority,
            gate_decision=gate_decision,
            tasks=tasks,
            outcome=outcome,
            result=result,
            audit=audit_summary,
        )
        return envelope.to_tool_payload()

    def _append_audit_event(
        self,
        session_id: str,
        step_name: str,
        payload: dict[str, Any] | None = None,
        required: bool = False,
    ) -> int:
        """在配置了审计仓储时追加事件，并返回本次新增数量。

        这样主流程只需要累加返回值，就能在保持旧调用兼容的同时返回审计计数。
        """

        if self.audit_store is None:
            if required:
                raise RuntimeError(
                    f"audit trail required but unavailable for step '{step_name}'"
                )
            return 0
        try:
            self.audit_store.append_event(
                session_id=session_id,
                step_name=step_name,
                operator_id=self.__class__.__name__,
                payload=payload or {},
            )
        except Exception as exc:
            # 审计链路是可选增强能力，不能反向污染主业务的成功/失败语义。
            if required:
                raise RuntimeError(
                    f"audit trail required but unavailable for step '{step_name}'"
                ) from exc
            return 0
        return 1

    def _persist_snapshot_to_viking(
        self,
        execution_id: str,
        snapshot: dict[str, Any],
    ) -> str | None:
        """将执行快照持久化到 OpenViking（可选增强）。

        此方法不会影响主流程——即使 OpenViking 未配置或写入失败，
        也不会抛出异常或改变执行语义。返回 viking:// URI 或 None。

        Args:
            execution_id: 执行 ID
            snapshot: 快照数据

        Returns:
            viking:// URI 字符串，未配置时返回 None
        """
        if self.openviking_context is None:
            return None

        try:
            return self.openviking_context.save_snapshot(
                execution_id=execution_id,
                snapshot=snapshot,
            )
        except Exception as exc:
            # OpenViking 是增强能力，不能反向污染主业务
            import logging
            logging.getLogger(__name__).warning(
                f"OpenViking 快照持久化失败 (execution_id={execution_id}): {exc}"
            )
            return None

    def _track_execution_cost(
        self,
        execution_id: str,
        scenario: str,
        model_tier: str = "standard",
        token_input: int = 0,
        token_output: int = 0,
        latency_ms: float = 0.0,
    ) -> None:
        """记录执行成本到 DecisionCostTracker（可选增强）。

        此方法不会影响主流程——即使 CostTracker 未配置，
        也不会抛出异常或改变执行语义。

        Args:
            execution_id: 执行 ID
            scenario: 场景名
            model_tier: 模型等级
            token_input: 输入 token 数（估算）
            token_output: 输出 token 数（估算）
            latency_ms: 执行延迟（毫秒）
        """
        if self.cost_tracker is None:
            return

        try:
            self.cost_tracker.track(
                execution_id=execution_id,
                scenario=scenario,
                model_tier=model_tier,
                token_input=token_input,
                token_output=token_output,
                latency_ms=latency_ms,
            )
        except Exception:
            # CostTracker 是增强能力，不能反向污染主业务
            pass

    def _build_routing_context(
        self,
        plan: dict[str, Any],
        payload: dict[str, Any],
        constraints: dict[str, Any],
    ) -> RoutingContext:
        """从请求上下文构建 DynamicRouter 所需的 RoutingContext。

        提取 token_budget / SLA / compliance 三维信息，
        让 DynamicRouter 的四层路由（Base→Cost→SLA→Compliance）全部生效。
        """
        from velaris_agent.velaris.dynamic_router import (
            ComplianceContext,
            ComplianceRegion,
            SLARequirement,
            TokenBudget,
        )

        # 1. TokenBudget：从 payload 或 constraints 中提取
        token_budget = None
        budget_raw = constraints.get("token_budget") or payload.get("token_budget")
        if budget_raw is not None:
            try:
                total = float(budget_raw) if not isinstance(budget_raw, dict) else float(budget_raw.get("total", 0))
                consumed = float(constraints.get("token_consumed", 0))
                token_budget = TokenBudget(
                    remaining=max(0.0, total - consumed),
                    total=total,
                    cost_rate=float(constraints.get("token_cost_rate", 1.0)),
                )
            except (TypeError, ValueError):
                pass

        # 2. SLARequirement：从 constraints 或 governance 中提取
        sla = None
        max_latency = constraints.get("max_latency_ms") or plan.get("governance", {}).get("max_latency_ms")
        min_quality = constraints.get("min_quality_score") or plan.get("governance", {}).get("min_quality_score")
        if max_latency is not None or min_quality is not None:
            sla = SLARequirement(
                max_latency_ms=float(max_latency) if max_latency is not None else None,
                min_quality_score=float(min_quality) if min_quality is not None else None,
            )

        # 3. ComplianceContext：从 constraints 中提取
        compliance = None
        compliance_raw = constraints.get("compliance") or payload.get("compliance")
        if compliance_raw is not None:
            if isinstance(compliance_raw, dict):
                region_str = str(compliance_raw.get("region", "global")).lower()
                data_classification = str(compliance_raw.get("data_classification", "internal"))
                requires_local = bool(compliance_raw.get("requires_local_inference", False))
            else:
                region_str = str(compliance_raw).lower()
                data_classification = str(constraints.get("data_classification", "internal"))
                requires_local = bool(constraints.get("requires_local_inference", False))

            try:
                region = ComplianceRegion(region_str)
            except ValueError:
                region = ComplianceRegion.GLOBAL
            compliance = ComplianceContext(
                region=region,
                data_classification=data_classification,
                requires_local_inference=requires_local,
            )

        # 4. historical_cost_tokens：从 CostTracker 获取（如有）
        historical_cost = 0.0
        if self.cost_tracker is not None:
            try:
                scenario = str(plan.get("scenario", "general"))
                roi = self.cost_tracker.roi(scenario=scenario)
                if roi.total_executions > 0:
                    historical_cost = roi.avg_token_per_execution
            except Exception:
                pass

        # 无任何动态上下文时返回 None，保持与 context=None 相同的向后兼容行为
        if token_budget is None and sla is None and compliance is None:
            return None

        return RoutingContext(
            token_budget=token_budget,
            sla=sla,
            compliance=compliance,
            scenario=str(plan.get("scenario", "general")),
            historical_cost_tokens=historical_cost,
        )

    def _collect_evolution_feedback(
        self,
        execution_id: str,
        scenario: str,
        result: dict[str, Any],
        model_tier: str = "standard",
    ) -> None:
        """收集执行反馈到 SkillEvolutionLoop（可选增强）。

        此方法不会影响主流程——即使 EvolutionLoop 未配置，
        也不会抛出异常或改变执行语义。

        从执行结果中提取质量评分、成本等信息，供自进化循环使用。
        """
        if self.evolution_loop is None:
            return

        try:
            # 从 result 中估算质量分
            quality_score = 0.7  # 默认中等质量
            recommended = result.get("recommended")
            if recommended and isinstance(recommended, dict):
                # 有推荐结果 → 质量偏高
                total_score = recommended.get("total_score")
                if total_score is not None:
                    quality_score = max(0.0, min(1.0, float(total_score)))

            # 从 result 中估算 token 成本
            token_cost = 0.0
            if self.cost_tracker is not None:
                try:
                    roi = self.cost_tracker.roi(scenario=scenario)
                    if roi.total_executions > 0:
                        token_cost = roi.total_cost_estimate / roi.total_executions
                except Exception:
                    pass

            self.evolution_loop.collect_feedback(
                execution_id=execution_id,
                scenario=scenario,
                quality_score=quality_score,
                token_cost=token_cost,
                model_tier=model_tier,
                metadata={"result_scenario": scenario},
            )
        except Exception:
            # EvolutionLoop 是增强能力，不能反向污染主业务
            pass


def _resolve_stakeholder_map(
    payload: dict[str, Any],
) -> StakeholderMapModel | None:
    """从编排 payload 中解析 stakeholder_map，保持旧调用兼容。"""

    raw_map = payload.get("stakeholder_map")
    if raw_map is None:
        return None
    if isinstance(raw_map, StakeholderMapModel):
        return raw_map
    return StakeholderMapModel.model_validate(raw_map)
