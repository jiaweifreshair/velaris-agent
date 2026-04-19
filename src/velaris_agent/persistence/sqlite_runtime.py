"""Velaris 运行时 SQLite 仓储。

该模块把 Task Ledger、Outcome Store 与 Audit Event 三类运行时记录
统一落到 SQLite 的最小 payload schema 上：
- 仅保证可持久化与按 session 列表读取；
- 不依赖 SQLite JSON1 扩展，所有过滤都在 Python 层完成；
- 先追求“可用 + 可测”，后续再按性能需求补索引或显式列。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from typing import Any
from uuid import uuid4

from velaris_agent.persistence.sqlite import sqlite_connection
from velaris_agent.velaris.outcome_store import OutcomeRecord, OutcomeStore
from velaris_agent.velaris.payload_redactor import PayloadRedactor
from velaris_agent.velaris.task_ledger import TaskLedger, TaskLedgerRecord


def _dump_json(payload: dict[str, Any]) -> str:
    """把 payload 字典序列化为 JSON 字符串。"""

    return json.dumps(payload, ensure_ascii=False)


def _load_json(value: Any) -> dict[str, Any] | None:
    """把 SQLite 返回的 JSON 字符串还原为字典。"""

    if value in (None, ""):
        return None
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, (bytes, bytearray)):
        text = value.decode("utf-8", errors="ignore")
    else:
        text = str(value)
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(loaded, dict):
        return dict(loaded)
    return None


def _to_timestamp(value: Any) -> str:
    """把时间字段稳定归一化为 ISO 字符串。"""

    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


@dataclass(frozen=True)
class AuditEventRecord:
    """运行时审计事件记录。"""

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
        """从持久化 payload 还原审计事件。"""

        return cls(
            event_id=str(payload["event_id"]),
            session_id=str(payload["session_id"]),
            step_name=str(payload["step_name"]),
            operator_id=str(payload["operator_id"]),
            payload=dict(payload.get("payload", {})),
            created_at=str(payload.get("created_at", "")),
        )


class _SqlitePayloadStore:
    """最小 payload 表访问基类。"""

    def __init__(self, database_path: str, table_name: str) -> None:
        """保存 SQLite 路径与目标表名，供子类复用。"""

        self._database_path = database_path
        self._table_name = table_name
        self._payload_redactor = PayloadRedactor()

    def _upsert_payload(self, record_id: str, created_at: Any, payload: dict[str, Any]) -> None:
        """按最小 schema 写入或覆盖一条 payload 记录。"""

        with sqlite_connection(self._database_path) as connection:
            connection.execute(
                f"""
                insert into {self._table_name} (record_id, created_at, payload_json)
                values (?, ?, ?)
                on conflict (record_id) do update set
                  created_at = excluded.created_at,
                  payload_json = excluded.payload_json
                """,
                (record_id, _to_timestamp(created_at), _dump_json(payload)),
            )

    def _update_payload(self, record_id: str, payload: dict[str, Any]) -> None:
        """仅更新 payload 内容，保留原始创建时间排序。"""

        with sqlite_connection(self._database_path) as connection:
            connection.execute(
                f"""
                update {self._table_name}
                set payload_json = ?
                where record_id = ?
                """,
                (_dump_json(payload), record_id),
            )

    def _fetch_payload(self, record_id: str) -> dict[str, Any] | None:
        """按 record_id 读取单条 payload。"""

        with sqlite_connection(self._database_path) as connection:
            row = connection.execute(
                f"""
                select payload_json
                from {self._table_name}
                where record_id = ?
                """,
                (record_id,),
            ).fetchone()
        if row is None:
            return None
        return _load_json(row[0])

    def _list_payloads_by_session(self, session_id: str) -> list[dict[str, Any]]:
        """按 session_id 读取最小时间顺序的 payload 列表。"""

        with sqlite_connection(self._database_path) as connection:
            rows = connection.execute(
                f"""
                select payload_json
                from {self._table_name}
                order by created_at asc, record_id asc
                """
            ).fetchall()

        payloads: list[dict[str, Any]] = []
        for row in rows:
            payload = _load_json(row[0])
            if payload is None:
                continue
            if str(payload.get("session_id", "")) != session_id:
                continue
            payloads.append(payload)
        return payloads


class SqliteTaskLedger(TaskLedger, _SqlitePayloadStore):
    """把任务账本持久化到 SQLite 的最小实现。"""

    def __init__(self, database_path: str) -> None:
        """初始化 SQLite 任务账本。"""

        _SqlitePayloadStore.__init__(self, str(database_path), table_name="task_ledger_records")

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
        """更新任务状态，并把最新快照写回 SQLite。"""

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


class SqliteOutcomeStore(OutcomeStore, _SqlitePayloadStore):
    """把 Outcome Store 持久化到 SQLite 的最小实现。"""

    def __init__(self, database_path: str) -> None:
        """初始化 SQLite outcome 仓储。"""

        _SqlitePayloadStore.__init__(self, str(database_path), table_name="outcome_records")

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
        redacted_metrics = self._payload_redactor.redact_mapping(metrics or {})
        record = OutcomeRecord(
            session_id=session_id,
            scenario=scenario,
            selected_strategy=selected_strategy,
            success=success,
            reason_codes=reason_codes,
            summary=self._payload_redactor.redact_text(summary),
            metrics=redacted_metrics,
            created_at=created_at_value.isoformat(),
        )
        record_id = f"outcome-{uuid4().hex[:12]}"
        self._upsert_payload(record_id, created_at_value, record.to_dict())
        return record

    def list_by_session(self, session_id: str) -> list[OutcomeRecord]:
        """按会话读取 outcome 列表，用于回放一次业务执行的结论。"""

        return [OutcomeRecord.from_dict(payload) for payload in self._list_payloads_by_session(session_id)]


class SqliteAuditEventStore(_SqlitePayloadStore):
    """把运行时审计事件持久化到 SQLite 的最小实现。"""

    def __init__(self, database_path: str) -> None:
        """初始化 SQLite 审计事件仓储。"""

        super().__init__(str(database_path), table_name="audit_events")

    def append_event(
        self,
        session_id: str,
        step_name: str,
        operator_id: str,
        payload: dict[str, Any] | None = None,
    ) -> AuditEventRecord:
        """追加一条审计事件，记录编排关键步骤发生了什么。"""

        created_at_value = datetime.now(UTC)
        redacted_payload = self._payload_redactor.redact_mapping(payload or {})
        event = AuditEventRecord(
            event_id=f"audit-{uuid4().hex[:12]}",
            session_id=session_id,
            step_name=step_name,
            operator_id=operator_id,
            payload=redacted_payload,
            created_at=created_at_value.isoformat(),
        )
        self._upsert_payload(event.event_id, created_at_value, event.to_dict())
        return event

    def list_by_session(self, session_id: str) -> list[AuditEventRecord]:
        """按会话列出审计事件，便于恢复最小执行轨迹。"""

        return [AuditEventRecord.from_dict(payload) for payload in self._list_payloads_by_session(session_id)]
