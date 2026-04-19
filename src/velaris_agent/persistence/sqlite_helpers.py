"""SQLite 持久化路径辅助函数。

该模块的职责非常单一：把“项目内 SQLite 数据库应该放哪”这件事收敛到一个稳定约定，
避免不同调用方各自拼路径导致不一致或写到意外位置。
"""

from __future__ import annotations

from pathlib import Path


def get_project_database_path(cwd: str | Path) -> Path:
    """返回项目内 SQLite 数据库文件路径。

    约定：<project>/.velaris-agent/velaris.db

    注意：该函数只负责“计算路径”，不负责创建目录或打开数据库连接，
    目录创建由 `velaris_agent.persistence.sqlite.sqlite_connection()` 统一处理。
    """

    return Path(cwd).resolve() / ".velaris-agent" / "velaris.db"
