"""SQLite schema bootstrap 测试。"""

from __future__ import annotations

from pathlib import Path
import sqlite3

from velaris_agent.persistence.schema import (
    EXPECTED_TABLES,
    bootstrap_sqlite_schema,
    build_sqlite_bootstrap_statements,
)
from velaris_agent.persistence.sqlite_helpers import get_project_database_path


def test_build_sqlite_bootstrap_statements_includes_expected_tables() -> None:
    """Bootstrap SQL 应包含全部预期表。"""

    statements = build_sqlite_bootstrap_statements()

    assert len(statements) == len(EXPECTED_TABLES)
    lowered = "\n".join(statements).lower()
    for table_name in EXPECTED_TABLES:
        assert f"create table if not exists {table_name}" in lowered


def test_build_sqlite_bootstrap_statements_exposes_explicit_execution_and_session_columns() -> None:
    """execution / session 应升级为显式结构表，而不是继续只保留 payload。"""

    statements = build_sqlite_bootstrap_statements()
    execution_sql = next(
        statement
        for statement in statements
        if "create table if not exists execution_records" in statement.lower()
    )
    session_sql = next(
        statement
        for statement in statements
        if "create table if not exists session_records" in statement.lower()
    )

    lowered_execution_sql = execution_sql.lower()
    lowered_session_sql = session_sql.lower()

    for fragment in (
        "execution_id text primary key",
        "session_id text",
        "execution_status text not null",
        "gate_status text not null",
        "effective_risk_level text not null",
        "degraded_mode integer not null default 0",
        "audit_status text not null",
        "resume_cursor_json text not null default '{}'",
        "snapshot_json text not null default '{}'",
    ):
        assert fragment in lowered_execution_sql

    for fragment in (
        "session_id text primary key",
        "binding_mode text not null",
        "source_runtime text not null",
        "message_count integer not null default 0",
        "snapshot_json text not null default '{}'",
    ):
        assert fragment in lowered_session_sql


def test_bootstrap_sqlite_schema_creates_all_tables(tmp_path: Path) -> None:
    """bootstrap_sqlite_schema 应能在空库上创建全部表。"""

    database_path = get_project_database_path(tmp_path)
    count = bootstrap_sqlite_schema(database_path)
    assert count == len(EXPECTED_TABLES)

    connection = sqlite3.connect(str(database_path))
    try:
        rows = connection.execute(
            "select name from sqlite_master where type='table' order by name asc"
        ).fetchall()
    finally:
        connection.close()

    tables = {str(row[0]) for row in rows}
    assert set(EXPECTED_TABLES).issubset(tables)

