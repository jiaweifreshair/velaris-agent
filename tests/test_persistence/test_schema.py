"""存储 schema bootstrap 测试。"""

from __future__ import annotations

import builtins
from contextlib import contextmanager
import importlib
import sys

from velaris_agent.persistence.schema import EXPECTED_TABLES, build_bootstrap_statements


def test_build_bootstrap_statements_includes_expected_tables():
    """Bootstrap SQL 应包含全部预期表。"""

    statements = build_bootstrap_statements()

    assert len(statements) == len(EXPECTED_TABLES)
    lowered = "\n".join(statements).lower()
    for table_name in EXPECTED_TABLES:
        assert f"create table if not exists {table_name}" in lowered


def test_build_bootstrap_statements_exposes_explicit_execution_and_session_columns():
    """execution / session 应升级为显式结构表，而不是继续只保留 payload。"""

    statements = build_bootstrap_statements()
    execution_sql = next(
        statement for statement in statements if "create table if not exists execution_records" in statement.lower()
    )
    session_sql = next(
        statement for statement in statements if "create table if not exists session_records" in statement.lower()
    )

    lowered_execution_sql = execution_sql.lower()
    lowered_session_sql = session_sql.lower()

    for fragment in (
        "execution_id text primary key",
        "session_id text",
        "execution_status text not null",
        "gate_status text not null",
        "effective_risk_level text not null",
        "degraded_mode boolean not null default false",
        "audit_status text not null",
        "resume_cursor jsonb not null default '{}'::jsonb",
        "snapshot_json jsonb not null default '{}'::jsonb",
    ):
        assert fragment in lowered_execution_sql

    for fragment in (
        "session_id text primary key",
        "binding_mode text not null",
        "source_runtime text not null",
        "message_count integer not null default 0",
        "snapshot_json jsonb not null default '{}'::jsonb",
    ):
        assert fragment in lowered_session_sql


def test_persistence_package_import_does_not_require_postgres_driver(monkeypatch):
    """仅导入 persistence 包并生成 bootstrap SQL 时不应强依赖 psycopg。"""

    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        """阻断 PostgreSQL 相关导入，验证 lazy import 边界。"""

        if name in {
            "psycopg",
            "velaris_agent.persistence.postgres",
        }:
            raise ModuleNotFoundError(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    for module_name in (
        "velaris_agent.persistence.schema",
        "velaris_agent.persistence",
        "velaris_agent.persistence.postgres",
    ):
        sys.modules.pop(module_name, None)

    persistence_module = importlib.import_module("velaris_agent.persistence")

    statements = persistence_module.build_bootstrap_statements()

    assert len(statements) == len(persistence_module.EXPECTED_TABLES)


def test_bootstrap_schema_executes_all_statements(monkeypatch):
    """bootstrap_schema 应逐条执行所有 bootstrap SQL。"""

    executed: list[str] = []

    class DummyCursor:
        def execute(self, sql: str) -> None:
            executed.append(sql)

        def __enter__(self) -> "DummyCursor":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    class DummyConnection:
        def __init__(self) -> None:
            self.committed = False
            self.rolled_back = False

        def cursor(self) -> DummyCursor:
            return DummyCursor()

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            self.rolled_back = True

        def __enter__(self) -> "DummyConnection":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    connection = DummyConnection()

    @contextmanager
    def fake_postgres_connection(dsn: str):
        assert dsn == "postgresql://user:pass@localhost:5432/velaris"
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()

    monkeypatch.setattr(
        "velaris_agent.persistence.schema._load_postgres_connection",
        lambda: fake_postgres_connection,
    )

    from velaris_agent.persistence.schema import bootstrap_schema

    count = bootstrap_schema("postgresql://user:pass@localhost:5432/velaris")

    assert count == len(EXPECTED_TABLES)
    assert executed == build_bootstrap_statements()
    assert connection.committed is True
    assert connection.rolled_back is False
