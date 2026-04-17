"""PostgreSQL 决策记忆测试。"""

from __future__ import annotations

import builtins
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import importlib
from pathlib import Path
import sys
from typing import Any

import velaris_agent.persistence.postgres_memory as postgres_memory_module
from velaris_agent.memory.types import DecisionRecord
from velaris_agent.persistence.factory import build_decision_memory
from velaris_agent.persistence.postgres_memory import PostgresDecisionMemory
from velaris_agent.persistence.schema import bootstrap_schema


def _make_record(
    decision_id: str = "dec-postgres-001",
    user_id: str = "u-postgres",
    scenario: str = "travel",
    query: str = "北京到上海机票",
    user_choice: dict[str, Any] | None = None,
    user_feedback: float | None = None,
) -> DecisionRecord:
    """构造一条可持久化的决策记录。"""
    return DecisionRecord(
        decision_id=decision_id,
        user_id=user_id,
        scenario=scenario,
        query=query,
        intent={"origin": "北京", "destination": "上海"},
        options_discovered=[
            {"id": "opt-a", "label": "航班A", "scores": {"price": 0.8, "time": 0.6}},
            {"id": "opt-b", "label": "航班B", "scores": {"price": 0.5, "time": 0.9}},
        ],
        options_after_filter=[],
        scores=[
            {"id": "opt-a", "scores": {"price": 0.8, "time": 0.6}},
            {"id": "opt-b", "scores": {"price": 0.5, "time": 0.9}},
        ],
        weights_used={"price": 0.4, "time": 0.35, "comfort": 0.25},
        tools_called=["search_flights"],
        recommended={"id": "opt-a", "label": "航班A"},
        alternatives=[{"id": "opt-b", "label": "航班B"}],
        explanation="航班A更均衡",
        user_choice=user_choice,
        user_feedback=user_feedback,
        created_at=datetime.now(timezone.utc),
    )


class _FakeCursor:
    """用于单元测试的内存版 PostgreSQL 游标。"""

    def __init__(self, rows: dict[str, dict[str, Any]]) -> None:
        self._rows = rows
        self._result: list[Any] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        """按预期的最小 SQL 语义更新或读取内存数据。"""
        params = params or ()
        normalized = " ".join(sql.lower().split())

        if normalized.startswith("insert into decision_records"):
            record_id = str(params[0])
            created_at = params[1]
            payload = params[2]
            payload_obj = getattr(payload, "obj", payload)
            self._rows[record_id] = {
                "record_id": record_id,
                "created_at": created_at,
                "payload": deepcopy(payload_obj),
            }
            self._result = []
            return

        if normalized.startswith("select payload from decision_records where record_id = %s"):
            record_id = str(params[0])
            row = self._rows.get(record_id)
            self._result = [(deepcopy(row["payload"]),)] if row else []
            return

        if normalized.startswith("update decision_records set payload = %s where record_id = %s"):
            payload = params[0]
            record_id = str(params[1])
            row = self._rows.get(record_id)
            if row is not None:
                payload_obj = getattr(payload, "obj", payload)
                row["payload"] = deepcopy(payload_obj)
            self._result = []
            return

        if normalized.startswith("select payload from decision_records order by created_at desc, record_id desc"):
            ordered = sorted(
                self._rows.values(),
                key=lambda item: (item["created_at"], item["record_id"]),
                reverse=True,
            )
            self._result = [(deepcopy(row["payload"]),) for row in ordered]
            return

        if "payload->>'user_id' = %s" in normalized:
            user_id = str(params[0])
            scenario = None
            limit = None
            if "and payload->>'scenario' = %s" in normalized:
                scenario = str(params[1])
                if "limit %s" in normalized:
                    limit = int(params[2])
            elif "limit %s" in normalized:
                limit = int(params[1])

            filtered = [
                row
                for row in sorted(
                    self._rows.values(),
                    key=lambda item: item["created_at"],
                    reverse=True,
                )
                if row["payload"].get("user_id") == user_id
                and (scenario is None or row["payload"].get("scenario") == scenario)
            ]
            if limit is not None:
                filtered = filtered[:limit]
            self._result = [(deepcopy(row["payload"]),) for row in filtered]
            return

        if normalized.startswith("select count(*) from decision_records"):
            user_id = str(params[0])
            scenario = str(params[1]) if len(params) > 1 else None
            count = 0
            for row in self._rows.values():
                payload = row["payload"]
                if payload.get("user_id") != user_id:
                    continue
                if scenario is not None and payload.get("scenario") != scenario:
                    continue
                count += 1
            self._result = [(count,)]
            return

        raise AssertionError(f"未预期的 SQL: {sql}")

    def fetchone(self) -> tuple[Any, ...] | None:
        """返回第一条结果。"""
        if not self._result:
            return None
        return self._result.pop(0)

    def fetchall(self) -> list[tuple[Any, ...]]:
        """返回所有结果。"""
        result = list(self._result)
        self._result = []
        return result

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeConnection:
    """用于单元测试的内存版 PostgreSQL 连接。"""

    def __init__(self, rows: dict[str, dict[str, Any]]) -> None:
        self._rows = rows
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> _FakeCursor:
        """创建伪游标。"""
        return _FakeCursor(self._rows)

    def commit(self) -> None:
        """记录提交动作。"""
        self.committed = True

    def rollback(self) -> None:
        """记录回滚动作。"""
        self.rolled_back = True

    def close(self) -> None:
        """记录关闭动作。"""
        self.closed = True


