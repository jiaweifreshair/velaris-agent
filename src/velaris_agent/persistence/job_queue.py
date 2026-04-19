"""SQLite 任务队列最小实现。

该模块依赖 SQLite 主线 schema 中的两张表：
- `job_queue`：保存“当前任务状态”
- `job_runs`：保存“每次执行尝试历史”

主要用途是把非热路径任务（例如自进化复盘）从同步工具调用中剥离出来，
避免阻塞主交互链路，同时让后台行为可追踪、可重放。

约束：
- 不依赖 SQLite JSON1，所有 payload 以 JSON 文本写入 `payload_json`；
- 只提供最小 enqueue / claim / mark_succeeded / mark_failed / list_runs API。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from velaris_agent.persistence.sqlite import sqlite_connection

SELF_EVOLUTION_REVIEW_JOB_TYPE = "self_evolution_review"


def _run_self_evolution_review_job(*, sqlite_database_path: str, payload: dict[str, Any]) -> Any:
    """按需导入并执行自进化 worker。

    这里保持 lazy import，避免 `job_queue` 在 import 阶段绑定上层依赖（pydantic 等），
    只有真正消费 self-evolution 任务时才加载完整链路。
    """

    from velaris_agent.evolution.self_evolution import run_self_evolution_review_job

    return run_self_evolution_review_job(sqlite_database_path=sqlite_database_path, payload=payload)


@dataclass(frozen=True)
class JobRecord:
    """任务队列中的单条作业记录。"""

    job_id: str
    job_type: str
    status: str
    idempotency_key: str
    payload: dict[str, Any]
    attempt_count: int
    created_at: str
    claimed_at: str | None = None
    finished_at: str | None = None
    last_error: str | None = None
    current_run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """把作业记录转换为 JSON 友好的 payload。"""

        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobRecord":
        """从 payload 还原作业记录。"""

        return cls(
            job_id=str(payload["job_id"]),
            job_type=str(payload["job_type"]),
            status=str(payload.get("status", "queued")),
            idempotency_key=str(payload.get("idempotency_key", "")),
            payload=dict(payload.get("payload", {})),
            attempt_count=int(payload.get("attempt_count", 0)),
            created_at=str(payload.get("created_at", "")),
            claimed_at=_optional_text(payload.get("claimed_at")),
            finished_at=_optional_text(payload.get("finished_at")),
            last_error=_optional_text(payload.get("last_error")),
            current_run_id=_optional_text(payload.get("current_run_id")),
        )


@dataclass(frozen=True)
class JobRunRecord:
    """单次后台任务执行记录。"""

    run_id: str
    job_id: str
    job_type: str
    attempt_count: int
    status: str
    started_at: str
    finished_at: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """把执行记录转换为 JSON 友好的 payload。"""

        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobRunRecord":
        """从 payload 还原执行记录。"""

        return cls(
            run_id=str(payload["run_id"]),
            job_id=str(payload["job_id"]),
            job_type=str(payload["job_type"]),
            attempt_count=int(payload.get("attempt_count", 0)),
            status=str(payload.get("status", "running")),
            started_at=str(payload.get("started_at", "")),
            finished_at=_optional_text(payload.get("finished_at")),
            last_error=_optional_text(payload.get("last_error")),
        )


class SqliteJobQueue:
    """基于 SQLite 显式列 schema 的任务队列。"""

    def __init__(self, database_path: str | Path) -> None:
        """保存 SQLite 数据库路径，供后续队列操作复用。"""

        self._database_path = str(database_path)

    def enqueue(
        self,
        job_type: str,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> str:
        """写入一条新任务；若幂等键已存在，则直接返回已有 job_id。"""

        existing = self._find_by_idempotency(job_type=job_type, idempotency_key=idempotency_key)
        if existing is not None:
            return existing.job_id

        created_at = _utc_now().isoformat()
        job = JobRecord(
            job_id=f"job-{uuid4().hex[:12]}",
            job_type=job_type,
            status="queued",
            idempotency_key=idempotency_key,
            payload=dict(payload),
            attempt_count=0,
            created_at=created_at,
        )
        with sqlite_connection(self._database_path) as connection:
            connection.execute(
                """
                insert into job_queue (
                  job_id,
                  job_type,
                  status,
                  idempotency_key,
                  payload_json,
                  attempt_count,
                  created_at,
                  claimed_at,
                  finished_at,
                  last_error,
                  current_run_id
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict (job_id) do update set
                  job_type = excluded.job_type,
                  status = excluded.status,
                  idempotency_key = excluded.idempotency_key,
                  payload_json = excluded.payload_json,
                  attempt_count = excluded.attempt_count,
                  created_at = excluded.created_at,
                  claimed_at = excluded.claimed_at,
                  finished_at = excluded.finished_at,
                  last_error = excluded.last_error,
                  current_run_id = excluded.current_run_id
                """,
                (
                    job.job_id,
                    job.job_type,
                    job.status,
                    job.idempotency_key,
                    _dump_json(job.payload),
                    job.attempt_count,
                    job.created_at,
                    job.claimed_at,
                    job.finished_at,
                    job.last_error,
                    job.current_run_id,
                ),
            )
        return job.job_id

    def claim_next(self, job_types: list[str]) -> JobRecord | None:
        """按创建顺序认领下一条待处理任务。"""

        if not job_types:
            return None

        placeholders = ", ".join("?" for _ in job_types)
        sql = f"""
            select
              job_id,
              job_type,
              status,
              idempotency_key,
              payload_json,
              attempt_count,
              created_at,
              claimed_at,
              finished_at,
              last_error,
              current_run_id
            from job_queue
            where status = 'queued'
              and job_type in ({placeholders})
            order by created_at asc, job_id asc
            limit 1
        """
        with sqlite_connection(self._database_path) as connection:
            row = connection.execute(sql, tuple(job_types)).fetchone()
        if row is None:
            return None

        record = self._row_to_job(row)
        updated = record_from(
            record,
            status="running",
            claimed_at=_utc_now().isoformat(),
            finished_at=None,
            last_error=None,
            attempt_count=record.attempt_count + 1,
            current_run_id=f"run-{uuid4().hex[:12]}",
        )
        self._update(updated)
        self._append_run(
            JobRunRecord(
                run_id=updated.current_run_id or f"run-{uuid4().hex[:12]}",
                job_id=updated.job_id,
                job_type=updated.job_type,
                attempt_count=updated.attempt_count,
                status="running",
                started_at=updated.claimed_at or _utc_now().isoformat(),
            )
        )
        return updated

    def mark_succeeded(self, job_id: str) -> JobRecord | None:
        """把任务标记为成功完成。"""

        record = self.get(job_id)
        if record is None:
            return None
        updated = record_from(
            record,
            status="succeeded",
            finished_at=_utc_now().isoformat(),
            last_error=None,
            current_run_id=None,
        )
        self._update(updated)
        self._update_run(
            run_id=record.current_run_id,
            status="succeeded",
            finished_at=updated.finished_at,
            last_error=None,
        )
        return updated

    def mark_failed(self, job_id: str, error: str) -> JobRecord | None:
        """把任务标记为失败，并保留最近一次错误信息。"""

        record = self.get(job_id)
        if record is None:
            return None
        updated = record_from(
            record,
            status="failed",
            finished_at=_utc_now().isoformat(),
            last_error=error,
            current_run_id=None,
        )
        self._update(updated)
        self._update_run(
            run_id=record.current_run_id,
            status="failed",
            finished_at=updated.finished_at,
            last_error=error,
        )
        return updated

    def get(self, job_id: str) -> JobRecord | None:
        """按 job_id 读取任务当前状态。"""

        with sqlite_connection(self._database_path) as connection:
            row = connection.execute(
                """
                select
                  job_id,
                  job_type,
                  status,
                  idempotency_key,
                  payload_json,
                  attempt_count,
                  created_at,
                  claimed_at,
                  finished_at,
                  last_error,
                  current_run_id
                from job_queue
                where job_id = ?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    def list_runs(self, job_id: str) -> list[JobRunRecord]:
        """按任务 ID 返回全部执行尝试，供观测与人工诊断使用。"""

        with sqlite_connection(self._database_path) as connection:
            rows = connection.execute(
                """
                select
                  run_id,
                  job_id,
                  job_type,
                  attempt_count,
                  status,
                  started_at,
                  finished_at,
                  last_error,
                  created_at
                from job_runs
                where job_id = ?
                order by created_at asc, run_id asc
                """,
                (job_id,),
            ).fetchall()

        runs: list[JobRunRecord] = []
        for row in rows:
            runs.append(
                JobRunRecord(
                    run_id=str(row[0]),
                    job_id=str(row[1]),
                    job_type=str(row[2]),
                    attempt_count=int(row[3]),
                    status=str(row[4]),
                    started_at=str(row[5]),
                    finished_at=_optional_text(row[6]),
                    last_error=_optional_text(row[7]),
                )
            )
        return runs

    def _find_by_idempotency(self, *, job_type: str, idempotency_key: str) -> JobRecord | None:
        """按作业类型与幂等键读取已有任务。"""

        with sqlite_connection(self._database_path) as connection:
            row = connection.execute(
                """
                select
                  job_id,
                  job_type,
                  status,
                  idempotency_key,
                  payload_json,
                  attempt_count,
                  created_at,
                  claimed_at,
                  finished_at,
                  last_error,
                  current_run_id
                from job_queue
                where job_type = ?
                  and idempotency_key = ?
                order by created_at desc, job_id desc
                limit 1
                """,
                (job_type, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    def _update(self, record: JobRecord) -> None:
        """把最新字段写回 job_queue。"""

        with sqlite_connection(self._database_path) as connection:
            connection.execute(
                """
                update job_queue set
                  status = ?,
                  payload_json = ?,
                  attempt_count = ?,
                  claimed_at = ?,
                  finished_at = ?,
                  last_error = ?,
                  current_run_id = ?
                where job_id = ?
                """,
                (
                    record.status,
                    _dump_json(record.payload),
                    record.attempt_count,
                    record.claimed_at,
                    record.finished_at,
                    record.last_error,
                    record.current_run_id,
                    record.job_id,
                ),
            )

    def _append_run(self, run: JobRunRecord) -> None:
        """把一次新的 job run 追加到 `job_runs` 表。"""

        with sqlite_connection(self._database_path) as connection:
            connection.execute(
                """
                insert into job_runs (
                  run_id,
                  job_id,
                  job_type,
                  attempt_count,
                  status,
                  started_at,
                  finished_at,
                  last_error,
                  created_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict (run_id) do update set
                  job_id = excluded.job_id,
                  job_type = excluded.job_type,
                  attempt_count = excluded.attempt_count,
                  status = excluded.status,
                  started_at = excluded.started_at,
                  finished_at = excluded.finished_at,
                  last_error = excluded.last_error,
                  created_at = excluded.created_at
                """,
                (
                    run.run_id,
                    run.job_id,
                    run.job_type,
                    run.attempt_count,
                    run.status,
                    run.started_at,
                    run.finished_at,
                    run.last_error,
                    run.started_at,
                ),
            )

    def _update_run(
        self,
        *,
        run_id: str | None,
        status: str,
        finished_at: str | None,
        last_error: str | None,
    ) -> None:
        """回写一次 job run 的最终状态。"""

        if not run_id:
            return
        with sqlite_connection(self._database_path) as connection:
            connection.execute(
                """
                update job_runs set
                  status = ?,
                  finished_at = ?,
                  last_error = ?
                where run_id = ?
                """,
                (status, finished_at, last_error, run_id),
            )

    @staticmethod
    def _row_to_job(row: Any) -> JobRecord:
        """从 SQLite 查询结果还原 JobRecord。"""

        return JobRecord(
            job_id=str(row[0]),
            job_type=str(row[1]),
            status=str(row[2]),
            idempotency_key=str(row[3]),
            payload=_load_json(row[4]),
            attempt_count=int(row[5]),
            created_at=str(row[6]),
            claimed_at=_optional_text(row[7]),
            finished_at=_optional_text(row[8]),
            last_error=_optional_text(row[9]),
            current_run_id=_optional_text(row[10]),
        )


def run_jobs_once(sqlite_database_path: str, limit: int = 10) -> int:
    """顺序处理一次队列中的后台任务，并返回处理数量。"""

    queue = SqliteJobQueue(sqlite_database_path)
    processed = 0
    for _ in range(max(limit, 0)):
        job = queue.claim_next([SELF_EVOLUTION_REVIEW_JOB_TYPE])
        if job is None:
            break
        try:
            if job.job_type != SELF_EVOLUTION_REVIEW_JOB_TYPE:
                raise ValueError(f"unsupported job type: {job.job_type}")
            _run_self_evolution_review_job(
                sqlite_database_path=str(sqlite_database_path),
                payload=job.payload,
            )
        except Exception as exc:
            queue.mark_failed(job.job_id, str(exc))
        else:
            queue.mark_succeeded(job.job_id)
        processed += 1
    return processed


def _dump_json(value: dict[str, Any]) -> str:
    """把 Python 字典序列化为 JSON 文本。"""

    return json.dumps(value, ensure_ascii=False)


def _load_json(value: Any) -> dict[str, Any]:
    """把 SQLite 返回的 JSON 文本还原为字典。"""

    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, (bytes, bytearray)):
        text = value.decode("utf-8", errors="ignore")
    else:
        text = str(value)
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if isinstance(loaded, dict):
        return dict(loaded)
    return {}


def _utc_now() -> datetime:
    """返回统一的 UTC 当前时间。"""

    return datetime.now(UTC)


def _optional_text(value: Any) -> str | None:
    """把可选字段归一化为字符串或 None。"""

    if value in (None, ""):
        return None
    return str(value)


def record_from(record: JobRecord, **updates: Any) -> JobRecord:
    """基于已有记录生成更新后的不可变作业对象。"""

    payload = record.to_dict()
    payload.update(updates)
    return JobRecord.from_dict(payload)

