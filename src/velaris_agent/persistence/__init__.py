"""Velaris 原生持久化基础设施。

该包只提供最小的 PostgreSQL bootstrap 与事务上下文，避免在 Phase 1
提前引入 ORM、迁移框架或其他额外基础设施。
"""

from importlib import import_module

from velaris_agent.persistence.schema import EXPECTED_TABLES, bootstrap_schema, build_bootstrap_statements

__all__ = [
    "EXPECTED_TABLES",
    "bootstrap_schema",
    "build_bootstrap_statements",
    "factory",
    "postgres_execution",
    "postgres_connection",
]


def __getattr__(name: str):
    """按需暴露可选的 PostgreSQL 连接入口。

    只有真正访问 `postgres_connection` 时才去导入 psycopg 相关模块，
    以保证默认文件后端、schema 生成和纯单元测试不会被可选驱动绑死。
    """

    if name == "postgres_connection":
        from velaris_agent.persistence.postgres import postgres_connection

        return postgres_connection
    if name == "factory":
        return import_module("velaris_agent.persistence.factory")
    if name == "postgres_execution":
        return import_module("velaris_agent.persistence.postgres_execution")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
