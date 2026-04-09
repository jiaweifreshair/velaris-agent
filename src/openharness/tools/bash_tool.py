"""Shell command execution tool."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from openharness.config.settings import SecuritySettings
from openharness.security import (
    SecuritySessionState,
    evaluate_command_guard,
    redact_sensitive_text,
    validate_workdir,
)
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class BashToolInput(BaseModel):
    """Arguments for the bash tool."""

    command: str = Field(description="Shell command to execute")
    cwd: str | None = Field(default=None, description="Working directory override")
    timeout_seconds: int = Field(default=120, ge=1, le=600)


class BashTool(BaseTool):
    """Execute a shell command with stdout/stderr capture."""

    name = "bash"
    description = "Run a shell command in the local repository."
    input_model = BashToolInput

    async def execute(  # type: ignore[override]
        self,
        arguments: BashToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        security_settings_raw = context.metadata.get("security_settings")
        if isinstance(security_settings_raw, SecuritySettings):
            security_settings = security_settings_raw
        elif isinstance(security_settings_raw, dict):
            security_settings = SecuritySettings.model_validate(security_settings_raw)
        else:
            security_settings = SecuritySettings()

        session_state_raw = context.metadata.get("security_session_state")
        if isinstance(session_state_raw, SecuritySessionState):
            session_state = session_state_raw
        else:
            session_state = SecuritySessionState()

        guard = evaluate_command_guard(
            arguments.command,
            approval_mode=security_settings.approval_mode,
            approved_pattern_ids=session_state.approved_command_patterns,
        )
        permission_prompt = context.metadata.get("permission_prompt")
        if guard.requires_confirmation:
            if not callable(permission_prompt):
                return ToolResult(
                    output=f"{guard.reason}\n未提供审批回调，框架已阻止执行。",
                    is_error=True,
                )
            confirmed = await permission_prompt(
                self.name,
                f"{guard.reason}\n命令: {arguments.command[:400]}",
            )
            if not confirmed:
                return ToolResult(
                    output="危险命令审批未通过，执行已取消。",
                    is_error=True,
                )
            if guard.matched_pattern_id is not None:
                session_state.approved_command_patterns.add(guard.matched_pattern_id)
        elif not guard.allowed:
            return ToolResult(output=guard.reason, is_error=True)

        if arguments.cwd:
            workdir_error = validate_workdir(arguments.cwd)
            if workdir_error is not None:
                return ToolResult(output=workdir_error, is_error=True)

        cwd = Path(arguments.cwd).expanduser() if arguments.cwd else context.cwd
        process = await asyncio.create_subprocess_exec(
            "/bin/bash",
            "-lc",
            arguments.command,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=arguments.timeout_seconds,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return ToolResult(
                output=f"Command timed out after {arguments.timeout_seconds} seconds",
                is_error=True,
            )

        parts = []
        if stdout:
            parts.append(stdout.decode("utf-8", errors="replace").rstrip())
        if stderr:
            parts.append(stderr.decode("utf-8", errors="replace").rstrip())

        text = "\n".join(part for part in parts if part).strip()
        if not text:
            text = "(no output)"

        text = redact_sensitive_text(text, enabled=security_settings.redact_secrets)
        if len(text) > 12000:
            text = f"{text[:12000]}\n...[truncated]..."

        return ToolResult(
            output=text,
            is_error=process.returncode != 0,
            metadata={"returncode": process.returncode},
        )
