"""持久化相关测试夹具。"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    """提供测试用 PostgreSQL DSN；未配置时跳过需要真实数据库的用例。"""
    dsn = os.getenv("VELARIS_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("未设置 VELARIS_TEST_POSTGRES_DSN, 跳过 PostgreSQL 集成测试")
    return dsn
