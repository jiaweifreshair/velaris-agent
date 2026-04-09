"""文本脱敏工具：统一处理日志、Shell 输出与 MCP 错误中的敏感信息。"""

from __future__ import annotations

import re

_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"ghp_[A-Za-z0-9_]{8,}", re.IGNORECASE), "ghp_[REDACTED]"),
    (re.compile(r"sk-[A-Za-z0-9_-]{8,}", re.IGNORECASE), "sk-[REDACTED]"),
    (re.compile(r"Bearer\s+\S+", re.IGNORECASE), "Bearer [REDACTED]"),
    (
        re.compile(
            r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH)[A-Z0-9_]*)=([^\s\"']+)"
        ),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"(?i)\b(token|key|secret|password)=([^\s&,;\"']{4,})"),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE),
        "AKIA[REDACTED]",
    ),
)


def redact_sensitive_text(text: str, *, enabled: bool = True) -> str:
    """对文本中的常见密钥、令牌和口令片段做保守脱敏。"""

    if not enabled or not text:
        return text

    redacted = text
    for pattern, replacement in _REPLACEMENTS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
