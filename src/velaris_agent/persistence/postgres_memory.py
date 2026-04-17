"""PostgreSQL 版决策记忆。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from velaris_agent.memory.decision_memory import (
    DecisionMemory,
    build_decision_index_entry,
    deserialize_decision_record,
    serialize_decision_record,
)
from velaris_agent.memory.types import DecisionRecord
from velaris_agent.persistence.postgres import postgres_connection
from velaris_agent.persistence.psycopg_compat import Jsonb


class PostgresDecisionMemory(DecisionMemory):
    """把决策记录持久化到 PostgreSQL 的最小后端。

    这个实现严格复用 `DecisionMemory` 的查询语义，先把完整记录写入
    `decision_records.payload`，再从 payload 还原出同样的检索行为，
    以保证文件后端与数据库后端在工具层表现一致。
    """

    def __init__(
        self,
        postgres_dsn: str,
        base_dir: str | Path | None = None,
    ) -> None:
        """初始化 PostgreSQL 决策记忆。"""

        self._postgres_dsn = postgres_dsn
        self._base_dir = Path(base_dir) if base_dir is not None else None

    def save(self, record: DecisionRecord) -> str:
        """把决策记录写入 PostgreSQL，并返回决策 ID。"""

        payload = serialize_decision_record(record)
        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into decision_records (record_id, created_at, payload)
                    values (%s, %s, %s)
                    on conflict (record_id) do update set
                      created_at = excluded.created_at,
                      payload = excluded.payload
                    """,
                    (record.decision_id, datetime.now(timezone.utc), Jsonb(payload)),
                )
        return record.decision_id

    def get(self, decision_id: str) -> DecisionRecord | None:
        """按 ID 读取完整决策记录。"""

        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select payload
                    from decision_records
                    where record_id = %s
                    """,
                    (decision_id,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        payload = self._extract_payload(row)
        if payload is None:
            return None
        return deserialize_decision_record(payload)

    def update_feedback(
        self,
        decision_id: str,
        user_choice: dict[str, Any] | None = None,
        user_feedback: float | None = None,
        outcome_notes: str | None = None,
    ) -> DecisionRecord | None:
        """回填用户选择和满意度，并把更新后的 payload 重新写入数据库。"""

        record = self.get(decision_id)
        if record is None:
            return None

        updates: dict[str, Any] = {}
        if user_choice is not None:
            updates["user_choice"] = user_choice
        if user_feedback is not None:
            updates["user_feedback"] = user_feedback
        if outcome_notes is not None:
            updates["outcome_notes"] = outcome_notes

        updated = record.model_copy(update=updates)
        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update decision_records
                    set payload = %s
                    where record_id = %s
                    """,
                    (Jsonb(serialize_decision_record(updated)), decision_id),
                )
        return updated

    def _scan_index_reversed(self) -> list[dict[str, Any]]:
        """从 PostgreSQL 读取最近优先的轻量索引视图。"""

        rows: list[dict[str, Any]] = []
        with postgres_connection(self._postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select payload
                    from decision_records
                    order by created_at desc, record_id desc
                    """
                )
                for row in cursor.fetchall():
                    payload = self._extract_payload(row)
                    if payload is None:
                        continue
                    record = deserialize_decision_record(payload)
                    rows.append(build_decision_index_entry(record))
        return rows

    @staticmethod
    def _extract_payload(row: Any) -> dict[str, Any] | None:
        """从数据库返回行中提取 payload。"""

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
