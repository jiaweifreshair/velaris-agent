"""SQLite 连接与 schema bootstrap 测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from velaris_agent.persistence.schema import EXPECTED_TABLES, bootstrap_sqlite_schema
from velaris_agent.persistence.sqlite import sqlite_connection
from velaris_agent.persistence.sqlite_helpers import get_project_database_path


def test_sqlite_connection_creates_parent_directory_and_commits(tmp_path: Path) -> None:
    """SQLite 连接层应自动创建数据库目录并在成功时提交事务。"""

    project_dir = tmp_path / "demo-project"
    database_path = get_project_database_path(project_dir)

    with sqlite_connection(database_path) as connection:
        connection.execute("create table sample (id text primary key, value text not null)")
        connection.execute("insert into sample (id, value) values (?, ?)", ("one", "hello"))

    assert database_path.parent.exists()
    with sqlite3.connect(database_path) as raw_connection:
        row = raw_connection.execute("select value from sample where id = ?", ("one",)).fetchone()
    assert row == ("hello",)


def test_sqlite_connection_rolls_back_when_exception_raised(tmp_path: Path) -> None:
    """SQLite 连接层应在异常路径回滚事务，避免写入半成品数据。"""

    database_path = get_project_database_path(tmp_path)
    with sqlite_connection(database_path) as connection:
        connection.execute("create table sample (id text primary key, value text not null)")

    try:
        with sqlite_connection(database_path) as connection:
            connection.execute("insert into sample (id, value) values (?, ?)", ("one", "hello"))
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    with sqlite3.connect(database_path) as raw_connection:
        row = raw_connection.execute("select value from sample where id = ?", ("one",)).fetchone()
    assert row is None


def test_bootstrap_sqlite_schema_creates_all_expected_tables(tmp_path: Path) -> None:
    """SQLite bootstrap 应创建全部持久化表。"""

    database_path = get_project_database_path(tmp_path)

    count = bootstrap_sqlite_schema(database_path)

    assert count == len(EXPECTED_TABLES)
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "select name from sqlite_master where type = 'table' order by name asc"
        ).fetchall()

    table_names = {row[0] for row in rows}
    for table_name in EXPECTED_TABLES:
        assert table_name in table_names


def test_sqlite_connection_sets_required_pragmas(tmp_path: Path) -> None:
    """SQLite 连接层应应用主线所需的关键 PRAGMA。"""

    database_path = get_project_database_path(tmp_path)

    with sqlite_connection(database_path) as connection:
        foreign_keys = connection.execute("pragma foreign_keys").fetchone()
        synchronous = connection.execute("pragma synchronous").fetchone()
        busy_timeout = connection.execute("pragma busy_timeout").fetchone()

    assert foreign_keys == (1,)
    assert synchronous is not None
    assert busy_timeout == (5000,)
