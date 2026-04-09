"""Shell 命令防护：危险命令识别、审批分级与 workdir 清洗。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import AbstractSet, Literal


@dataclass(frozen=True)
class DangerousCommandPattern:
    """描述一条危险命令规则：是什么、为什么危险、以及应如何分级处理。"""

    pattern_id: str
    pattern: str
    description: str
    severity: Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class CommandGuardDecision:
    """描述命令守卫的决策结果，供 Bash 工具统一执行。"""

    allowed: bool
    requires_confirmation: bool
    reason: str
    matched_pattern_id: str | None = None


_ANSI_ESCAPE_RE = re.compile(
    r"(?:\x1B[@-Z\\-_]|\x1B\[[0-?]*[ -/]*[@-~]|\x1B\][^\x07]*(?:\x07|\x1B\\))"
)

_WORKDIR_SAFE_RE = re.compile(r"^[A-Za-z0-9/_\-.~ +@=,]+$")

_SSH_SENSITIVE_PATH = r'(?:~|\$home|\$\{home\})/\.ssh(?:/|$)'
_VELARIS_ENV_PATH = (
    r'(?:~\/\.velaris-agent/|'
    r'(?:\$home|\$\{home\})/\.velaris-agent/|'
    r'(?:\$openharness_home|\$\{openharness_home\})/)'
    r'(?:settings\.json|\.env)\b'
)
_SENSITIVE_WRITE_TARGET = (
    r'(?:/etc/|/dev/sd|'
    rf'{_SSH_SENSITIVE_PATH}|'
    rf'{_VELARIS_ENV_PATH})'
)

_DANGEROUS_COMMAND_PATTERNS: tuple[DangerousCommandPattern, ...] = (
    DangerousCommandPattern("delete_root_path", r"\brm\s+(-[^\s]*\s+)*/", "删除根路径下内容", "critical"),
    DangerousCommandPattern("recursive_delete", r"\brm\s+-[^\s]*r", "递归删除", "high"),
    DangerousCommandPattern("recursive_delete_long", r"\brm\s+--recursive\b", "递归删除（长参数）", "high"),
    DangerousCommandPattern("chmod_world_writable", r"\bchmod\s+(-[^\s]*\s+)*(777|666|o\+[rwx]*w|a\+[rwx]*w)\b", "把文件改成全局可写", "medium"),
    DangerousCommandPattern("chmod_world_writable_recursive", r"\bchmod\s+--recursive\b.*(777|666|o\+[rwx]*w|a\+[rwx]*w)", "递归改成全局可写", "high"),
    DangerousCommandPattern("chown_root_recursive", r"\bchown\s+(-[^\s]*)?R\s+root", "递归把所有者改成 root", "high"),
    DangerousCommandPattern("chown_root_recursive_long", r"\bchown\s+--recursive\b.*root", "递归把所有者改成 root（长参数）", "high"),
    DangerousCommandPattern("mkfs", r"\bmkfs\b", "格式化文件系统", "critical"),
    DangerousCommandPattern("dd", r"\bdd\s+.*if=", "磁盘级复制/覆写", "critical"),
    DangerousCommandPattern("write_block_device", r">\s*/dev/sd", "向块设备直接写入", "critical"),
    DangerousCommandPattern("sql_drop", r"\bDROP\s+(TABLE|DATABASE)\b", "执行 SQL DROP", "critical"),
    DangerousCommandPattern("sql_delete_without_where", r"\bDELETE\s+FROM\b(?!.*\bWHERE\b)", "执行无 WHERE 的 SQL DELETE", "critical"),
    DangerousCommandPattern("sql_truncate", r"\bTRUNCATE\s+(TABLE)?\s*\w", "执行 SQL TRUNCATE", "critical"),
    DangerousCommandPattern("overwrite_system_config", r">\s*/etc/", "覆写系统配置文件", "critical"),
    DangerousCommandPattern("systemctl_disable", r"\bsystemctl\s+(stop|disable|mask)\b", "停用系统服务", "high"),
    DangerousCommandPattern("kill_all_processes", r"\bkill\s+-9\s+-1\b", "杀死所有进程", "critical"),
    DangerousCommandPattern("force_kill_processes", r"\bpkill\s+-9\b", "强制杀死进程", "high"),
    DangerousCommandPattern("fork_bomb", r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "Fork Bomb", "critical"),
    DangerousCommandPattern("shell_dash_c", r"\b(bash|sh|zsh|ksh)\s+-[^\s]*c(\s+|$)", "通过 shell -c 执行字符串命令", "low"),
    DangerousCommandPattern("script_dash_c", r"\b(python[23]?|perl|ruby|node)\s+-[ec]\s+", "通过脚本解释器内联执行代码", "low"),
    DangerousCommandPattern("pipe_remote_script", r"\b(curl|wget)\b.*\|\s*(ba)?sh\b", "把远程脚本直接管道给 shell", "critical"),
    DangerousCommandPattern("process_substitution_remote", r"\b(bash|sh|zsh|ksh)\s+<\s*<?\s*\(\s*(curl|wget)\b", "通过进程替换执行远程脚本", "critical"),
    DangerousCommandPattern("tee_sensitive_target", rf"\btee\b.*[\"']?{_SENSITIVE_WRITE_TARGET}", "通过 tee 覆盖敏感目标", "critical"),
    DangerousCommandPattern("redirect_sensitive_target", rf">>?\s*[\"']?{_SENSITIVE_WRITE_TARGET}", "通过重定向覆写敏感目标", "critical"),
    DangerousCommandPattern("xargs_rm", r"\bxargs\s+.*\brm\b", "通过 xargs 批量删除", "high"),
    DangerousCommandPattern("find_exec_rm", r"\bfind\b.*-exec\s+(/\S*/)?rm\b", "通过 find -exec rm 删除", "high"),
    DangerousCommandPattern("find_delete", r"\bfind\b.*-delete\b", "通过 find -delete 删除", "high"),
    DangerousCommandPattern("nohup_background_gateway", r"\bnohup\b.*gateway\s+run\b", "脱离守护方式启动 gateway", "medium"),
    DangerousCommandPattern("background_gateway", r"gateway\s+run\b.*(&\s*$|&\s*;|\bdisown\b|\bsetsid\b)", "后台直接启动 gateway", "medium"),
    DangerousCommandPattern("self_termination", r"\b(pkill|killall)\b.*\b(velaris|openharness|gateway|cli\.py)\b", "终止代理自身进程", "critical"),
    DangerousCommandPattern("copy_into_etc", r"\b(cp|mv|install)\b.*\s/etc/", "把文件复制/移动到 /etc", "high"),
    DangerousCommandPattern("sed_inplace_etc", r"\bsed\s+-[^\s]*i.*\s/etc/", "原地编辑 /etc 中的配置", "high"),
    DangerousCommandPattern("sed_inplace_etc_long", r"\bsed\s+--in-place\b.*\s/etc/", "原地编辑 /etc 中的配置（长参数）", "high"),
)


def normalize_approval_mode(mode: str | None) -> str:
    """把审批模式规范化为 manual / smart / off，避免上层到处做兜底判断。"""

    normalized = (mode or "manual").strip().lower()
    if normalized in {"manual", "smart", "off"}:
        return normalized
    return "manual"


def validate_workdir(workdir: str) -> str | None:
    """校验 workdir 是否只包含允许字符，防止路径参数携带 shell 元字符。"""

    if not workdir:
        return None
    if not _WORKDIR_SAFE_RE.match(workdir):
        for character in workdir:
            if not _WORKDIR_SAFE_RE.match(character):
                return (
                    f"Blocked: workdir 包含不允许的字符 {character!r}。"
                    "请提供纯文件系统路径，不要带 shell 元字符。"
                )
        return "Blocked: workdir 包含不允许的字符。"
    return None


def _strip_ansi_sequences(text: str) -> str:
    """移除 ANSI 转义序列，避免利用终端控制字符绕过正则检测。"""

    return _ANSI_ESCAPE_RE.sub("", text)


def _normalize_command(command: str) -> str:
    """对命令做安全归一化，确保全角、空字节、彩色字符等无法绕过规则。"""

    normalized = _strip_ansi_sequences(command)
    normalized = normalized.replace("\x00", "")
    normalized = unicodedata.normalize("NFKC", normalized)
    return normalized


def detect_dangerous_command(command: str) -> DangerousCommandPattern | None:
    """识别命令是否命中危险规则，命中后返回规则本身供上层做审批。"""

    normalized = _normalize_command(command).lower()
    for pattern in _DANGEROUS_COMMAND_PATTERNS:
        if re.search(pattern.pattern, normalized, re.IGNORECASE | re.DOTALL):
            return pattern
    return None


def evaluate_command_guard(
    command: str,
    *,
    approval_mode: str,
    approved_pattern_ids: AbstractSet[str] | None = None,
) -> CommandGuardDecision:
    """根据审批模式和会话内已确认规则，对命令做框架级强制决策。"""

    pattern = detect_dangerous_command(command)
    if pattern is None:
        return CommandGuardDecision(
            allowed=True,
            requires_confirmation=False,
            reason="命令未命中危险规则。",
        )

    approved_pattern_ids = approved_pattern_ids or set()
    if pattern.pattern_id in approved_pattern_ids:
        return CommandGuardDecision(
            allowed=True,
            requires_confirmation=False,
            reason=f"命令命中规则“{pattern.description}”，但当前会话已审批通过。",
            matched_pattern_id=pattern.pattern_id,
        )

    mode = normalize_approval_mode(approval_mode)
    if mode == "off":
        return CommandGuardDecision(
            allowed=True,
            requires_confirmation=False,
            reason=f"命令命中规则“{pattern.description}”，但安全审批已关闭。",
            matched_pattern_id=pattern.pattern_id,
        )

    if mode == "smart":
        if pattern.severity in {"critical", "high"}:
            return CommandGuardDecision(
                allowed=False,
                requires_confirmation=False,
                reason=(
                    f"BLOCKED: 命令命中高风险规则“{pattern.description}”。"
                    "当前为 smart 审批模式，框架已自动拒绝执行。"
                ),
                matched_pattern_id=pattern.pattern_id,
            )
        if pattern.severity == "medium":
            return CommandGuardDecision(
                allowed=False,
                requires_confirmation=True,
                reason=(
                    f"命令命中中风险规则“{pattern.description}”。"
                    "当前为 smart 审批模式，需要用户确认后才会执行。"
                ),
                matched_pattern_id=pattern.pattern_id,
            )
        return CommandGuardDecision(
            allowed=True,
            requires_confirmation=False,
            reason=f"命令命中低风险规则“{pattern.description}”，smart 审批自动放行。",
            matched_pattern_id=pattern.pattern_id,
        )

    return CommandGuardDecision(
        allowed=False,
        requires_confirmation=True,
        reason=(
            f"命令命中危险规则“{pattern.description}”。"
            "当前为 manual 审批模式，需要用户确认后才会执行。"
        ),
        matched_pattern_id=pattern.pattern_id,
    )
