"""Velaris 原生持久化基础设施（SQLite 主线）。"""

from __future__ import annotations

from importlib import import_module

from velaris_agent.persistence.schema import (
    EXPECTED_TABLES,
    bootstrap_sqlite_schema,
    build_sqlite_bootstrap_statements,
)

# 兼容别名：历史调用点可能仍使用更通用的函数名。
build_bootstrap_statements = build_sqlite_bootstrap_statements
bootstrap_schema = bootstrap_sqlite_schema

__all__ = [
    "EXPECTED_TABLES",
    "bootstrap_sqlite_schema",
    "build_sqlite_bootstrap_statements",
    "bootstrap_schema",
    "build_bootstrap_statements",
    "factory",
]


def __getattr__(name: str):
    if name == "factory":
        return import_module("velaris_agent.persistence.factory")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

