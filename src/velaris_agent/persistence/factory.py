"""决策记忆工厂。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.velaris.outcome_store import OutcomeStore
from velaris_agent.velaris.task_ledger import TaskLedger

if TYPE_CHECKING:
    from velaris_agent.persistence.postgres_execution import (
        ExecutionRepository,
        SessionRepository,
    )
    from velaris_agent.persistence.job_queue import PostgresJobQueue, SqliteJobQueue
    from velaris_agent.persistence.postgres_runtime import (
        AuditEventStore,
    )
    from velaris_agent.persistence.sqlite_execution import (
        ExecutionRepository as SqliteExecutionRepository,
        SessionRepository as SqliteSessionRepository,
    )
    from velaris_agent.persistence.sqlite_runtime import (
        SqliteAuditEventStore,
    )


def _resolve_sqlite_database_path(
    sqlite_database_path: str | Path | None,
    cwd: str | Path | None,
) -> str | None:
    """解析 SQLite 数据库路径。

    优先级：
    1) 显式 sqlite_database_path
    2) 从 cwd 推导项目内默认路径
    """

    if sqlite_database_path is not None and str(sqlite_database_path).strip():
        return str(Path(sqlite_database_path))
    if cwd is not None and str(cwd).strip():
        from velaris_agent.persistence.sqlite_helpers import get_project_database_path

        return str(get_project_database_path(cwd))
    return None


def build_decision_memory(
    postgres_dsn: str = "",
    base_dir: str | Path | None = None,
    sqlite_database_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> DecisionMemory:
    """按配置构建决策记忆后端。

    SQLite 会成为主线，因此优先按 sqlite_database_path/cwd 构建 SQLite 后端；
    若未提供 SQLite 路径但显式给出 `postgres_dsn`，则继续沿用 PostgreSQL；
    其余情况保持文件后端，确保现有行为默认兼容。
    """

    resolved_sqlite_path = _resolve_sqlite_database_path(sqlite_database_path, cwd)
    if resolved_sqlite_path is not None:
        from velaris_agent.persistence.sqlite_memory import SqliteDecisionMemory

        return SqliteDecisionMemory(resolved_sqlite_path, base_dir=base_dir)

    if postgres_dsn.strip():
        from velaris_agent.persistence.postgres_memory import PostgresDecisionMemory

        return PostgresDecisionMemory(postgres_dsn.strip(), base_dir=base_dir)
    return DecisionMemory(base_dir=base_dir)


def build_task_ledger(
    postgres_dsn: str = "",
    sqlite_database_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> TaskLedger:
    """按配置构建任务账本后端。

    该工厂保持默认内存账本不变，只在显式提供 SQLite/PostgreSQL 配置时切换到数据库后端。
    """

    resolved_sqlite_path = _resolve_sqlite_database_path(sqlite_database_path, cwd)
    if resolved_sqlite_path is not None:
        from velaris_agent.persistence.sqlite_runtime import SqliteTaskLedger

        return SqliteTaskLedger(resolved_sqlite_path)

    if postgres_dsn.strip():
        from velaris_agent.persistence.postgres_runtime import PostgresTaskLedger

        return PostgresTaskLedger(postgres_dsn.strip())
    return TaskLedger()


def build_outcome_store(
    postgres_dsn: str = "",
    sqlite_database_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> OutcomeStore:
    """按配置构建 outcome 仓储后端。

    这样 OpenHarness 入口后续只需透传 DSN，就能在不改调用点的前提下接入持久化。
    """

    resolved_sqlite_path = _resolve_sqlite_database_path(sqlite_database_path, cwd)
    if resolved_sqlite_path is not None:
        from velaris_agent.persistence.sqlite_runtime import SqliteOutcomeStore

        return SqliteOutcomeStore(resolved_sqlite_path)

    if postgres_dsn.strip():
        from velaris_agent.persistence.postgres_runtime import PostgresOutcomeStore

        return PostgresOutcomeStore(postgres_dsn.strip())
    return OutcomeStore()


def build_audit_store(
    postgres_dsn: str = "",
    sqlite_database_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> "AuditEventStore | SqliteAuditEventStore | None":
    """按配置构建审计事件仓储。

    审计仓储保持可选，确保旧调用方在未开启 PostgreSQL 时仍返回 `audit_event_count = 0`。
    """

    resolved_sqlite_path = _resolve_sqlite_database_path(sqlite_database_path, cwd)
    if resolved_sqlite_path is not None:
        from velaris_agent.persistence.sqlite_runtime import SqliteAuditEventStore

        return SqliteAuditEventStore(resolved_sqlite_path)

    if postgres_dsn.strip():
        from velaris_agent.persistence.postgres_runtime import AuditEventStore

        return AuditEventStore(postgres_dsn.strip())
    return None


def build_execution_repository(
    postgres_dsn: str = "",
    sqlite_database_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> "ExecutionRepository | SqliteExecutionRepository | None":
    """按配置构建 execution 主记录仓储。

    只有显式提供 PostgreSQL DSN 时才暴露 execution 主线仓储，
    这样现有未迁移调用方不会被强制拉入新的持久化依赖。
    """

    resolved_sqlite_path = _resolve_sqlite_database_path(sqlite_database_path, cwd)
    if resolved_sqlite_path is not None:
        from velaris_agent.persistence.sqlite_execution import ExecutionRepository

        return ExecutionRepository(resolved_sqlite_path)

    if postgres_dsn.strip():
        from velaris_agent.persistence.postgres_execution import ExecutionRepository

        return ExecutionRepository(postgres_dsn.strip())
    return None


def build_session_repository(
    postgres_dsn: str = "",
    sqlite_database_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> "SessionRepository | SqliteSessionRepository | None":
    """按配置构建 session 主记录仓储。

    该入口为后续 `session_storage.py` PostgreSQL 化预留统一工厂，
    避免桥接层直接 new 数据库仓储实现。
    """

    resolved_sqlite_path = _resolve_sqlite_database_path(sqlite_database_path, cwd)
    if resolved_sqlite_path is not None:
        from velaris_agent.persistence.sqlite_execution import SessionRepository

        return SessionRepository(resolved_sqlite_path)

    if postgres_dsn.strip():
        from velaris_agent.persistence.postgres_execution import SessionRepository

        return SessionRepository(postgres_dsn.strip())
    return None


def build_job_queue(
    postgres_dsn: str = "",
    sqlite_database_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> "PostgresJobQueue | SqliteJobQueue | None":
    """按配置构建数据库任务队列。

    只有显式提供 PostgreSQL DSN 时才启用队列，
    这样 `save_decision` 在默认文件模式下仍保持原有同步兼容行为。
    """

    resolved_sqlite_path = _resolve_sqlite_database_path(sqlite_database_path, cwd)
    if resolved_sqlite_path is not None:
        from velaris_agent.persistence.job_queue import SqliteJobQueue

        return SqliteJobQueue(resolved_sqlite_path)

    if postgres_dsn.strip():
        from velaris_agent.persistence.job_queue import PostgresJobQueue

        return PostgresJobQueue(postgres_dsn.strip())
    return None
