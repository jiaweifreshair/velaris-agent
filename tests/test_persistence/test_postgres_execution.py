"""execution / session PostgreSQL 仓储测试。"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from velaris_agent.persistence.schema import bootstrap_schema
from velaris_agent.velaris.execution_contract import BizExecutionRecord


def _unwrap_payload(value: Any) -> Any:
    """从 psycopg Jsonb 或普通对象中取出原始字典。"""

    return getattr(value, "obj", value)


class _FakeCursor:
    """用于 execution / session 仓储测试的伪游标。"""

    def __init__(self, tables: dict[str, dict[str, dict[str, Any]]]) -> None:
        self._tables = tables
        self._result: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        """按最小 SQL 语义更新内存表状态。"""

        params = params or ()
        normalized = " ".join(sql.lower().split())

        if normalized.startswith("insert into session_records "):
            self._tables.setdefault("session_records", {})[str(params[0])] = {
                "session_id": str(params[0]),
                "binding_mode": str(params[1]),
                "source_runtime": str(params[2]),
                "summary": str(params[3]),
                "message_count": int(params[4]),
                "snapshot_json": deepcopy(_unwrap_payload(params[5])),
                "created_at": str(params[6]),
                "updated_at": str(params[7]),
            }
            self._result = []
            return

        if normalized.startswith("select session_id, binding_mode"):
            row = self._tables.get("session_records", {}).get(str(params[0]))
            self._result = [(
                row["session_id"],
                row["binding_mode"],
                row["source_runtime"],
                row["summary"],
                row["message_count"],
                deepcopy(row["snapshot_json"]),
                row["created_at"],
                row["updated_at"],
            )] if row else []
            return

        if normalized.startswith("insert into execution_records "):
            self._tables.setdefault("execution_records", {})[str(params[0])] = {
                "execution_id": str(params[0]),
                "session_id": params[1],
                "scenario": str(params[2]),
                "execution_status": str(params[3]),
                "gate_status": str(params[4]),
                "effective_risk_level": str(params[5]),
                "degraded_mode": bool(params[6]),
                "audit_status": str(params[7]),
                "structural_complete": bool(params[8]),
                "constraint_complete": bool(params[9]),
                "goal_complete": bool(params[10]),
                "resume_cursor": deepcopy(_unwrap_payload(params[11])),
                "snapshot_json": deepcopy(_unwrap_payload(params[12])),
                "created_at": str(params[13]),
                "updated_at": str(params[14]),
            }
            self._result = []
            return

        if normalized.startswith("update execution_records set "):
            execution_id = str(params[-1])
            row = self._tables.get("execution_records", {}).get(execution_id)
            if row is None:
                self._result = []
                return
            row.update(
                {
                    "execution_status": str(params[0]),
                    "gate_status": str(params[1]),
                    "effective_risk_level": str(params[2]),
                    "degraded_mode": bool(params[3]),
                    "audit_status": str(params[4]),
                    "structural_complete": bool(params[5]),
                    "constraint_complete": bool(params[6]),
                    "goal_complete": bool(params[7]),
                    "resume_cursor": deepcopy(_unwrap_payload(params[8])),
                    "snapshot_json": deepcopy(_unwrap_payload(params[9])),
                    "updated_at": str(params[10]),
                }
            )
            self._result = []
            return

        if normalized.startswith("select execution_id, session_id"):
            if "where execution_id = %s" in normalized:
                row = self._tables.get("execution_records", {}).get(str(params[0]))
                rows = [row] if row else []
            else:
                session_id = str(params[0])
                rows = [
                    row
                    for row in self._tables.get("execution_records", {}).values()
                    if str(row.get("session_id")) == session_id
                ]
                rows = sorted(rows, key=lambda item: (item["created_at"], item["execution_id"]))
            self._result = [
                (
                    row["execution_id"],
                    row["session_id"],
                    row["scenario"],
                    row["execution_status"],
                    row["gate_status"],
                    row["effective_risk_level"],
                    row["degraded_mode"],
                    row["audit_status"],
                    row["structural_complete"],
                    row["constraint_complete"],
                    row["goal_complete"],
                    deepcopy(row["resume_cursor"]),
                    deepcopy(row["snapshot_json"]),
                    row["created_at"],
                    row["updated_at"],
                )
                for row in rows
            ]
            return

        raise AssertionError(f"未预期的 SQL: {sql}")

    def fetchone(self) -> tuple[Any, ...] | None:
        """返回一条结果。"""

        if not self._result:
            return None
        return self._result.pop(0)

    def fetchall(self) -> list[tuple[Any, ...]]:
        """返回全部结果。"""

        result = list(self._result)
        self._result = []
        return result

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeConnection:
    """用于 execution / session 仓储测试的伪连接。"""

    def __init__(self, tables: dict[str, dict[str, dict[str, Any]]]) -> None:
        self._tables = tables
        self.committed = False

    def cursor(self) -> _FakeCursor:
        """返回与共享表绑定的伪游标。"""

        return _FakeCursor(self._tables)

    def commit(self) -> None:
        """记录提交动作。"""

        self.committed = True

    def rollback(self) -> None:
        """保持与真实接口兼容。"""

        return None

    def close(self) -> None:
        """保持与真实接口兼容。"""

        return None


def test_execution_and_session_repositories_roundtrip_with_fake_connection(monkeypatch) -> None:
    """显式 execution / session 仓储应完成 upsert、读取与状态推进闭环。"""

    from velaris_agent.persistence.postgres_execution import (
        ExecutionRepository,
        SessionRecord,
        SessionRepository,
    )

    tables: dict[str, dict[str, dict[str, Any]]] = {}
    connection = _FakeConnection(tables)

    @contextmanager
    def fake_postgres_connection(dsn: str):
        assert dsn == "postgresql://user:pass@localhost:5432/velaris"
        try:
            yield connection
        finally:
            connection.committed = True

    monkeypatch.setattr(
        "velaris_agent.persistence.postgres_execution.postgres_connection",
        fake_postgres_connection,
    )

    session_repository = SessionRepository("postgresql://user:pass@localhost:5432/velaris")
    execution_repository = ExecutionRepository("postgresql://user:pass@localhost:5432/velaris")

    session = session_repository.upsert(
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
    created = execution_repository.create(
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
        snapshot_json={"plan": {"scenario": "procurement"}, "result": {"success": True}},
    )

    assert session.session_id == "session-explicit"
    assert session_repository.get("session-explicit").snapshot_json["cwd"] == "/workspace/velaris-agent"
    assert created.execution_id == "exec-explicit"
    assert updated is not None
    assert updated.execution_status == "completed"
    assert updated.audit_status == "persisted"
    assert execution_repository.get("exec-explicit").resume_cursor == {"stage": "completed"}
    assert len(execution_repository.list_by_session("session-explicit")) == 1


def test_execution_and_session_repositories_persist_with_real_postgres(postgres_dsn: str) -> None:
    """真实 PostgreSQL 环境下也应完成 execution / session 显式仓储最小闭环。"""

    from velaris_agent.persistence.postgres_execution import (
        ExecutionRepository,
        SessionRecord,
        SessionRepository,
    )

    bootstrap_schema(postgres_dsn)
    unique_suffix = str(int(datetime.now(timezone.utc).timestamp() * 1000000))
    session_id = f"session-explicit-{unique_suffix}"
    execution_id = f"exec-explicit-{unique_suffix}"
    session_repository = SessionRepository(postgres_dsn)
    execution_repository = ExecutionRepository(postgres_dsn)

    session_repository.upsert(
        SessionRecord(
            session_id=session_id,
            binding_mode="attached",
            source_runtime="openharness",
            summary="采购比价闭环",
            message_count=2,
            created_at="2026-04-18T20:00:00+08:00",
            updated_at="2026-04-18T20:00:01+08:00",
            snapshot_json={"cwd": "/workspace/velaris-agent"},
        )
    )
    execution_repository.create(
        BizExecutionRecord(
            execution_id=execution_id,
            session_id=session_id,
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

    execution_repository.update_status(
        execution_id,
        execution_status="completed",
        gate_status="allowed",
        effective_risk_level="low",
        degraded_mode=False,
        audit_status="persisted",
        structural_complete=True,
        constraint_complete=True,
        goal_complete=True,
        resume_cursor={"stage": "completed"},
        snapshot_json={"plan": {"scenario": "procurement"}, "result": {"success": True}},
    )

    stored_session = session_repository.get(session_id)
    stored_execution = execution_repository.get(execution_id)

    assert stored_session is not None
    assert stored_session.summary == "采购比价闭环"
    assert stored_execution is not None
    assert stored_execution.execution_status == "completed"
    assert stored_execution.audit_status == "persisted"
    assert len(execution_repository.list_by_session(session_id)) == 1