def test_build_decision_memory_switches_backend(tmp_path: Path) -> None:
    """工厂应在默认文件后端与 PostgreSQL 后端之间切换。"""
    file_memory = build_decision_memory(base_dir=tmp_path / "decisions")
    assert file_memory.__class__.__name__ == "DecisionMemory"

    postgres_memory = build_decision_memory(postgres_dsn="postgresql://example")
    assert isinstance(postgres_memory, PostgresDecisionMemory)


def test_factory_file_backend_does_not_require_postgres_driver(tmp_path: Path, monkeypatch) -> None:
    """仅构建文件后端时不应因为 PostgreSQL 依赖缺失而失败。"""

    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        """阻断 PostgreSQL 相关导入，验证工厂层 lazy import。"""

        if name in {
            "psycopg",
            "velaris_agent.persistence.postgres",
            "velaris_agent.persistence.postgres_memory",
            "velaris_agent.persistence.postgres_runtime",
            "velaris_agent.persistence.job_queue",
        }:
            raise ModuleNotFoundError(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    for module_name in (
        "velaris_agent.persistence.factory",
        "velaris_agent.persistence.job_queue",
        "velaris_agent.persistence.postgres_memory",
        "velaris_agent.persistence.postgres_runtime",
        "velaris_agent.persistence.postgres",
        "velaris_agent.persistence.schema",
        "velaris_agent.persistence",
    ):
        sys.modules.pop(module_name, None)

    factory_module = importlib.import_module("velaris_agent.persistence.factory")

    file_memory = factory_module.build_decision_memory(base_dir=tmp_path / "decisions")

    assert file_memory.__class__.__name__ == "DecisionMemory"


def test_postgres_decision_memory_roundtrip_with_fake_connection(monkeypatch) -> None:
    """PostgreSQL 决策记忆应完成保存、读取、回填和聚合闭环。"""
    rows: dict[str, dict[str, Any]] = {}
    connection = _FakeConnection(rows)

    @contextmanager
    def fake_postgres_connection(dsn: str):
        """伪造 PostgreSQL 事务连接，验证 memory 层行为。"""
        assert dsn == "postgresql://user:pass@localhost:5432/velaris"
        try:
            yield connection
        finally:
            connection.committed = True
            connection.closed = True

    monkeypatch.setattr(
        postgres_memory_module,
        "postgres_connection",
        fake_postgres_connection,
    )

    memory = PostgresDecisionMemory("postgresql://user:pass@localhost:5432/velaris")
    record = _make_record(query="北京 上海 机票")

    saved_id = memory.save(record)
    assert saved_id == record.decision_id

    got = memory.get(saved_id)
    assert got is not None
    assert got.decision_id == record.decision_id
    assert got.recommended == record.recommended

    updated = memory.update_feedback(
        saved_id,
        user_choice={"id": "opt-b", "label": "航班B"},
        user_feedback=4.5,
        outcome_notes="用户最终选择了航班B",
    )
    assert updated is not None
    assert updated.user_choice == {"id": "opt-b", "label": "航班B"}
    assert updated.user_feedback == 4.5
    assert updated.outcome_notes == "用户最终选择了航班B"

    listed = memory.list_by_user("u-postgres", scenario="travel")
    assert [item.decision_id for item in listed] == [saved_id]

    assert memory.count_by_user("u-postgres", scenario="travel") == 1

    similar = memory.recall_similar("u-postgres", "travel", "北京 上海 机票")
    assert [item.decision_id for item in similar] == [saved_id]

    agg = memory.aggregate_outcomes("travel", option_field="id", option_value="opt-b")
    assert agg["times_seen"] == 1
    assert agg["times_chosen"] == 1
    assert agg["sample_size"] == 1
    assert agg["avg_satisfaction"] == 4.5


def test_postgres_decision_memory_recent_order_follows_write_time(monkeypatch) -> None:
    """PostgreSQL 后端的最近优先顺序应跟随写入顺序，而不是 payload.created_at。"""
    rows: dict[str, dict[str, Any]] = {}
    connection = _FakeConnection(rows)

    @contextmanager
    def fake_postgres_connection(dsn: str):
        """伪造 PostgreSQL 事务连接，验证写入顺序。"""
        assert dsn == "postgresql://user:pass@localhost:5432/velaris"
        try:
            yield connection
        finally:
            connection.committed = True
            connection.closed = True

    monkeypatch.setattr(
        postgres_memory_module,
        "postgres_connection",
        fake_postgres_connection,
    )

    memory = PostgresDecisionMemory("postgresql://user:pass@localhost:5432/velaris")

    future_record = _make_record(
        decision_id="dec-order-a",
        user_id="u-order",
        query="未来时间记录",
    ).model_copy(update={"created_at": datetime(2099, 1, 1, tzinfo=timezone.utc)})
    past_record = _make_record(
        decision_id="dec-order-b",
        user_id="u-order",
        query="过去时间记录",
    ).model_copy(update={"created_at": datetime(1999, 1, 1, tzinfo=timezone.utc)})

    memory.save(future_record)
    memory.save(past_record)

    ordered = memory.list_by_user("u-order", scenario="travel")
    assert [item.decision_id for item in ordered] == ["dec-order-b", "dec-order-a"]

    memory.update_feedback(
        "dec-order-a",
        user_choice={"id": "opt-b", "label": "航班B"},
        user_feedback=4.2,
    )
    ordered_after_feedback = memory.list_by_user("u-order", scenario="travel")
    assert [item.decision_id for item in ordered_after_feedback] == [
        "dec-order-b",
        "dec-order-a",
    ]

    memory.save(
        future_record.model_copy(
            update={
                "query": "未来时间记录-更新后",
                "created_at": datetime(1988, 1, 1, tzinfo=timezone.utc),
            }
        )
    )
    ordered_after_resave = memory.list_by_user("u-order", scenario="travel")
    assert [item.decision_id for item in ordered_after_resave] == [
        "dec-order-a",
        "dec-order-b",
    ]
    assert memory.count_by_user("u-order", scenario="travel") == 2
    assert memory.get("dec-order-a").query == "未来时间记录-更新后"


def test_postgres_decision_memory_real_roundtrip(postgres_dsn: str) -> None:
    """真实 PostgreSQL 环境下应能完成最小读写闭环。"""
    bootstrap_schema(postgres_dsn)
    memory = PostgresDecisionMemory(postgres_dsn)
    record = _make_record(decision_id=f"dec-postgres-{datetime.now(timezone.utc).timestamp():.0f}")

    saved_id = memory.save(record)
    assert saved_id == record.decision_id
    assert memory.get(saved_id) is not None
