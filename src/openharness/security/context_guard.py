"""系统提示上下文防护：在注入模型前扫描项目指令文件与外部上下文。"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_CONTEXT_THREAT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"ignore\s+(previous|all|above|prior)\s+instructions", "prompt_injection"),
    (r"do\s+not\s+tell\s+the\s+user", "deception_hide"),
    (r"system\s+prompt\s+override", "sys_prompt_override"),
    (r"disregard\s+(your|all|any)\s+(instructions|rules|guidelines)", "disregard_rules"),
    (r"act\s+as\s+(if|though)\s+you\s+(have\s+no|don't\s+have)\s+(restrictions|limits|rules)", "bypass_restrictions"),
    (r"<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->", "html_comment_injection"),
    (r"<\s*div\s+style\s*=\s*[\"'].*display\s*:\s*none", "hidden_div"),
    (r"translate\s+.*\s+into\s+.*\s+and\s+(execute|run|eval)", "translate_execute"),
    (r"curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfil_curl"),
    (r"cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass)", "read_secrets"),
)

_CONTEXT_INVISIBLE_CHARS = {
    "\u200b",
    "\u200c",
    "\u200d",
    "\u2060",
    "\ufeff",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
}


def scan_context_content(content: str, label: str, *, enabled: bool = True) -> str:
    """扫描要注入系统提示的上下文，命中威胁时直接返回阻断占位符。"""

    if not enabled or not content:
        return content

    findings: list[str] = []
    for character in _CONTEXT_INVISIBLE_CHARS:
        if character in content:
            findings.append(f"invisible unicode U+{ord(character):04X}")

    for pattern, threat_id in _CONTEXT_THREAT_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            findings.append(threat_id)

    if not findings:
        return content

    logger.warning("Blocked context file %s: %s", label, ", ".join(findings))
    return (
        f"[BLOCKED: {label} 包含潜在提示注入或敏感信息外带模式"
        f"（{', '.join(findings)}），内容已在进入模型前被阻断。]"
    )


def truncate_context_content(content: str, label: str, *, max_chars: int) -> str:
    """对上下文做头尾保留式截断，避免超长文件挤占主提示窗口。"""

    if len(content) <= max_chars:
        return content

    head_chars = int(max_chars * 0.65)
    tail_chars = max_chars - head_chars
    marker = (
        f"\n...[truncated {label}: 保留前 {head_chars} 字 + 后 {tail_chars} 字，"
        f"原始长度 {len(content)}]...\n"
    )
    return content[:head_chars] + marker + content[-tail_chars:]
