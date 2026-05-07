"""Velaris execution 审计修复服务。

该模块负责把 `audit_status=pending/failed` 的历史 execution
补写为“最小可恢复审计轨迹”，并把状态推进到 `persisted`。
"""

from __future__ import annotations

from datetime import timezone, datetime
from pathlib import Path
from typing import Any

from velaris_agent.persistence.factory import build_audit_store, build_execution_repository


def _ensure_mapping(value: Any) -> dict[str, Any]:
    """把任意对象尽量收敛为普通字典。"""

    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "items"):
        return dict(value)
    return {}


class ExecutionRepairService:
    """按 execution_id 修复审计状态的最小服务。"""

    def __init__(
        self,
        *,
        cwd: str | Path,
        sqlite_database_path: str | Path | None = None,
    ) -> None:
        """绑定 SQLite 仓储，确保 repair 始终在项目内单库上执行。"""

        resolved_cwd = Path(cwd).resolve()
        resolved_sqlite_path: str | None = str(sqlite_database_path) if sqlite_database_path is not None else None
        if resolved_sqlite_path is None or not str(resolved_sqlite_path).strip():
            from velaris_agent.persistence.sqlite_helpers import get_project_database_path

            resolved_sqlite_path = str(get_project_database_path(resolved_cwd))

        self.cwd = resolved_cwd
        self.sqlite_database_path = resolved_sqlite_path
        self.execution_repository = build_execution_repository(sqlite_database_path=resolved_sqlite_path)
        self.audit_store = build_audit_store(sqlite_database_path=resolved_sqlite_path)

        if self.execution_repository is None or self.audit_store is None:  # pragma: no cover
            raise RuntimeError("execution repair dependencies unavailable")

    def repair_execution(self, execution_id: str) -> dict[str, Any]:
        """补写最小审计并把 execution 审计状态推进到 persisted。"""

        execution = self.execution_repository.get(execution_id)
        if execution is None:
            raise RuntimeError(f"Execution not found: {execution_id}")

        audit_status_before = execution.audit_status
        if audit_status_before in {"persisted", "not_required"}:
            return {
                "execution_id": execution_id,
                "repaired": False,
                "audit_status_before": audit_status_before,
                "audit_status_after": audit_status_before,
                "events_appended": 0,
            }

        snapshot_json = self.execution_repository.get_snapshot_json(execution_id)
        session_id = execution.session_id or str(snapshot_json.get("session_id", "") or "detached-execution")
        existing_events = self._collect_execution_events(
            execution_id=execution_id,
            session_id=session_id,
        )
        existing_steps = {event.step_name for event in existing_events}

        backfill_events = self._build_backfill_events(
            execution_id=execution_id,
            session_id=session_id,
            execution=execution,
            snapshot_json=snapshot_json,
            existing_steps=existing_steps,
        )

        events_appended = 0
        for event in backfill_events:
            self.audit_store.append_event(
                session_id=session_id,
                step_name=str(event["step_name"]),
                operator_id=self.__class__.__name__,
                payload=_ensure_mapping(event.get("payload")),
            )
            events_appended += 1

        repair_snapshot = dict(snapshot_json)
        repair_snapshot["audit_repair"] = {
            "repaired_at": datetime.now(timezone.utc).isoformat(),
            "audit_status_before": audit_status_before,
            "events_appended": events_appended,
        }
        repaired = self.execution_repository.update_status(
            execution_id,
            execution_status=execution.execution_status,
            gate_status=execution.gate_status,
            effective_risk_level=execution.effective_risk_level,
            degraded_mode=execution.degraded_mode,
            audit_status="persisted",
            structural_complete=execution.structural_complete,
            constraint_complete=execution.constraint_complete,
            goal_complete=execution.goal_complete,
            resume_cursor=execution.resume_cursor,
            snapshot_json=repair_snapshot,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        if repaired is None:  # pragma: no cover
            raise RuntimeError(f"Execution disappeared during repair: {execution_id}")

        return {
            "execution_id": execution_id,
            "repaired": True,
            "audit_status_before": audit_status_before,
            "audit_status_after": repaired.audit_status,
            "events_appended": events_appended,
        }

    def _collect_execution_events(self, *, execution_id: str, session_id: str) -> list[Any]:
        """按 execution_id 收集已存在的审计事件。

        当一个 session 只有一个 execution 时，允许退回到 session 级事件，
        兼容旧事件缺失 `execution_id` 的历史记录。
        """

        session_events = self.audit_store.list_by_session(session_id)
        execution_events = [
            event
            for event in session_events
            if str((event.payload or {}).get("execution_id", "")) == execution_id
        ]
        if execution_events:
            return execution_events

        session_executions = self.execution_repository.list_by_session(session_id)
        if len(session_executions) == 1:
            return session_events
        return []

    def _build_backfill_events(
        self,
        *,
        execution_id: str,
        session_id: str,
        execution: Any,
        snapshot_json: dict[str, Any],
        existing_steps: set[str],
    ) -> list[dict[str, Any]]:
        """按 execution 当前状态回补最小但可读的审计轨迹。"""

        del session_id
        plan = _ensure_mapping(snapshot_json.get("plan"))
        routing = _ensure_mapping(snapshot_json.get("routing"))
        authority = _ensure_mapping(snapshot_json.get("authority"))
        gate_decision = _ensure_mapping(snapshot_json.get("gate_decision"))
        result = _ensure_mapping(snapshot_json.get("result"))
        outcome = _ensure_mapping(snapshot_json.get("outcome"))

        scenario = str(plan.get("scenario", execution.scenario))
        selected_strategy = str(routing.get("selected_strategy", ""))
        selected_route = _ensure_mapping(routing.get("selected_route"))
        runtime = str(selected_route.get("runtime", ""))
        task_id = str(snapshot_json.get("task_id", "") or "")

        events: list[dict[str, Any]] = []

        if task_id and "orchestrator.routed" not in existing_steps:
            events.append(
                {
                    "step_name": "orchestrator.routed",
                    "payload": {
                        "task_id": task_id,
                        "execution_id": execution_id,
                        "scenario": scenario,
                        "selected_strategy": selected_strategy,
                        "runtime": runtime,
                        "approvals_required": bool(authority.get("approvals_required", False)),
                    },
                }
            )

        final_step = self._build_terminal_event(
            execution_id=execution_id,
            execution=execution,
            scenario=scenario,
            selected_strategy=selected_strategy,
            gate_decision=gate_decision,
            task_id=task_id,
            result=result,
            outcome=outcome,
        )
        if final_step is not None and str(final_step["step_name"]) not in existing_steps:
            events.append(final_step)

        if not events:
            events.append(
                {
                    "step_name": "execution.repaired",
                    "payload": {
                        "execution_id": execution_id,
                        "scenario": scenario,
                        "execution_status": execution.execution_status,
                        "audit_status_before": execution.audit_status,
                    },
                }
            )

        return events

    def _build_terminal_event(
        self,
        *,
        execution_id: str,
        execution: Any,
        scenario: str,
        selected_strategy: str,
        gate_decision: dict[str, Any],
        task_id: str,
        result: dict[str, Any],
        outcome: dict[str, Any],
    ) -> dict[str, Any] | None:
        """根据 execution 最终态构造与 orchestrator 对齐的结束事件。"""

        if execution.execution_status in {"completed", "partially_completed"}:
            operator_trace_summary: list[dict[str, Any]] = []
            for item in result.get("operator_trace", []):
                if not isinstance(item, dict):
                    continue
                operator_trace_summary.append(
                    {
                        "operator_id": item.get("operator_id"),
                        "operator_version": item.get("operator_version"),
                        "confidence": item.get("confidence"),
                    }
                )
            return {
                "step_name": "orchestrator.completed",
                "payload": {
                    "task_id": task_id,
                    "execution_id": execution_id,
                    "scenario": scenario,
                    "selected_strategy": selected_strategy,
                    "success": bool(outcome.get("success", True)),
                    "summary": str(outcome.get("summary") or result.get("summary") or "执行完成"),
                    "operator_trace_summary": operator_trace_summary,
                },
            }

        if execution.execution_status == "failed":
            return {
                "step_name": "orchestrator.failed",
                "payload": {
                    "task_id": task_id,
                    "execution_id": execution_id,
                    "scenario": scenario,
                    "selected_strategy": selected_strategy,
                    "error": str(
                        outcome.get("summary")
                        or result.get("error")
                        or "execution failed"
                    ),
                },
            }

        if execution.execution_status == "blocked" or execution.gate_status == "denied":
            return {
                "step_name": "orchestrator.blocked",
                "payload": {
                    "execution_id": execution_id,
                    "scenario": scenario,
                    "selected_strategy": selected_strategy,
                    "reason": str(gate_decision.get("reason", "execution blocked")),
                },
            }

        return None
