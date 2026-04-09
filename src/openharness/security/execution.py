"""执行链安全辅助：统一解析安全配置、审批危险命令并整理子进程输出。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from openharness.config.settings import SecuritySettings
from openharness.security.command_guard import evaluate_command_guard, validate_workdir
from openharness.security.redaction import redact_sensitive_text
from openharness.security.session_state import SecuritySessionState

SecurityPermissionPrompt = Callable[[str, str], Awaitable[bool]]


def resolve_security_settings(raw: object | None) -> SecuritySettings:
    """把零散的安全配置输入收敛成 SecuritySettings。

    这样 bridge、task、hook 等执行链都能复用同一套解析逻辑，
    避免每个调用点重复处理 dict / 模型实例 / None 三种分支。
    """

    if isinstance(raw, SecuritySettings):
        return raw
    if isinstance(raw, dict):
        return SecuritySettings.model_validate(raw)
    return SecuritySettings()


def resolve_security_session_state(raw: object | None) -> SecuritySessionState:
    """把会话级审批状态规范化为 SecuritySessionState。

    这样各执行链只需要关心“当前会话是否已审批过某条危险规则”，
    不需要自己处理状态缺省值。
    """

    if isinstance(raw, SecuritySessionState):
        return raw
    return SecuritySessionState()


async def enforce_command_guard(
    command: str,
    *,
    tool_name: str,
    security_settings: SecuritySettings,
    session_state: SecuritySessionState,
    permission_prompt: SecurityPermissionPrompt | None = None,
) -> str | None:
    """统一执行危险命令审批流程，返回错误文本或 None。

    返回 None 表示命令已通过框架级安全校验；返回字符串表示应阻断执行，
    由上层把该原因直接呈现给用户或调用方。
    """

    guard = evaluate_command_guard(
        command,
        approval_mode=security_settings.approval_mode,
        approved_pattern_ids=session_state.approved_command_patterns,
    )
    if guard.requires_confirmation:
        if not callable(permission_prompt):
            return f"{guard.reason}\n未提供审批回调，框架已阻止执行。"
        confirmed = await permission_prompt(
            tool_name,
            f"{guard.reason}\n命令: {command[:400]}",
        )
        if not confirmed:
            return "危险命令审批未通过，执行已取消。"
        if guard.matched_pattern_id is not None:
            session_state.approved_command_patterns.add(guard.matched_pattern_id)
        return None
    if not guard.allowed:
        return guard.reason
    return None


def validate_process_workdir(cwd: str | Path | None) -> str | None:
    """统一校验工作目录参数，防止目录字段夹带 shell 元字符。"""

    if cwd is None:
        return None
    return validate_workdir(str(cwd))


def render_process_output(
    *,
    stdout: bytes | str | None = None,
    stderr: bytes | str | None = None,
    redact_secrets: bool = True,
    max_chars: int = 12000,
    default_text: str = "(no output)",
) -> str:
    """把子进程输出整理成可返回给模型或 UI 的安全文本。

    这里会统一做解码、拼接、脱敏和截断，确保不同执行链的输出行为一致，
    也避免某一处忘记脱敏后把密钥带回模型上下文。
    """

    parts: list[str] = []
    for chunk in (stdout, stderr):
        if chunk is None:
            continue
        if isinstance(chunk, bytes):
            text = chunk.decode("utf-8", errors="replace").rstrip()
        else:
            text = chunk.rstrip()
        if text:
            parts.append(text)

    rendered = "\n".join(parts).strip() or default_text
    rendered = redact_sensitive_text(rendered, enabled=redact_secrets)
    if len(rendered) > max_chars:
        return f"{rendered[:max_chars]}\n...[truncated]..."
    return rendered
