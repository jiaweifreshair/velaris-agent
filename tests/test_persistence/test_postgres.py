"""PostgreSQL 事务连接上下文测试。"""

from __future__ import annotations

import velaris_agent.persistence.postgres as postgres_module


def test_postgres_connection_commits_and_closes_on_success(monkeypatch):
    """成功退出上下文时应 commit 并 close。"""

    calls: list[str] = []

    class DummyConnection:
        def commit(self) -> None:
            calls.append("commit")

        def rollback(self) -> None:
            calls.append("rollback")

        def close(self) -> None:
            calls.append("close")

    dummy_connection = DummyConnection()

    def fake_connect(dsn: str) -> DummyConnection:
        assert dsn == "postgresql://user:pass@localhost:5432/velaris"
        calls.append("connect")
        return dummy_connection

    class DummyPsycopg:
        """用于替代真实 psycopg 模块的最小假对象。"""

        @staticmethod
        def connect(dsn: str) -> DummyConnection:
            return fake_connect(dsn)

    monkeypatch.setattr(postgres_module, "_load_psycopg", lambda: DummyPsycopg())

    with postgres_module.postgres_connection("postgresql://user:pass@localhost:5432/velaris") as connection:
        assert connection is dummy_connection

    assert calls == ["connect", "commit", "close"]


def test_postgres_connection_rolls_back_and_closes_on_exception(monkeypatch):
    """上下文内抛异常时应 rollback 并 close。"""

    calls: list[str] = []

    class DummyConnection:
        def commit(self) -> None:
            calls.append("commit")

        def rollback(self) -> None:
            calls.append("rollback")

        def close(self) -> None:
            calls.append("close")

    dummy_connection = DummyConnection()

    def fake_connect(dsn: str) -> DummyConnection:
        assert dsn == "postgresql://user:pass@localhost:5432/velaris"
        calls.append("connect")
        return dummy_connection

    class DummyPsycopg:
        """用于替代真实 psycopg 模块的最小假对象。"""

        @staticmethod
        def connect(dsn: str) -> DummyConnection:
            return fake_connect(dsn)

    monkeypatch.setattr(postgres_module, "_load_psycopg", lambda: DummyPsycopg())

    try:
        with postgres_module.postgres_connection("postgresql://user:pass@localhost:5432/velaris"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert calls == ["connect", "rollback", "close"]
