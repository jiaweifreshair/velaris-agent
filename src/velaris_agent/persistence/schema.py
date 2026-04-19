"""SQLite 主线 schema bootstrap 定义。"""

from __future__ import annotations

from pathlib import Path

EXPECTED_TABLES = [
    "decision_records",
    "session_records",
    "execution_records",
    "task_ledger_records",
    "outcome_records",
    "audit_events",
    "job_queue",
    "job_runs",
]


def _build_payload_table_statement(table_name: str) -> str:
    """生成 payload 风格表的 bootstrap SQL。

    SQLite 主线暂时保持“最小表 + payload_json”策略：
    - 表结构只提供 record_id / created_at / payload_json 三个字段；
    - 任何过滤或提取都在 Python 层完成，避免依赖 SQLite JSON1 扩展。
    """

    return (
        f"create table if not exists {table_name} (\n"
        "  record_id text primary key,\n"
        "  created_at text not null,\n"
        "  payload_json text not null\n"
        ");"
    )


def _build_session_table_statement() -> str:
    """生成 session 主表 bootstrap SQL。"""

    return (
        "create table if not exists session_records (\n"
        "  session_id text primary key,\n"
        "  binding_mode text not null,\n"
        "  source_runtime text not null,\n"
        "  summary text not null default '',\n"
        "  message_count integer not null default 0,\n"
        "  snapshot_json text not null default '{}',\n"
        "  created_at text not null,\n"
        "  updated_at text not null\n"
        ");"
    )


def _build_execution_table_statement() -> str:
    """生成 execution 主表 bootstrap SQL。"""

    return (
        "create table if not exists execution_records (\n"
        "  execution_id text primary key,\n"
        "  session_id text,\n"
        "  scenario text not null,\n"
        "  execution_status text not null,\n"
        "  gate_status text not null,\n"
        "  effective_risk_level text not null,\n"
        "  degraded_mode integer not null default 0,\n"
        "  audit_status text not null,\n"
        "  structural_complete integer not null default 0,\n"
        "  constraint_complete integer not null default 0,\n"
        "  goal_complete integer not null default 0,\n"
        "  resume_cursor_json text not null default '{}',\n"
        "  snapshot_json text not null default '{}',\n"
        "  created_at text not null,\n"
        "  updated_at text not null,\n"
        "  constraint fk_execution_session\n"
        "    foreign key (session_id) references session_records(session_id)\n"
        ");"
    )


def _build_job_queue_table_statement() -> str:
    """生成 job_queue 表 bootstrap SQL。"""

    return (
        "create table if not exists job_queue (\n"
        "  job_id text primary key,\n"
        "  job_type text not null,\n"
        "  status text not null,\n"
        "  idempotency_key text not null,\n"
        "  payload_json text not null,\n"
        "  attempt_count integer not null,\n"
        "  created_at text not null,\n"
        "  claimed_at text,\n"
        "  finished_at text,\n"
        "  last_error text,\n"
        "  current_run_id text\n"
        ");"
    )


def _build_job_runs_table_statement() -> str:
    """生成 job_runs 表 bootstrap SQL。"""

    return (
        "create table if not exists job_runs (\n"
        "  run_id text primary key,\n"
        "  job_id text not null,\n"
        "  job_type text not null,\n"
        "  attempt_count integer not null,\n"
        "  status text not null,\n"
        "  started_at text not null,\n"
        "  finished_at text,\n"
        "  last_error text,\n"
        "  created_at text not null,\n"
        "  constraint fk_job_runs_job\n"
        "    foreign key (job_id) references job_queue(job_id)\n"
        ");"
    )


def build_sqlite_bootstrap_statements() -> list[str]:
    """返回 SQLite 主线需要执行的 bootstrap SQL 列表。"""

    statements: list[str] = []
    for table_name in EXPECTED_TABLES:
        if table_name == "session_records":
            statements.append(_build_session_table_statement())
            continue
        if table_name == "execution_records":
            statements.append(_build_execution_table_statement())
            continue
        if table_name == "job_queue":
            statements.append(_build_job_queue_table_statement())
            continue
        if table_name == "job_runs":
            statements.append(_build_job_runs_table_statement())
            continue
        statements.append(_build_payload_table_statement(table_name))
    return statements


def bootstrap_sqlite_schema(database_path: str | Path) -> int:
    """把最小持久化 schema 写入 SQLite，并返回执行条数。"""

    from velaris_agent.persistence.sqlite import sqlite_connection

    statements = build_sqlite_bootstrap_statements()
    with sqlite_connection(database_path) as connection:
        for statement in statements:
            connection.execute(statement)
    return len(statements)

