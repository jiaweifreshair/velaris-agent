"""存储 schema bootstrap 定义。"""

from __future__ import annotations

EXPECTED_TABLES = [
    "decision_records",
    "task_ledger_records",
    "outcome_records",
    "audit_events",
    "job_queue",
    "job_runs",
]


def _build_table_statement(table_name: str) -> str:
    """生成单表 bootstrap SQL。

    这些表先只保留统一的最小列集合，确保 Phase 1 可以完成 schema 落地，
    后续任务再按业务需要逐步补充细节字段。
    """

    return (
        f"create table if not exists {table_name} (\n"
        "  record_id text primary key,\n"
        "  created_at timestamptz not null default now(),\n"
        "  payload jsonb not null default '{}'::jsonb\n"
        ");"
    )


def build_bootstrap_statements() -> list[str]:
    """返回 Phase 1 需要执行的 PostgreSQL bootstrap SQL 列表。"""

    return [_build_table_statement(table_name) for table_name in EXPECTED_TABLES]


def _load_postgres_connection():
    """按需加载 PostgreSQL 事务上下文。

    这样仅生成 SQL 或导入 persistence 包时，不会在 import 阶段硬依赖 psycopg。
    """

    from velaris_agent.persistence.postgres import postgres_connection

    return postgres_connection


def bootstrap_schema(dsn: str) -> int:
    """把最小持久化 schema 写入 PostgreSQL，并返回执行条数。"""

    statements = build_bootstrap_statements()
    postgres_connection = _load_postgres_connection()
    with postgres_connection(dsn) as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
    return len(statements)
