"""PostgreSQL 运行时仓储测试。"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from velaris_agent.persistence.schema import bootstrap_schema
from velaris_agent.velaris.outcome_store import OutcomeRecord
from velaris_agent.velaris.task_ledger import TaskLedgerRecord


def _unwrap_payload(value: Any) -> Any:
    """从 psycopg Jsonb 或普通对象中提取原始 payload。"""

    return getattr(value, "obj", value)


class _FakeCursor:
    """用于单元测试的内存版 PostgreSQL 游标。"""

    def __init__(self, tables: dict[str, dict[str, dict[str, Any]]]) -> None:
        """绑定共享表状态，模拟最小 SQL 闭环。"""

        self._tables = tables
        self._result: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        """按 Task 3 需要的最小 SQL 语义更新或读取内存数据。"""

        params = params or ()
        normalized = " ".join(sql.lower().split())

        if normalized.startswith("insert into "):
            table_name = normalized.split()[2]
            record_id = str(params[0])
            created_at = params[1]
            payload = deepcopy(_unwrap_payload(params[2]))
            self._tables.setdefault(table_name, {})[record_id] = {
                "record_id": record_id,
                "created_at": created_at,
                "payload": payload,
            }
            self._result = []
            return

        if normalized.startswith("select payload from ") and "where record_id = %s" in normalized:
            table_name = normalized.split()[3]
            record_id = str(params[0])
            row = self._tables.get(table_name, {}).get(record_id)
            self._result = [(deepcopy(row["payload"]),)] if row else []
            return

        if normalized.startswith("update ") and "set payload = %s where record_id = %s" in normalized:
            table_name = normalized.split()[1]
            payload = deepcopy(_unwrap_payload(params[0]))
            record_id = str(params[1])
            row = self._tables.get(table_name, {}).get(record_id)
            if row is not None:
                row["payload"] = payload
            self._result = []
            return

        if "where payload->>'session_id' = %s" in normalized:
            table_name = normalized.split()[3]
            session_id = str(params[0])
            rows = [
                row
                for row in self._tables.get(table_name, {}).values()
                if str(row["payload"].get("session_id")) == session_id
            ]
            ordered = sorted(rows, key=lambda item: (item["created_at"], item["record_id"]))
            self._result = [(deepcopy(row["payload"]),) for row in ordered]
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
    """用于单元测试的内存版 PostgreSQL 连接。"""

    def __init__(self, tables: dict[str, dict[str, dict[str, Any]]]) -> None:
        """持有共享表状态，用于模拟事务连接。"""

        self._tables = tables
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> _FakeCursor:
        """返回与当前连接关联的伪游标。"""

        return _FakeCursor(self._tables)

    def commit(self) -> None:
        """记录提交动作，便于测试事务闭环。"""

        self.committed = True

    def rollback(self) -> None:
        """记录回滚动作，便于测试异常路径。"""

        self.rolled_back = True

    def close(self) -> None:
        """与真实连接接口保持一致。"""

        return None


def test_runtime_repositories_roundtrip_with_fake_connection(monkeypatch) -> None:
    """运行时 PostgreSQL 仓储应完成写入、更新与按会话读取闭环。"""

    from velaris_agent.persistence.postgres_runtime import (
        AuditEventStore,
        PostgresOutcomeStore,
        PostgresTaskLedger,
    )

    tables: dict[str, dict[str, dict[str, Any]]] = {}
    connection = _FakeConnection(tables)

    @contextmanager
    def fake_postgres_connection(dsn: str):
        """伪造 PostgreSQL 事务连接，验证仓储层行为。"""

        assert dsn == "postgresql://user:pass@localhost:5432/velaris"
        try:
            yield connection
        finally:
            connection.committed = True

    monkeypatch.setattr(
        "velaris_agent.persistence.postgres_runtime.postgres_connection",
        fake_postgres_connection,
    )

    ledger = PostgresTaskLedger("postgresql://user:pass@localhost:5432/velaris")
    outcome_store = PostgresOutcomeStore("postgresql://user:pass@localhost:5432/velaris")
    audit_store = AuditEventStore("postgresql://user:pass@localhost:5432/velaris")

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


def test_runtime_repositories_persist_and_list(postgres_dsn: str) -> None:
    """真实 PostgreSQL 环境下应完成运行时仓储最小持久化闭环。"""

    from velaris_agent.persistence.postgres_runtime import (
        AuditEventStore,
        PostgresOutcomeStore,
        PostgresTaskLedger,
    )

    bootstrap_schema(postgres_dsn)
    unique_suffix = str(int(datetime.now(timezone.utc).timestamp() * 1000000))
    session_id = f"session-runtime-{unique_suffix}"
    ledger = PostgresTaskLedger(postgres_dsn)
    outcome_store = PostgresOutcomeStore(postgres_dsn)
    audit_store = AuditEventStore(postgres_dsn)

    task = ledger.create_task(
        session_id=session_id,
        runtime="local",
        role="biz_executor",
        objective="采购比价",
    )
    ledger.update_status(task.task_id, "completed")
    outcome_store.record(
        session_id=session_id,
        scenario="procurement",
        selected_strategy="local_closed_loop",
        success=True,
        reason_codes=["R001"],
        summary="推荐完成",
    )
    audit_store.append_event(
        session_id=session_id,
        step_name="orchestrator.completed",
        operator_id="VelarisBizOrchestrator",
        payload={"task_id": task.task_id},
    )

    tasks = ledger.list_by_session(session_id)
    outcomes = outcome_store.list_by_session(session_id)
    events = audit_store.list_by_session(session_id)

    assert len(tasks) == 1
    assert tasks[0].status == "completed"
    assert len(outcomes) == 1
    assert outcomes[0].selected_strategy == "local_closed_loop"
    assert len(events) == 1
    assert events[0].payload["task_id"] == task.task_id


def test_outcome_record_from_dict_parses_false_string_explicitly() -> None:
    """OutcomeRecord 应显式解析字符串布尔值，避免 `"false"` 被误判。"""

    record = OutcomeRecord.from_dict(
        {
            "session_id": "session-1",
            "scenario": "procurement",
            "selected_strategy": "local_closed_loop",
            "success": "false",
            "reason_codes": ["R001"],
            "summary": "推荐完成",
            "metrics": {},
            "created_at": "2026-04-16T00:00:00+00:00",
        }
    )

    assert record.success is False
