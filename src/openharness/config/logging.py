"""Velaris/OpenHarness 运行时日志初始化。

该模块只负责配置标准库 ``logging`` 的统一落盘能力。业务代码仍然使用
``logging.getLogger(__name__)`` 获取各自模块 logger，最终由这里挂载到 root
logger 的文件 handler 统一写入 ``velaris.log``。
"""

from __future__ import annotations

import logging
from pathlib import Path

from openharness.config.paths import get_logs_dir

_LOG_FILE_NAME = "velaris.log"
_HANDLER_ATTR = "_velaris_logging_handler"


def _find_managed_handler(root: logging.Logger) -> logging.Handler | None:
    """查找由本模块创建的文件 handler，避免重复挂载。"""

    for handler in root.handlers:
        if getattr(handler, _HANDLER_ATTR, False):
            return handler
    return None


def setup_logging(*, level: int = logging.INFO) -> Path:
    """初始化统一文件日志，并返回实际日志文件路径。

    这里配置的是 root logger，因此所有使用标准库 logging 的模块都会进入同一
    个日志文件，包括 ``openharness.*`` 与 ``velaris_agent.*``。

    该函数是幂等的，可以在 CLI 启动流程中安全重复调用。如果日志目录因为
    ``VELARIS_LOGS_DIR`` 或 ``OPENHARNESS_LOGS_DIR`` 发生变化，则会关闭旧
    handler 并切换到新的文件路径，避免重复写入或锁住旧文件。
    """

    log_path = get_logs_dir() / _LOG_FILE_NAME
    root = logging.getLogger()
    managed_handler = _find_managed_handler(root)

    if managed_handler is not None:
        current_path = Path(getattr(managed_handler, "baseFilename", ""))
        if current_path == log_path:
            root.setLevel(level)
            managed_handler.setLevel(level)
            return log_path
        root.removeHandler(managed_handler)
        managed_handler.close()

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    setattr(handler, _HANDLER_ATTR, True)

    root.addHandler(handler)
    root.setLevel(level)
    return log_path
