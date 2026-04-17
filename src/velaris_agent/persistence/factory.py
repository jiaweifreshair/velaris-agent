"""决策记忆工厂。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.velaris.outcome_store import OutcomeStore
from velaris_agent.velaris.task_ledger import TaskLedger

if TYPE_CHECKING:
    from velaris_agent.persistence.job_queue import PostgresJobQueue
    from velaris_agent.persistence.postgres_runtime import (
        AuditEventStore,
        PostgresOutcomeStore,
        PostgresTaskLedger,
    )


def build_decision_memory(
    postgres_dsn: str = "",
    base_dir: str | Path | None = None,
) -> DecisionMemory:
    """按配置构建决策记忆后端。

    只有在显式提供 `postgres_dsn` 时才切换到 PostgreSQL，
    其余情况继续沿用文件后端，确保现有行为默认兼容。
    """

    if postgres_dsn.strip():
        from velaris_agent.persistence.postgres_memory import PostgresDecisionMemory

        return PostgresDecisionMemory(postgres_dsn.strip(), base_dir=base_dir)
    return DecisionMemory(base_dir=base_dir)


def build_task_ledger(postgres_dsn: str = "") -> TaskLedger:
    """按配置构建任务账本后端。

    该工厂保持默认内存账本不变，只在显式提供 PostgreSQL DSN 时切换到数据库后端。
    """

    if postgres_dsn.strip():
        from velaris_agent.persistence.postgres_runtime import PostgresTaskLedger

        return PostgresTaskLedger(postgres_dsn.strip())
    return TaskLedger()


def build_outcome_store(postgres_dsn: str = "") -> OutcomeStore:
    """按配置构建 outcome 仓储后端。

    这样 OpenHarness 入口后续只需透传 DSN，就能在不改调用点的前提下接入持久化。
    """

    if postgres_dsn.strip():
        from velaris_agent.persistence.postgres_runtime import PostgresOutcomeStore

        return PostgresOutcomeStore(postgres_dsn.strip())
    return OutcomeStore()


def build_audit_store(postgres_dsn: str = "") -> "AuditEventStore | None":
    """按配置构建审计事件仓储。

    审计仓储保持可选，确保旧调用方在未开启 PostgreSQL 时仍返回 `audit_event_count = 0`。
    """

    if postgres_dsn.strip():
        from velaris_agent.persistence.postgres_runtime import AuditEventStore

        return AuditEventStore(postgres_dsn.strip())
    return None


def build_job_queue(postgres_dsn: str = "") -> "PostgresJobQueue | None":
    """按配置构建数据库任务队列。

    只有显式提供 PostgreSQL DSN 时才启用队列，
    这样 `save_decision` 在默认文件模式下仍保持原有同步兼容行为。
    """

    if postgres_dsn.strip():
        from velaris_agent.persistence.job_queue import PostgresJobQueue

        return PostgresJobQueue(postgres_dsn.strip())
    return None
