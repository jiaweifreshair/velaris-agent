"""execution / session PostgreSQL 仓储实现。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from velaris_agent.persistence.postgres import postgres_connection
from velaris_agent.persistence.psycopg_compat import Jsonb
from velaris_agent.velaris.execution_contract import BizExecutionRecord


def _coerce_json(value: Any) -> dict[str, Any]:
    """把数据库返回的 JSON 值稳定转换成普通字典。

    这样无论运行在真实 psycopg、兼容层还是单元测试假对象上，
    仓储都能得到统一的 Python 结构。
    """

    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "items"):
        return dict(value)
    return dict(value)


@dataclass(frozen=True)
class SessionRecord:
    """session 显式主记录。

    该对象承载 session 与 execution 之间的稳定引用边界，
    同时保留最小 snapshot 信息，供后续 session_storage PostgreSQL 化复用。
    """

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

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> "SessionRecord":
        """从数据库查询结果还原 `SessionRecord`。"""

        return cls(
            session_id=str(row[0]),
            binding_mode=str(row[1]),
            source_runtime=str(row[2]),
            summary=str(row[3]),
            message_count=int(row[4]),
            snapshot_json=_coerce_json(row[5]),
            created_at=str(row[6]),
            updated_at=str(row[7]),
        )


class SessionRepository:
    """管理 session 显式主记录的 PostgreSQL 仓储。"""

    def __init__(self, postgres_dsn: str) -> None:
        """保存 PostgreSQL 连接串，供后续读写复用。"""

        self._postgres_dsn = postgres_dsn

    def upsert(self, record: SessionRecord) -> SessionRecord:
        """写入或覆盖 session 主记录，保持 session_id 为稳定主键。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
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
                    values (%s, %s, %s, %s, %s, %s, %s, %s)
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
                        Jsonb(record.snapshot_json),
                        record.created_at,
                        record.updated_at,
                    ),
                )
        return record

    def get(self, session_id: str) -> SessionRecord | None:
        """按 session_id 读取单条 session 主记录。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
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
                    where session_id = %s
                    """,
                    (session_id,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return SessionRecord.from_row(row)

    def latest_by_cwd(self, cwd: str) -> SessionRecord | None:
        """按工作区读取最近一条 session 主记录。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
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
                    where snapshot_json->>'cwd' = %s
                    order by updated_at desc, session_id desc
                    limit 1
                    """,
                    (cwd,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return SessionRecord.from_row(row)

    def list_by_cwd(self, cwd: str) -> list[SessionRecord]:
        """按工作区列出 session 主记录，供 /resume 与 UI 会话列表使用。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
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
                    where snapshot_json->>'cwd' = %s
                    order by updated_at desc, session_id desc
                    """,
                    (cwd,),
                )
                rows = cursor.fetchall()
        return [SessionRecord.from_row(row) for row in rows]


class ExecutionRepository:
    """管理 execution 显式主记录的 PostgreSQL 仓储。"""

    def __init__(self, postgres_dsn: str) -> None:
        """保存 PostgreSQL 连接串，供 execution 主线复用。"""

        self._postgres_dsn = postgres_dsn

    def create(
        self,
        record: BizExecutionRecord,
        *,
        snapshot_json: dict[str, Any] | None = None,
    ) -> BizExecutionRecord:
        """创建 execution 主记录，并保留补充 snapshot_json。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
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
                      resume_cursor,
                      snapshot_json,
                      created_at,
                      updated_at
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                      resume_cursor = excluded.resume_cursor,
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
                        record.degraded_mode,
                        record.audit_status,
                        record.structural_complete,
                        record.constraint_complete,
                        record.goal_complete,
                        Jsonb(record.resume_cursor or {}),
                        Jsonb(snapshot_json or {}),
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
        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update execution_records set
                      execution_status = %s,
                      gate_status = %s,
                      effective_risk_level = %s,
                      degraded_mode = %s,
                      audit_status = %s,
                      structural_complete = %s,
                      constraint_complete = %s,
                      goal_complete = %s,
                      resume_cursor = %s,
                      snapshot_json = %s,
                      updated_at = %s
                    where execution_id = %s
                    """,
                    (
                        execution_status,
                        gate_status,
                        effective_risk_level,
                        degraded_mode,
                        audit_status,
                        structural_complete,
                        constraint_complete,
                        goal_complete,
                        Jsonb(resume_cursor or {}),
                        Jsonb(snapshot_json or {}),
                        resolved_updated_at,
                        execution_id,
                    ),
                )
        return self.get(execution_id)

    def get(self, execution_id: str) -> BizExecutionRecord | None:
        """按 execution_id 读取单条 execution 主记录。"""

        row = self._fetch_single(execution_id)
        if row is None:
            return None
        return self._row_to_execution_record(row)

    def list_by_session(self, session_id: str) -> list[BizExecutionRecord]:
        """按 session_id 列出 execution 主记录，供恢复与追踪使用。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
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
                      resume_cursor,
                      snapshot_json,
                      created_at,
                      updated_at
                    from execution_records
                    where session_id = %s
                    order by created_at asc, execution_id asc
                    """,
                    (session_id,),
                )
                rows = cursor.fetchall()
        return [self._row_to_execution_record(row) for row in rows]

    def _fetch_single(self, execution_id: str) -> tuple[Any, ...] | None:
        """查询单条 execution 记录的原始数据库行。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
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
                      resume_cursor,
                      snapshot_json,
                      created_at,
                      updated_at
                    from execution_records
                    where execution_id = %s
                    """,
                    (execution_id,),
                )
                return cursor.fetchone()

    def _row_to_execution_record(self, row: tuple[Any, ...]) -> BizExecutionRecord:
        """把查询结果还原为 `BizExecutionRecord`。"""

        return BizExecutionRecord(
            execution_id=str(row[0]),
            session_id=None if row[1] is None else str(row[1]),
            scenario=str(row[2]),
            execution_status=str(row[3]),
            gate_status=str(row[4]),
            effective_risk_level=str(row[5]),
            degraded_mode=bool(row[6]),
            audit_status=str(row[7]),
            structural_complete=bool(row[8]),
            constraint_complete=bool(row[9]),
            goal_complete=bool(row[10]),
            resume_cursor=_coerce_json(row[11]),
            created_at=str(row[13]),
            updated_at=str(row[14]),
        )
