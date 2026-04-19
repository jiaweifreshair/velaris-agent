"""execution / session SQLite 仓储实现。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

from velaris_agent.persistence.sqlite import sqlite_connection
from velaris_agent.velaris.execution_contract import BizExecutionRecord


def _dump_json(value: dict[str, Any] | None) -> str:
    """把可选 JSON 字典稳定序列化为字符串。"""

    return json.dumps(value or {}, ensure_ascii=False)


def _load_json(value: Any) -> dict[str, Any]:
    """把 SQLite 返回的 JSON 文本稳定还原为普通字典。"""

    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "items"):
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


@dataclass(frozen=True)
class SessionRecord:
    """session 显式主记录。"""

    session_id: str
    binding_mode: str
    source_runtime: str
    summary: str
    message_count: int
    created_at: str
    updated_at: str
    snapshot_json: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 友好的 session 记录结构。"""

        return asdict(self)


class SessionRepository:
    """管理 session 显式主记录的 SQLite 仓储。"""

    def __init__(self, database_path: str) -> None:
        """保存 SQLite 数据库路径，供后续读写复用。"""

        self._database_path = database_path

    def upsert(self, record: SessionRecord) -> SessionRecord:
        """写入或覆盖 session 主记录，保持 session_id 为稳定主键。"""

        with sqlite_connection(self._database_path) as connection:
            connection.execute(
                """
                insert into session_records (
                  session_id,
                  binding_mode,
                  source_runtime,
                  summary,
                  message_count,
                  snapshot_json,
                  created_at,
                  updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict (session_id) do update set
                  binding_mode = excluded.binding_mode,
                  source_runtime = excluded.source_runtime,
                  summary = excluded.summary,
                  message_count = excluded.message_count,
                  snapshot_json = excluded.snapshot_json,
                  created_at = excluded.created_at,
                  updated_at = excluded.updated_at
                """,
                (
                    record.session_id,
                    record.binding_mode,
                    record.source_runtime,
                    record.summary,
                    record.message_count,
                    _dump_json(record.snapshot_json),
                    record.created_at,
                    record.updated_at,
                ),
            )
        return record

    def get(self, session_id: str) -> SessionRecord | None:
        """按 session_id 读取单条 session 主记录。"""

        with sqlite_connection(self._database_path) as connection:
            row = connection.execute(
                """
                select
                  session_id,
                  binding_mode,
                  source_runtime,
                  summary,
                  message_count,
                  snapshot_json,
                  created_at,
                  updated_at
                from session_records
                where session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return SessionRecord(
            session_id=str(row[0]),
            binding_mode=str(row[1]),
            source_runtime=str(row[2]),
            summary=str(row[3]),
            message_count=int(row[4]),
            snapshot_json=_load_json(row[5]),
            created_at=str(row[6]),
            updated_at=str(row[7]),
        )

    def latest_by_cwd(self, cwd: str) -> SessionRecord | None:
        """按工作区读取最近一条 session 主记录。"""

        with sqlite_connection(self._database_path) as connection:
            rows = connection.execute(
                """
                select
                  session_id,
                  binding_mode,
                  source_runtime,
                  summary,
                  message_count,
                  snapshot_json,
                  created_at,
                  updated_at
                from session_records
                order by updated_at desc, session_id desc
                """,
            ).fetchall()

        for row in rows:
            snapshot = _load_json(row[5])
            if str(snapshot.get("cwd", "")) != cwd:
                continue
            return SessionRecord(
                session_id=str(row[0]),
                binding_mode=str(row[1]),
                source_runtime=str(row[2]),
                summary=str(row[3]),
                message_count=int(row[4]),
                snapshot_json=snapshot,
                created_at=str(row[6]),
                updated_at=str(row[7]),
            )
        return None

    def list_by_cwd(self, cwd: str) -> list[SessionRecord]:
        """按工作区列出 session 主记录，供 /resume 与 UI 会话列表使用。"""

        with sqlite_connection(self._database_path) as connection:
            rows = connection.execute(
                """
                select
                  session_id,
                  binding_mode,
                  source_runtime,
                  summary,
                  message_count,
                  snapshot_json,
                  created_at,
                  updated_at
                from session_records
                order by updated_at desc, session_id desc
                """,
            ).fetchall()

        records: list[SessionRecord] = []
        for row in rows:
            snapshot = _load_json(row[5])
            if str(snapshot.get("cwd", "")) != cwd:
                continue
            records.append(
                SessionRecord(
                    session_id=str(row[0]),
                    binding_mode=str(row[1]),
                    source_runtime=str(row[2]),
                    summary=str(row[3]),
                    message_count=int(row[4]),
                    snapshot_json=snapshot,
                    created_at=str(row[6]),
                    updated_at=str(row[7]),
                )
            )
        return records


class ExecutionRepository:
    """管理 execution 显式主记录的 SQLite 仓储。"""

    def __init__(self, database_path: str) -> None:
        """保存 SQLite 数据库路径，供 execution 主线复用。"""

        self._database_path = database_path

    def create(
        self,
        record: BizExecutionRecord,
        *,
        snapshot_json: dict[str, Any] | None = None,
    ) -> BizExecutionRecord:
        """创建 execution 主记录，并保留补充 snapshot_json。"""

        with sqlite_connection(self._database_path) as connection:
            connection.execute(
                """
                insert into execution_records (
                  execution_id,
                  session_id,
                  scenario,
                  execution_status,
                  gate_status,
                  effective_risk_level,
                  degraded_mode,
                  audit_status,
                  structural_complete,
                  constraint_complete,
                  goal_complete,
                  resume_cursor_json,
                  snapshot_json,
                  created_at,
                  updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict (execution_id) do update set
                  session_id = excluded.session_id,
                  scenario = excluded.scenario,
                  execution_status = excluded.execution_status,
                  gate_status = excluded.gate_status,
                  effective_risk_level = excluded.effective_risk_level,
                  degraded_mode = excluded.degraded_mode,
                  audit_status = excluded.audit_status,
                  structural_complete = excluded.structural_complete,
                  constraint_complete = excluded.constraint_complete,
                  goal_complete = excluded.goal_complete,
                  resume_cursor_json = excluded.resume_cursor_json,
                  snapshot_json = excluded.snapshot_json,
                  created_at = excluded.created_at,
                  updated_at = excluded.updated_at
                """,
                (
                    record.execution_id,
                    record.session_id,
                    record.scenario,
                    record.execution_status,
                    record.gate_status,
                    record.effective_risk_level,
                    1 if record.degraded_mode else 0,
                    record.audit_status,
                    1 if record.structural_complete else 0,
                    1 if record.constraint_complete else 0,
                    1 if record.goal_complete else 0,
                    _dump_json(record.resume_cursor or {}),
                    _dump_json(snapshot_json),
                    record.created_at,
                    record.updated_at,
                ),
            )
        return record

    def update_status(
        self,
        execution_id: str,
        *,
        execution_status: str,
        gate_status: str,
        effective_risk_level: str,
        degraded_mode: bool,
        audit_status: str,
        structural_complete: bool,
        constraint_complete: bool,
        goal_complete: bool,
        resume_cursor: dict[str, Any] | None = None,
        snapshot_json: dict[str, Any] | None = None,
        updated_at: str | None = None,
    ) -> BizExecutionRecord | None:
        """推进 execution 主状态、completion 派生字段与审计状态。"""

        current = self.get(execution_id)
        if current is None:
            return None

        resolved_updated_at = updated_at or current.updated_at
        with sqlite_connection(self._database_path) as connection:
            connection.execute(
                """
                update execution_records set
                  execution_status = ?,
                  gate_status = ?,
                  effective_risk_level = ?,
                  degraded_mode = ?,
                  audit_status = ?,
                  structural_complete = ?,
                  constraint_complete = ?,
                  goal_complete = ?,
                  resume_cursor_json = ?,
                  snapshot_json = ?,
                  updated_at = ?
                where execution_id = ?
                """,
                (
                    execution_status,
                    gate_status,
                    effective_risk_level,
                    1 if degraded_mode else 0,
                    audit_status,
                    1 if structural_complete else 0,
                    1 if constraint_complete else 0,
                    1 if goal_complete else 0,
                    _dump_json(resume_cursor),
                    _dump_json(snapshot_json),
                    resolved_updated_at,
                    execution_id,
                ),
            )
        return self.get(execution_id)

    def get(self, execution_id: str) -> BizExecutionRecord | None:
        """按 execution_id 读取单条 execution 主记录。"""

        with sqlite_connection(self._database_path) as connection:
            row = connection.execute(
                """
                select
                  execution_id,
                  session_id,
                  scenario,
                  execution_status,
                  gate_status,
                  effective_risk_level,
                  degraded_mode,
                  audit_status,
                  structural_complete,
                  constraint_complete,
                  goal_complete,
                  resume_cursor_json,
                  snapshot_json,
                  created_at,
                  updated_at
                from execution_records
                where execution_id = ?
                """,
                (execution_id,),
            ).fetchone()
        if row is None:
            return None
        return BizExecutionRecord(
            execution_id=str(row[0]),
            session_id=None if row[1] is None else str(row[1]),
            scenario=str(row[2]),
            execution_status=str(row[3]),
            gate_status=str(row[4]),
            effective_risk_level=str(row[5]),
            degraded_mode=bool(int(row[6])),
            audit_status=str(row[7]),
            structural_complete=bool(int(row[8])),
            constraint_complete=bool(int(row[9])),
            goal_complete=bool(int(row[10])),
            resume_cursor=_load_json(row[11]),
            created_at=str(row[13]),
            updated_at=str(row[14]),
        )

    def list_by_session(self, session_id: str) -> list[BizExecutionRecord]:
        """按 session_id 列出 execution 主记录，供恢复与追踪使用。"""

        with sqlite_connection(self._database_path) as connection:
            rows = connection.execute(
                """
                select
                  execution_id,
                  session_id,
                  scenario,
                  execution_status,
                  gate_status,
                  effective_risk_level,
                  degraded_mode,
                  audit_status,
                  structural_complete,
                  constraint_complete,
                  goal_complete,
                  resume_cursor_json,
                  snapshot_json,
                  created_at,
                  updated_at
                from execution_records
                where session_id = ?
                order by created_at asc, execution_id asc
                """,
                (session_id,),
            ).fetchall()

        records: list[BizExecutionRecord] = []
        for row in rows:
            records.append(
                BizExecutionRecord(
                    execution_id=str(row[0]),
                    session_id=None if row[1] is None else str(row[1]),
                    scenario=str(row[2]),
                    execution_status=str(row[3]),
                    gate_status=str(row[4]),
                    effective_risk_level=str(row[5]),
                    degraded_mode=bool(int(row[6])),
                    audit_status=str(row[7]),
                    structural_complete=bool(int(row[8])),
                    constraint_complete=bool(int(row[9])),
                    goal_complete=bool(int(row[10])),
                    resume_cursor=_load_json(row[11]),
                    created_at=str(row[13]),
                    updated_at=str(row[14]),
                )
            )
        return records
