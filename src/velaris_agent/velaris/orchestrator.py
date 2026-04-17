"""Velaris 原生业务编排器。"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from velaris_agent.biz.engine import build_capability_plan, run_scenario
from velaris_agent.memory.types import StakeholderMapModel
from velaris_agent.velaris.authority import AuthorityService
from velaris_agent.velaris.outcome_store import OutcomeStore
from velaris_agent.velaris.router import PolicyRouter
from velaris_agent.velaris.task_ledger import TaskLedger


class AuditStore(Protocol):
    """编排器可接受的最小审计仓储协议。

    这里仅约束编排器真正需要的 append 能力，
    让 PostgreSQL 仓储与未来其他实现都能以最小成本接入。
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
    ) -> None:
        """初始化编排器及其依赖。"""
        self.router = router or PolicyRouter()
        self.authority_service = authority_service or AuthorityService()
        self.task_ledger = task_ledger or TaskLedger()
        self.outcome_store = outcome_store or OutcomeStore()
        self.audit_store = audit_store

    def execute(
        self,
        query: str,
        payload: dict[str, Any],
        constraints: dict[str, Any] | None = None,
        scenario: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """执行一次完整的 Velaris 业务闭环。"""
        resolved_session_id = session_id or f"session-{uuid4().hex[:12]}"
        audit_event_count = 0
        stakeholder_map = _resolve_stakeholder_map(payload)
        plan = build_capability_plan(
            query=query,
            constraints=constraints,
            scenario=scenario,
            stakeholder_map=stakeholder_map,
        )
        scenario_payload = dict(payload)
        if "stakeholder_context" in plan:
            scenario_payload["stakeholder_context"] = plan["stakeholder_context"]
        if "decision_weights" not in scenario_payload and "decision_weights" in plan:
            scenario_payload["decision_weights"] = plan["decision_weights"]
        audit_required = bool(plan.get("governance", {}).get("requires_audit", False))
        routing = self.router.route(plan=plan, query=query)
        authority = self.authority_service.issue_plan(
            required_capabilities=routing.required_capabilities,
            governance=plan["governance"],
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
                    "scenario": plan["scenario"],
                    "selected_strategy": routing.selected_strategy,
                    "runtime": routing.selected_route.runtime,
                    "approvals_required": authority.approvals_required,
                },
                required=audit_required,
            )
            scenario_result = run_scenario(plan["scenario"], scenario_payload)
            audit_event_count += self._append_audit_event(
                session_id=resolved_session_id,
                step_name="orchestrator.completed",
                payload={
                    "task_id": task.task_id,
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
                required=audit_required,
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
            raise RuntimeError(
                {
                    "session_id": resolved_session_id,
                    "plan": plan,
                    "routing": routing.to_dict(),
                    "authority": authority.to_dict(),
                    "task": failed_task.to_dict() if failed_task is not None else task.to_dict(),
                    "outcome": outcome.to_dict(),
                    "audit_event_count": audit_event_count,
                }
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
        return {
            "session_id": resolved_session_id,
            "plan": plan,
            "routing": routing.to_dict(),
            "authority": authority.to_dict(),
            "task": completed_task.to_dict(),
            "outcome": outcome.to_dict(),
            "result": scenario_result,
            "audit_event_count": audit_event_count,
        }

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
