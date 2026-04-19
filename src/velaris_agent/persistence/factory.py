"""Velaris 持久化对象工厂。

本仓库已收束为 SQLite 单库主线，因此该模块只负责：
- 解析 `sqlite_database_path` / `cwd` 推导出的项目内数据库位置；
- 幂等初始化 schema（避免调用方必须先手动执行 `velaris storage init` 才能使用）；
- 构建 SQLite 仓储实现，并在缺省场景下回退到内存/文件后端以保持兼容。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.velaris.outcome_store import OutcomeStore
from velaris_agent.velaris.task_ledger import TaskLedger

if TYPE_CHECKING:
    from velaris_agent.persistence.job_queue import SqliteJobQueue
    from velaris_agent.persistence.sqlite_execution import (
        ExecutionRepository as SqliteExecutionRepository,
        SessionRepository as SqliteSessionRepository,
    )
    from velaris_agent.persistence.sqlite_runtime import SqliteAuditEventStore

_BOOTSTRAPPED_SQLITE_PATHS: set[str] = set()


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


def _ensure_sqlite_schema(database_path: str) -> None:
    """确保 SQLite schema 已初始化。

    该函数是幂等的：同一路径只会执行一次 bootstrap，避免在高频工厂调用中重复跑 DDL。
    """

    if database_path in _BOOTSTRAPPED_SQLITE_PATHS:
        return
    from velaris_agent.persistence.schema import bootstrap_sqlite_schema

    bootstrap_sqlite_schema(database_path)
    _BOOTSTRAPPED_SQLITE_PATHS.add(database_path)


def build_decision_memory(
    base_dir: str | Path | None = None,
    sqlite_database_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> DecisionMemory:
    """按配置构建决策记忆后端。

    - 若解析到 SQLite 路径：返回 `SqliteDecisionMemory`；
    - 否则：回退到文件版 `DecisionMemory`（用于无项目上下文的纯函数调用/单测）。
    """

    resolved_sqlite_path = _resolve_sqlite_database_path(sqlite_database_path, cwd)
    if resolved_sqlite_path is not None:
        _ensure_sqlite_schema(resolved_sqlite_path)
        from velaris_agent.persistence.sqlite_memory import SqliteDecisionMemory

        return SqliteDecisionMemory(resolved_sqlite_path, base_dir=base_dir)

    return DecisionMemory(base_dir=base_dir)


def build_task_ledger(
    sqlite_database_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> TaskLedger:
    """按配置构建任务账本后端。"""

    resolved_sqlite_path = _resolve_sqlite_database_path(sqlite_database_path, cwd)
    if resolved_sqlite_path is not None:
        _ensure_sqlite_schema(resolved_sqlite_path)
        from velaris_agent.persistence.sqlite_runtime import SqliteTaskLedger

        return SqliteTaskLedger(resolved_sqlite_path)

    return TaskLedger()


def build_outcome_store(
    sqlite_database_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> OutcomeStore:
    """按配置构建 outcome 仓储后端。"""

    resolved_sqlite_path = _resolve_sqlite_database_path(sqlite_database_path, cwd)
    if resolved_sqlite_path is not None:
        _ensure_sqlite_schema(resolved_sqlite_path)
        from velaris_agent.persistence.sqlite_runtime import SqliteOutcomeStore

        return SqliteOutcomeStore(resolved_sqlite_path)

    return OutcomeStore()


def build_audit_store(
    sqlite_database_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> "SqliteAuditEventStore | None":
    """按配置构建审计事件仓储。"""

    resolved_sqlite_path = _resolve_sqlite_database_path(sqlite_database_path, cwd)
    if resolved_sqlite_path is not None:
        _ensure_sqlite_schema(resolved_sqlite_path)
        from velaris_agent.persistence.sqlite_runtime import SqliteAuditEventStore

        return SqliteAuditEventStore(resolved_sqlite_path)
    return None


def build_execution_repository(
    sqlite_database_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> "SqliteExecutionRepository | None":
    """按配置构建 execution 主记录仓储。"""

    resolved_sqlite_path = _resolve_sqlite_database_path(sqlite_database_path, cwd)
    if resolved_sqlite_path is not None:
        _ensure_sqlite_schema(resolved_sqlite_path)
        from velaris_agent.persistence.sqlite_execution import ExecutionRepository

        return ExecutionRepository(resolved_sqlite_path)
    return None


def build_session_repository(
    sqlite_database_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> "SqliteSessionRepository | None":
    """按配置构建 session 主记录仓储。"""

    resolved_sqlite_path = _resolve_sqlite_database_path(sqlite_database_path, cwd)
    if resolved_sqlite_path is not None:
        _ensure_sqlite_schema(resolved_sqlite_path)
        from velaris_agent.persistence.sqlite_execution import SessionRepository

        return SessionRepository(resolved_sqlite_path)
    return None


def build_job_queue(
    sqlite_database_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> "SqliteJobQueue | None":
    """按配置构建数据库任务队列。"""

    resolved_sqlite_path = _resolve_sqlite_database_path(sqlite_database_path, cwd)
    if resolved_sqlite_path is not None:
        _ensure_sqlite_schema(resolved_sqlite_path)
        from velaris_agent.persistence.job_queue import SqliteJobQueue

        return SqliteJobQueue(resolved_sqlite_path)
    return None

