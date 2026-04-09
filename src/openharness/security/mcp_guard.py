"""MCP 运行时防护：过滤子进程环境变量，并对错误文本做敏感信息脱敏。"""

from __future__ import annotations

import os
from collections.abc import Mapping

from openharness.security.redaction import redact_sensitive_text

_SAFE_MCP_ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "LC_ALL",
        "TERM",
        "SHELL",
        "TMPDIR",
    }
)


def build_safe_mcp_env(
    user_env: Mapping[str, str] | None,
    *,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """构造安全的 MCP stdio 子进程环境，只透传基础变量与显式配置项。"""

    inherited_env = base_env or os.environ
    safe_env: dict[str, str] = {}
    for key, value in inherited_env.items():
        if key in _SAFE_MCP_ENV_KEYS or key.startswith("XDG_"):
            safe_env[key] = value
    if user_env:
        safe_env.update(dict(user_env))
    return safe_env


def sanitize_mcp_error(text: str) -> str:
    """对 MCP 错误文本做统一脱敏，避免密钥在状态面板或模型上下文中泄露。"""

    return redact_sensitive_text(text)
