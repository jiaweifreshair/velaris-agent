"""存储 schema bootstrap 定义。"""

from __future__ import annotations

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

    对尚未升级为显式结构的表，先保留统一最小列集合，
    以便在不破坏现有运行时仓储的前提下平滑推进本单元改造。
    """

    return (
        f"create table if not exists {table_name} (\n"
        "  record_id text primary key,\n"
        "  created_at timestamptz not null default now(),\n"
        "  payload jsonb not null default '{}'::jsonb\n"
        ");"
    )


def _build_session_table_statement() -> str:
    """生成 session 主表 bootstrap SQL。

    session 在 UOW-1 中先承担“显式 reference + snapshot 锚点”的职责，
    把主键、绑定模式和运行时来源提升为显式列，其余上下文保留在 `snapshot_json`。
    """

    return (
        "create table if not exists session_records (\n"
        "  session_id text primary key,\n"
        "  binding_mode text not null,\n"
        "  source_runtime text not null,\n"
        "  summary text not null default '',\n"
        "  message_count integer not null default 0,\n"
        "  snapshot_json jsonb not null default '{}'::jsonb,\n"
        "  created_at timestamptz not null default now(),\n"
        "  updated_at timestamptz not null default now()\n"
        ");"
    )


def _build_execution_table_statement() -> str:
    """生成 execution 主表 bootstrap SQL。

    execution 是本单元的一等主实体，因此把状态、风险、completion 派生字段和恢复锚点
    明确提升为显式列，避免主语义继续只存在于弱结构 JSON 中。
    """

    return (
        "create table if not exists execution_records (\n"
        "  execution_id text primary key,\n"
        "  session_id text,\n"
        "  scenario text not null,\n"
        "  execution_status text not null,\n"
        "  gate_status text not null,\n"
        "  effective_risk_level text not null,\n"
        "  degraded_mode boolean not null default false,\n"
        "  audit_status text not null,\n"
        "  structural_complete boolean not null default false,\n"
        "  constraint_complete boolean not null default false,\n"
        "  goal_complete boolean not null default false,\n"
        "  resume_cursor jsonb not null default '{}'::jsonb,\n"
        "  snapshot_json jsonb not null default '{}'::jsonb,\n"
        "  created_at timestamptz not null default now(),\n"
        "  updated_at timestamptz not null default now(),\n"
        "  constraint fk_execution_session\n"
        "    foreign key (session_id) references session_records(session_id)\n"
        ");"
    )


def build_bootstrap_statements() -> list[str]:
    """返回 Phase 1 需要执行的 PostgreSQL bootstrap SQL 列表。"""

    statements: list[str] = []
    for table_name in EXPECTED_TABLES:
        if table_name == "session_records":
            statements.append(_build_session_table_statement())
            continue
        if table_name == "execution_records":
            statements.append(_build_execution_table_statement())
            continue
        statements.append(_build_payload_table_statement(table_name))
    return statements


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
