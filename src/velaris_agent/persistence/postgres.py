"""PostgreSQL 事务连接上下文。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from psycopg import Connection


def _load_psycopg() -> Any:
    """按需导入 psycopg。

    这样默认文件后端、schema 生成、以及大量只做 monkeypatch 的单元测试
    都不会在 import 阶段被 PostgreSQL 驱动环境绑死。
    """

    import psycopg

    return psycopg


@contextmanager
def postgres_connection(dsn: str) -> Iterator["Connection[Any]"]:
    """创建 PostgreSQL 连接并在上下文退出时统一提交或回滚。

    这样上层 bootstrap 逻辑只需要关注 SQL 执行本身，
    而事务边界与连接关闭由这里集中收口。
    """

    psycopg = _load_psycopg()
    connection = psycopg.connect(dsn)
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()
