"""SQLite 路径 helper 测试。"""

from __future__ import annotations

from pathlib import Path

from velaris_agent.persistence.factory import build_decision_memory, build_job_queue
from velaris_agent.persistence.job_queue import SqliteJobQueue
from velaris_agent.persistence.sqlite_memory import SqliteDecisionMemory
from velaris_agent.persistence.sqlite_helpers import get_project_database_path


def test_get_project_database_path_points_to_project_local_velaris_db(tmp_path: Path) -> None:
    """SQLite 数据库路径应固定落到 <project>/.velaris-agent/velaris.db。"""

    path = get_project_database_path(tmp_path)

    assert path == tmp_path.resolve() / ".velaris-agent" / "velaris.db"


def test_factory_builders_support_cwd_based_sqlite(tmp_path: Path) -> None:
    """工厂应支持按 cwd 构建 SQLite 主线后端，便于上层最小侵入迁移。"""

    memory = build_decision_memory(cwd=tmp_path)
    assert isinstance(memory, SqliteDecisionMemory)

    queue = build_job_queue(cwd=tmp_path)
    assert isinstance(queue, SqliteJobQueue)
