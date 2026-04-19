"""SQLite 运行时仓储测试。"""

from __future__ import annotations

from pathlib import Path

from velaris_agent.persistence.schema import bootstrap_sqlite_schema
from velaris_agent.persistence.sqlite_helpers import get_project_database_path
from velaris_agent.persistence.sqlite_runtime import (
    SqliteAuditEventStore,
    SqliteOutcomeStore,
    SqliteTaskLedger,
)
from velaris_agent.velaris.outcome_store import OutcomeRecord
from velaris_agent.velaris.task_ledger import TaskLedgerRecord


def test_sqlite_runtime_repositories_roundtrip(tmp_path: Path) -> None:
    """SQLite 运行时仓储应完成写入、更新与按会话读取闭环。"""

    database_path = get_project_database_path(tmp_path)
    bootstrap_sqlite_schema(database_path)

    ledger = SqliteTaskLedger(database_path)
    outcome_store = SqliteOutcomeStore(database_path)
    audit_store = SqliteAuditEventStore(database_path)

    task = ledger.create_task(
        session_id="session-unit",
        runtime="local",
        role="biz_executor",
        objective="采购比价",
    )
    updated_task = ledger.update_status(task.task_id, "completed")
    outcome = outcome_store.record(
        session_id="session-unit",
        scenario="procurement",
        selected_strategy="local_closed_loop",
        success=True,
        reason_codes=["R001"],
        summary="推荐完成",
    )
    event = audit_store.append_event(
        session_id="session-unit",
        step_name="orchestrator.completed",
        operator_id="VelarisBizOrchestrator",
        payload={"task_id": task.task_id},
    )

    assert isinstance(updated_task, TaskLedgerRecord)
    assert updated_task.status == "completed"
    assert ledger.get_task(task.task_id).status == "completed"
    assert len(ledger.list_by_session("session-unit")) == 1
    assert isinstance(outcome, OutcomeRecord)
    assert len(outcome_store.list_by_session("session-unit")) == 1
    assert event.step_name == "orchestrator.completed"
    assert len(audit_store.list_by_session("session-unit")) == 1
