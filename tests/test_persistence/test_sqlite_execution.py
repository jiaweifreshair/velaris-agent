"""execution / session SQLite 仓储测试。"""

from __future__ import annotations

from pathlib import Path

from velaris_agent.persistence.schema import bootstrap_sqlite_schema
from velaris_agent.persistence.sqlite_execution import (
    ExecutionRepository,
    SessionRecord,
    SessionRepository,
)
from velaris_agent.persistence.sqlite_helpers import get_project_database_path
from velaris_agent.velaris.execution_contract import BizExecutionRecord


def test_sqlite_execution_and_session_repositories_roundtrip(tmp_path: Path) -> None:
    """SQLite 仓储应完成 upsert、读取与状态推进闭环。"""

    database_path = get_project_database_path(tmp_path)
    bootstrap_sqlite_schema(database_path)

    session_repository = SessionRepository(database_path)
    execution_repository = ExecutionRepository(database_path)

    session_repository.upsert(
        SessionRecord(
            session_id="session-explicit",
            binding_mode="attached",
            source_runtime="openharness",
            summary="采购比价闭环",
            message_count=3,
            created_at="2026-04-18T20:00:00+08:00",
            updated_at="2026-04-18T20:00:01+08:00",
            snapshot_json={"cwd": "/workspace/velaris-agent"},
        )
    )

    stored_session = session_repository.get("session-explicit")
    assert stored_session is not None
    assert stored_session.snapshot_json["cwd"] == "/workspace/velaris-agent"
    assert session_repository.latest_by_cwd("/workspace/velaris-agent").session_id == "session-explicit"
    assert len(session_repository.list_by_cwd("/workspace/velaris-agent")) == 1

    execution_repository.create(
        BizExecutionRecord(
            execution_id="exec-explicit",
            session_id="session-explicit",
            scenario="procurement",
            execution_status="planned",
            gate_status="allowed",
            effective_risk_level="low",
            degraded_mode=False,
            audit_status="not_required",
            structural_complete=False,
            constraint_complete=False,
            goal_complete=False,
            created_at="2026-04-18T20:00:02+08:00",
            updated_at="2026-04-18T20:00:02+08:00",
            resume_cursor={"stage": "planned"},
        ),
        snapshot_json={"plan": {"scenario": "procurement"}},
    )

    updated = execution_repository.update_status(
        "exec-explicit",
        execution_status="completed",
        gate_status="allowed",
        effective_risk_level="low",
        degraded_mode=False,
        audit_status="persisted",
        structural_complete=True,
        constraint_complete=True,
        goal_complete=True,
        resume_cursor={"stage": "completed"},
    )

    assert updated is not None
    assert updated.execution_status == "completed"
    assert execution_repository.get("exec-explicit").resume_cursor == {"stage": "completed"}
    assert len(execution_repository.list_by_session("session-explicit")) == 1


def test_sqlite_execution_repository_returns_none_when_execution_missing(tmp_path: Path) -> None:
    """缺少 execution 时应返回 None，避免调用方误判状态推进成功。"""

    database_path = get_project_database_path(tmp_path)
    bootstrap_sqlite_schema(database_path)
    repository = ExecutionRepository(database_path)

    updated = repository.update_status(
        "exec-missing",
        execution_status="completed",
        gate_status="allowed",
        effective_risk_level="low",
        degraded_mode=False,
        audit_status="persisted",
        structural_complete=True,
        constraint_complete=True,
        goal_complete=True,
        resume_cursor={"stage": "completed"},
    )

    assert updated is None
