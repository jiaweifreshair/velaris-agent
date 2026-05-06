"""Velaris 持久化对象工厂。

本仓库支持 SQLite 和 OpenViking 双后端：
- SQLite：传统关系型存储，适合单用户 CLI 和渐进迁移
- OpenViking：AI Agent 原生上下文数据库，支持 viking:// URI + 三层加载

工厂职责：
- 解析 `sqlite_database_path` / `openviking_path` / `cwd` 推导存储位置；
- 幂等初始化 schema（避免调用方必须先手动执行 `velaris storage init` 才能使用）；
- 按 OpenViking 优先原则构建仓储实现，SQLite 作为回退和兼容层。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.velaris.outcome_store import OutcomeStore
from velaris_agent.velaris.task_ledger import TaskLedger

if TYPE_CHECKING:
    from velaris_agent.context.openviking_context import OpenVikingContext
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


# ── OpenViking 工厂方法 ──────────────────────────────────────────────


_BOOTSTRAPPED_VIKING_PATHS: set[str] = set()


def _resolve_openviking_path(
    openviking_path: str | Path | None,
    cwd: str | Path | None,
) -> str | None:
    """解析 OpenViking 数据路径。

    优先级：
    1) 显式 openviking_path
    2) 从 cwd 推导项目内默认路径 (.velaris/viking/)
    """
    if openviking_path is not None and str(openviking_path).strip():
        return str(Path(openviking_path))
    if cwd is not None and str(cwd).strip():
        return str(Path(cwd).resolve() / ".velaris" / "viking")
    return None


def build_openviking_context(
    openviking_path: str | Path | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    agent_id: str = "velaris-default",
    cwd: str | Path | None = None,
) -> "OpenVikingContext | None":
    """按配置构建 OpenViking 上下文管理器。

    构建逻辑：
    - 若有 openviking_path 或 cwd：构建本地模式 OpenVikingContext
    - 若有 base_url：构建 HTTP 模式 OpenVikingContext
    - 否则：返回 None（回退到 SQLite/文件后端）

    Args:
        openviking_path: 本地 OpenViking 数据目录
        base_url: 远程 OpenViking 服务地址
        api_key: 远程服务的 API 密钥
        agent_id: Agent 标识
        cwd: 工作目录（用于推导默认路径）

    Returns:
        OpenVikingContext 实例，无法构建时返回 None
    """
    from velaris_agent.context.openviking_context import OpenVikingContext

    resolved_local = _resolve_openviking_path(openviking_path, cwd)

    if resolved_local is not None:
        return OpenVikingContext(
            local_path=resolved_local,
            agent_id=agent_id,
        )

    if base_url is not None and base_url.strip():
        return OpenVikingContext(
            base_url=base_url,
            api_key=api_key,
            agent_id=agent_id,
        )

    return None

