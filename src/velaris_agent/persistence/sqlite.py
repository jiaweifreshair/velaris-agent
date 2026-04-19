"""SQLite 事务连接上下文。

SQLite 会成为本仓库默认且唯一的主线持久化后端，因此这里提供：
- 统一的连接创建与 PRAGMA 设置；
- 统一的事务提交 / 回滚边界；
- 自动创建数据库文件所在目录，避免调用方重复处理。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3


def _apply_pragmas(connection: sqlite3.Connection) -> None:
    """对连接应用主线需要的 SQLite PRAGMA 设置。"""

    # 外键约束默认关闭，主线必须打开以保证引用一致性。
    connection.execute("pragma foreign_keys = on")
    # WAL 在读多写少场景更稳；同时避免长事务阻塞读。
    connection.execute("pragma journal_mode = wal")
    # 在保证基本可靠性的前提下，降低同步强度以获得更好性能。
    connection.execute("pragma synchronous = normal")
    # 避免并发时立刻报错，给短暂锁等待一个合理窗口（毫秒）。
    connection.execute("pragma busy_timeout = 5000")
    # 临时表尽量放内存，减少磁盘 IO。
    connection.execute("pragma temp_store = memory")


@contextmanager
def sqlite_connection(database_path: str | Path) -> Iterator[sqlite3.Connection]:
    """创建 SQLite 连接并在上下文退出时统一提交或回滚。

    该上下文保持稳定一致的事务行为契约：
    - 正常退出：commit
    - 异常退出：rollback 并向上抛出
    - 始终 close 连接
    """

    path = Path(database_path)
    if str(database_path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path))
    try:
        _apply_pragmas(connection)
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()
