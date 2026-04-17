"""PostgreSQL 任务队列最小实现。

该模块只依赖 Phase 1 已有的 `job_queue` 表最小 payload schema，
用于把非热路径任务（例如自进化复盘）从同步工具调用中剥离出来。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from velaris_agent.persistence.postgres import postgres_connection
from velaris_agent.persistence.psycopg_compat import Jsonb

SELF_EVOLUTION_REVIEW_JOB_TYPE = "self_evolution_review"


def _run_self_evolution_review_job(*, postgres_dsn: str, payload: dict[str, Any]) -> Any:
    """按需导入并执行自进化 worker。

    这样 `job_queue` 模块本身不会因为 `pydantic` 或其他上层依赖在 import 阶段失败，
    只有真正消费这类任务时才加载完整自进化链路。
    """

    from velaris_agent.evolution.self_evolution import run_self_evolution_review_job

    return run_self_evolution_review_job(postgres_dsn=postgres_dsn, payload=payload)


@dataclass(frozen=True)
class JobRecord:
    """任务队列中的单条作业记录。

    字段全部保存在 `job_queue.payload` 中，
    这样无需新增 schema 就能完成最小的入队、认领和状态回写闭环。
    """

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
    """单次后台任务执行记录。

    `job_queue` 负责表达“当前任务状态”，而 `job_runs` 负责保留每次尝试的历史，
    便于做失败分析、重试诊断和人工重放。
    """

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


class PostgresJobQueue:
    """基于 PostgreSQL 最小 payload schema 的任务队列。"""

    def __init__(self, postgres_dsn: str) -> None:
        """保存 PostgreSQL DSN，供后续队列操作复用。"""

        self._postgres_dsn = postgres_dsn.strip()

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

        created_at = _utc_now()
        job = JobRecord(
            job_id=f"job-{uuid4().hex[:12]}",
            job_type=job_type,
            status="queued",
            idempotency_key=idempotency_key,
            payload=dict(payload),
            attempt_count=0,
            created_at=created_at.isoformat(),
        )
        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into job_queue (record_id, created_at, payload)
                    values (%s, %s, %s)
                    on conflict (record_id) do update set
                      created_at = excluded.created_at,
                      payload = excluded.payload
                    """,
                    (job.job_id, created_at, Jsonb(job.to_dict())),
                )
        return job.job_id

    def claim_next(self, job_types: list[str]) -> JobRecord | None:
        """按创建顺序认领下一条待处理任务。"""

        if not job_types:
            return None

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select record_id, payload
                    from job_queue
                    where coalesce(payload->>'status', 'queued') = 'queued'
                      and payload->>'job_type' = any(%s)
                    order by created_at asc, record_id asc
                    limit 1
                    """,
                    (job_types,),
                )
                row = cursor.fetchone()
        if row is None:
            return None

        record = self._extract_job(row)
        if record is None:
            return None

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
            job_id=job_id,
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
            job_id=job_id,
            run_id=record.current_run_id,
            status="failed",
            finished_at=updated.finished_at,
            last_error=error,
        )
        return updated

    def get(self, job_id: str) -> JobRecord | None:
        """按 job_id 读取任务当前状态。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select payload
                    from job_queue
                    where record_id = %s
                    """,
                    (job_id,),
                )
                row = cursor.fetchone()
        return self._extract_job(row)

    def list_runs(self, job_id: str) -> list[JobRunRecord]:
        """按任务 ID 返回全部执行尝试，供观测与人工诊断使用。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select payload
                    from job_runs
                    where payload->>'job_id' = %s
                    order by created_at asc, record_id asc
                    """,
                    (job_id,),
                )
                rows = cursor.fetchall()
        runs: list[JobRunRecord] = []
        for row in rows:
            payload = _extract_payload(row)
            if payload is not None:
                runs.append(JobRunRecord.from_dict(payload))
        return runs

    def _find_by_idempotency(self, *, job_type: str, idempotency_key: str) -> JobRecord | None:
        """按作业类型与幂等键读取已有任务。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select record_id, payload
                    from job_queue
                    where payload->>'job_type' = %s
                      and payload->>'idempotency_key' = %s
                    order by created_at desc, record_id desc
                    limit 1
                    """,
                    (job_type, idempotency_key),
                )
                row = cursor.fetchone()
        return self._extract_job(row)

    def _update(self, record: JobRecord) -> None:
        """把最新 payload 写回 job_queue。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update job_queue
                    set payload = %s
                    where record_id = %s
                    """,
                    (Jsonb(record.to_dict()), record.job_id),
                )

    def _append_run(self, run: JobRunRecord) -> None:
        """把一次新的 job run 追加到 `job_runs` 表。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into job_runs (record_id, created_at, payload)
                    values (%s, %s, %s)
                    on conflict (record_id) do update set
                      created_at = excluded.created_at,
                      payload = excluded.payload
                    """,
                    (run.run_id, run.started_at, Jsonb(run.to_dict())),
                )

    def _update_run(
        self,
        *,
        job_id: str,
        run_id: str | None,
        status: str,
        finished_at: str | None,
        last_error: str | None,
    ) -> None:
        """回写一次 job run 的最终状态。

        若缺少 `run_id`，说明当前任务是在旧数据或异常状态下结束，
        这里直接跳过，避免把状态修复逻辑本身变成新的失败点。
        """

        if not run_id:
            return

        runs = self.list_runs(job_id)
        run = next((item for item in reversed(runs) if item.run_id == run_id), None)
        if run is None:
            return

        updated = JobRunRecord(
            run_id=run.run_id,
            job_id=run.job_id,
            job_type=run.job_type,
            attempt_count=run.attempt_count,
            status=status,
            started_at=run.started_at,
            finished_at=finished_at,
            last_error=last_error,
        )
        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update job_runs
                    set payload = %s
                    where record_id = %s
                    """,
                    (Jsonb(updated.to_dict()), updated.run_id),
                )

    @staticmethod
    def _extract_job(row: Any) -> JobRecord | None:
        """从数据库结果中提取作业记录。"""

        payload = _extract_payload(row)
        if payload is None:
            return None
        return JobRecord.from_dict(payload)


def run_jobs_once(dsn: str, limit: int = 10) -> int:
    """顺序处理一次队列中的后台任务，并返回处理数量。"""

    queue = PostgresJobQueue(dsn)
    processed = 0
    for _ in range(max(limit, 0)):
        job = queue.claim_next([SELF_EVOLUTION_REVIEW_JOB_TYPE])
        if job is None:
            break
        try:
            if job.job_type != SELF_EVOLUTION_REVIEW_JOB_TYPE:
                raise ValueError(f"unsupported job type: {job.job_type}")
            _run_self_evolution_review_job(postgres_dsn=dsn, payload=job.payload)
        except Exception as exc:
            queue.mark_failed(job.job_id, str(exc))
        else:
            queue.mark_succeeded(job.job_id)
        processed += 1
    return processed


def _extract_payload(row: Any) -> dict[str, Any] | None:
    """从 psycopg 返回结果中提取 payload 字典。"""

    if row is None:
        return None
    if isinstance(row, dict):
        payload = row.get("payload")
    elif isinstance(row, tuple):
        if len(row) >= 2:
            payload = row[1]
        else:
            payload = row[0] if row else None
    else:
        payload = row
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "items"):
        return dict(payload)
    return payload


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
