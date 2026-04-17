"""Velaris 运行时 PostgreSQL 仓储。

这个模块把 Task Ledger、Outcome Store 与 Audit Event 三类运行时记录
统一落到 Phase 1 已有的最小 payload schema 上，避免引入额外中间件。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from velaris_agent.persistence.postgres import postgres_connection
from velaris_agent.persistence.psycopg_compat import Jsonb
from velaris_agent.velaris.outcome_store import OutcomeRecord, OutcomeStore
from velaris_agent.velaris.task_ledger import TaskLedger, TaskLedgerRecord


@dataclass(frozen=True)
class AuditEventRecord:
    """运行时审计事件记录。

    该记录描述编排器在关键步骤留下的最小审计痕迹，
    便于后续按 session 回放闭环而不提前设计复杂审计模型。
    """

    event_id: str
    session_id: str
    step_name: str
    operator_id: str
    payload: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        """把审计事件转换为 JSON 友好的字典。"""

        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AuditEventRecord":
        """从持久化 payload 还原审计事件。

        统一走 dataclass 还原，确保数据库后端与调用方看到的结构稳定一致。
        """

        return cls(
            event_id=str(payload["event_id"]),
            session_id=str(payload["session_id"]),
            step_name=str(payload["step_name"]),
            operator_id=str(payload["operator_id"]),
            payload=dict(payload.get("payload", {})),
            created_at=str(payload.get("created_at", "")),
        )


class _PostgresPayloadStore:
    """最小 payload 表访问基类。

    它只负责统一执行“按 record_id 写入/读取、按 session_id 列表查询”的 SQL，
    让各运行时仓储专注于记录模型本身。
    """

    def __init__(self, postgres_dsn: str, table_name: str) -> None:
        """保存连接串与目标表名，供子类复用。"""

        self._postgres_dsn = postgres_dsn
        self._table_name = table_name

    def _upsert_payload(self, record_id: str, created_at: Any, payload: dict[str, Any]) -> None:
        """按最小 schema 写入或覆盖一条 payload 记录。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    insert into {self._table_name} (record_id, created_at, payload)
                    values (%s, %s, %s)
                    on conflict (record_id) do update set
                      created_at = excluded.created_at,
                      payload = excluded.payload
                    """,
                    (record_id, created_at, Jsonb(payload)),
                )

    def _update_payload(self, record_id: str, payload: dict[str, Any]) -> None:
        """仅更新 payload 内容，保留原始创建时间排序。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    update {self._table_name}
                    set payload = %s
                    where record_id = %s
                    """,
                    (Jsonb(payload), record_id),
                )

    def _fetch_payload(self, record_id: str) -> dict[str, Any] | None:
        """按 record_id 读取单条 payload。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select payload
                    from {self._table_name}
                    where record_id = %s
                    """,
                    (record_id,),
                )
                row = cursor.fetchone()
        return self._extract_payload(row)

    def _list_payloads_by_session(self, session_id: str) -> list[dict[str, Any]]:
        """按 session_id 读取最小时间顺序的 payload 列表。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select payload
                    from {self._table_name}
                    where payload->>'session_id' = %s
                    order by created_at asc, record_id asc
                    """,
                    (session_id,),
                )
                rows = cursor.fetchall()
        payloads: list[dict[str, Any]] = []
        for row in rows:
            payload = self._extract_payload(row)
            if payload is not None:
                payloads.append(payload)
        return payloads

    @staticmethod
    def _extract_payload(row: Any) -> dict[str, Any] | None:
        """从 psycopg 返回结果中提取 payload 字典。"""

        if row is None:
            return None
        if isinstance(row, dict):
            payload = row.get("payload")
        elif isinstance(row, tuple):
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


class PostgresTaskLedger(TaskLedger, _PostgresPayloadStore):
    """把任务账本持久化到 PostgreSQL 的最小实现。

    该实现复用 `TaskLedgerRecord` 作为唯一领域模型，保证编排器无需感知后端变化。
    """

    def __init__(self, postgres_dsn: str) -> None:
        """初始化 PostgreSQL 任务账本。"""

        _PostgresPayloadStore.__init__(self, postgres_dsn, table_name="task_ledger_records")

    def create_task(
        self,
        session_id: str,
        runtime: str,
        role: str,
        objective: str,
        depends_on: list[str] | None = None,
    ) -> TaskLedgerRecord:
        """创建任务并落库，保持与内存账本一致的默认状态。"""

        created_at_value = datetime.now(UTC)
        timestamp = created_at_value.isoformat()
        task = TaskLedgerRecord(
            task_id=f"task-{uuid4().hex[:12]}",
            session_id=session_id,
            runtime=runtime,
            role=role,
            objective=objective,
            status="queued",
            depends_on=depends_on or [],
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._upsert_payload(task.task_id, created_at_value, task.to_dict())
        return task

    def update_status(self, task_id: str, status: str, error: str | None = None) -> TaskLedgerRecord | None:
        """更新任务状态，并把最新快照写回 PostgreSQL。"""

        payload = self._fetch_payload(task_id)
        if payload is None:
            return None
        task = TaskLedgerRecord.from_dict(payload)
        task.status = status
        task.error = error
        task.updated_at = datetime.now(UTC).isoformat()
        self._update_payload(task_id, task.to_dict())
        return task

    def get_task(self, task_id: str) -> TaskLedgerRecord | None:
        """按任务 ID 读取最新任务快照。"""

        payload = self._fetch_payload(task_id)
        if payload is None:
            return None
        return TaskLedgerRecord.from_dict(payload)

    def list_by_session(self, session_id: str) -> list[TaskLedgerRecord]:
        """按会话列出任务快照，便于编排器回放执行过程。"""

        return [TaskLedgerRecord.from_dict(payload) for payload in self._list_payloads_by_session(session_id)]


class PostgresOutcomeStore(OutcomeStore, _PostgresPayloadStore):
    """把 Outcome Store 持久化到 PostgreSQL 的最小实现。

    它只保存 outcome 完整快照，不做额外聚合，以满足当前 Phase 的闭环目标。
    """

    def __init__(self, postgres_dsn: str) -> None:
        """初始化 PostgreSQL outcome 仓储。"""

        _PostgresPayloadStore.__init__(self, postgres_dsn, table_name="outcome_records")

    def record(
        self,
        session_id: str,
        scenario: str,
        selected_strategy: str,
        success: bool,
        reason_codes: list[str],
        summary: str,
        metrics: dict[str, Any] | None = None,
    ) -> OutcomeRecord:
        """写入一条 outcome 快照并返回标准化记录。"""

        created_at_value = datetime.now(UTC)
        record = OutcomeRecord(
            session_id=session_id,
            scenario=scenario,
            selected_strategy=selected_strategy,
            success=success,
            reason_codes=reason_codes,
            summary=summary,
            metrics=metrics or {},
            created_at=created_at_value.isoformat(),
        )
        record_id = f"outcome-{uuid4().hex[:12]}"
        self._upsert_payload(record_id, created_at_value, record.to_dict())
        return record

    def list_by_session(self, session_id: str) -> list[OutcomeRecord]:
        """按会话读取 outcome 列表，用于回放一次业务执行的结论。"""

        return [OutcomeRecord.from_dict(payload) for payload in self._list_payloads_by_session(session_id)]


class AuditEventStore(_PostgresPayloadStore):
    """把运行时审计事件持久化到 PostgreSQL 的最小实现。

    它专注记录关键步骤事件，当前只提供 append/list 两个能力，避免过度设计。
    """

    def __init__(self, postgres_dsn: str) -> None:
        """初始化 PostgreSQL 审计事件仓储。"""

        super().__init__(postgres_dsn, table_name="audit_events")

    def append_event(
        self,
        session_id: str,
        step_name: str,
        operator_id: str,
        payload: dict[str, Any] | None = None,
    ) -> AuditEventRecord:
        """追加一条审计事件，记录编排关键步骤发生了什么。"""

        created_at_value = datetime.now(UTC)
        event = AuditEventRecord(
            event_id=f"audit-{uuid4().hex[:12]}",
            session_id=session_id,
            step_name=step_name,
            operator_id=operator_id,
            payload=payload or {},
            created_at=created_at_value.isoformat(),
        )
        self._upsert_payload(event.event_id, created_at_value, event.to_dict())
        return event

    def list_by_session(self, session_id: str) -> list[AuditEventRecord]:
        """按会话列出审计事件，便于恢复最小执行轨迹。"""

        return [AuditEventRecord.from_dict(payload) for payload in self._list_payloads_by_session(session_id)]
