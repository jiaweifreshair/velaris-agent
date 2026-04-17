"""数据库任务队列测试。"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from typing import Any

import velaris_agent.persistence.job_queue as job_queue_module
from velaris_agent.persistence.job_queue import PostgresJobQueue, run_jobs_once


def _unwrap_payload(value: Any) -> Any:
    """从 psycopg Jsonb 或普通对象中提取原始 payload。"""

    return getattr(value, "obj", value)


class _FakeCursor:
    """用于单元测试的内存版 PostgreSQL 游标。"""

    def __init__(self, tables: dict[str, dict[str, dict[str, Any]]]) -> None:
        """绑定共享表状态，模拟最小 SQL 读写语义。"""

        self._tables = tables
        self._result: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        """按任务队列当前需要的最小 SQL 语义更新或读取内存数据。"""

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

        if normalized.startswith("select record_id, payload from job_queue where payload->>'job_type' = %s and payload->>'idempotency_key' = %s"):
            job_type = str(params[0])
            idempotency_key = str(params[1])
            rows = [
                row
                for row in self._tables.get("job_queue", {}).values()
                if row["payload"].get("job_type") == job_type
                and row["payload"].get("idempotency_key") == idempotency_key
            ]
            ordered = sorted(rows, key=lambda item: (item["created_at"], item["record_id"]), reverse=True)
            self._result = [
                (ordered[0]["record_id"], deepcopy(ordered[0]["payload"]))
            ] if ordered else []
            return

        if normalized.startswith("select record_id, payload from job_queue where coalesce(payload->>'status', 'queued') = 'queued'"):
            job_types = set(params[0])
            rows = [
                row
                for row in self._tables.get("job_queue", {}).values()
                if row["payload"].get("status", "queued") == "queued"
                and row["payload"].get("job_type") in job_types
            ]
            ordered = sorted(rows, key=lambda item: (item["created_at"], item["record_id"]))
            self._result = [
                (ordered[0]["record_id"], deepcopy(ordered[0]["payload"]))
            ] if ordered else []
            return

        if normalized.startswith("select payload from job_queue where record_id = %s"):
            row = self._tables.get("job_queue", {}).get(str(params[0]))
            self._result = [(deepcopy(row["payload"]),)] if row else []
            return

        if normalized.startswith("select payload from job_runs where payload->>'job_id' = %s"):
            job_id = str(params[0])
            rows = [
                row
                for row in self._tables.get("job_runs", {}).values()
                if row["payload"].get("job_id") == job_id
            ]
            ordered = sorted(rows, key=lambda item: (item["created_at"], item["record_id"]))
            self._result = [(deepcopy(row["payload"]),) for row in ordered]
            return

        if normalized.startswith("update ") and "set payload = %s where record_id = %s" in normalized:
            payload = deepcopy(_unwrap_payload(params[0]))
            record_id = str(params[1])
            table_name = normalized.split()[1]
            row = self._tables.get(table_name, {}).get(record_id)
            if row is not None:
                row["payload"] = payload
            self._result = []
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

    def cursor(self) -> _FakeCursor:
        """返回与当前连接关联的伪游标。"""

        return _FakeCursor(self._tables)

    def commit(self) -> None:
        """与真实连接接口保持一致。"""

        return None

    def rollback(self) -> None:
        """与真实连接接口保持一致。"""

        return None

    def close(self) -> None:
        """与真实连接接口保持一致。"""

        return None


def test_postgres_job_queue_roundtrip_with_fake_connection(monkeypatch) -> None:
    """任务队列应完成 enqueue / claim / mark_succeeded / get 最小闭环。"""

    tables: dict[str, dict[str, dict[str, Any]]] = {}
    connection = _FakeConnection(tables)

    @contextmanager
    def fake_postgres_connection(dsn: str):
        """伪造 PostgreSQL 事务连接，验证队列层行为。"""

        assert dsn == "postgresql://user:pass@localhost:5432/velaris"
        yield connection

    monkeypatch.setattr(job_queue_module, "postgres_connection", fake_postgres_connection)

    queue = PostgresJobQueue("postgresql://user:pass@localhost:5432/velaris")
    job_id = queue.enqueue(
        "self_evolution_review",
        "u-save:travel:2",
        {"user_id": "u-save", "scenario": "travel", "window": 10},
    )

    queued = queue.get(job_id)
    assert queued is not None
    assert queued.status == "queued"
    assert queued.payload["user_id"] == "u-save"

    claimed = queue.claim_next(["self_evolution_review"])
    assert claimed is not None
    assert claimed.job_id == job_id
    assert claimed.status == "running"
    assert claimed.attempt_count == 1

    queue.mark_succeeded(job_id)

    succeeded = queue.get(job_id)
    assert succeeded is not None
    assert succeeded.status == "succeeded"
    assert succeeded.finished_at is not None
    runs = queue.list_runs(job_id)
    assert len(runs) == 1
    assert runs[0].status == "succeeded"
    assert runs[0].attempt_count == 1
    assert runs[0].finished_at is not None


def test_run_jobs_once_processes_self_evolution_jobs(monkeypatch) -> None:
    """run_jobs_once 应顺序执行 self_evolution_review 队列任务。"""

    tables: dict[str, dict[str, dict[str, Any]]] = {}
    connection = _FakeConnection(tables)

    @contextmanager
    def fake_postgres_connection(dsn: str):
        """伪造 PostgreSQL 事务连接，验证 worker 调度行为。"""

        assert dsn == "postgresql://user:pass@localhost:5432/velaris"
        yield connection

    processed_payloads: list[dict[str, Any]] = []

    def fake_run_self_evolution_review_job(*, postgres_dsn: str, payload: dict[str, Any]):
        """记录 worker 收到的 payload，避免真实执行自进化。"""

        assert postgres_dsn == "postgresql://user:pass@localhost:5432/velaris"
        processed_payloads.append(dict(payload))
        return {"status": "ok"}

    monkeypatch.setattr(job_queue_module, "postgres_connection", fake_postgres_connection)
    monkeypatch.setattr(
        job_queue_module,
        "_run_self_evolution_review_job",
        fake_run_self_evolution_review_job,
    )

    queue = PostgresJobQueue("postgresql://user:pass@localhost:5432/velaris")
    first_job_id = queue.enqueue(
        "self_evolution_review",
        "u-save:travel:2",
        {"user_id": "u-save", "scenario": "travel", "window": 10},
    )
    second_job_id = queue.enqueue(
        "self_evolution_review",
        "u-save:travel:4",
        {"user_id": "u-save", "scenario": "travel", "window": 10},
    )

    processed = run_jobs_once("postgresql://user:pass@localhost:5432/velaris", limit=5)

    assert processed == 2
    assert [payload["scenario"] for payload in processed_payloads] == ["travel", "travel"]
    assert queue.get(first_job_id).status == "succeeded"
    assert queue.get(second_job_id).status == "succeeded"
    assert len(queue.list_runs(first_job_id)) == 1
    assert len(queue.list_runs(second_job_id)) == 1
