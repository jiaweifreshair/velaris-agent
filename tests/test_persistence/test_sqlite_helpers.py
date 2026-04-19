"""SQLite 路径 helper 测试。"""

from __future__ import annotations

from pathlib import Path

from velaris_agent.persistence.sqlite_helpers import get_project_database_path


def test_get_project_database_path_points_to_project_local_velaris_db(tmp_path: Path) -> None:
    """SQLite 数据库路径应固定落到 <project>/.velaris-agent/velaris.db。"""

    path = get_project_database_path(tmp_path)

    assert path == tmp_path.resolve() / ".velaris-agent" / "velaris.db"
