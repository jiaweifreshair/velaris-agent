"""Shell command execution tool."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from openharness.security import (
    enforce_command_guard,
    render_process_output,
    resolve_security_session_state,
    resolve_security_settings,
    validate_process_workdir,
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

    @staticmethod
    def _build_shell_command(command: str) -> str:
        """构造带有 `python -> python3` 兼容层的 shell 命令。

        这个方法只在系统缺少 `python` 但存在 `python3` 时，在当前 shell
        进程里声明一个同名函数，避免历史脚本和测试因为命令名差异直接失败。
        """

        compatibility_prefix = (
            'if ! command -v python >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then '
            'python(){ command python3 "$@"; }; '
            "fi; "
        )
        return f"{compatibility_prefix}{command}"

    async def execute(  # type: ignore[override]
        self,
        arguments: BashToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        security_settings = resolve_security_settings(context.metadata.get("security_settings"))
        session_state = resolve_security_session_state(context.metadata.get("security_session_state"))
        permission_prompt = context.metadata.get("permission_prompt")
        guard_error = await enforce_command_guard(
            arguments.command,
            tool_name=self.name,
            security_settings=security_settings,
            session_state=session_state,
            permission_prompt=permission_prompt if callable(permission_prompt) else None,
        )
        if guard_error is not None:
            return ToolResult(output=guard_error, is_error=True)

        workdir_error = validate_process_workdir(arguments.cwd)
        if workdir_error is not None:
            return ToolResult(output=workdir_error, is_error=True)

        cwd = Path(arguments.cwd).expanduser() if arguments.cwd else context.cwd
        process = await asyncio.create_subprocess_exec(
            "/bin/bash",
            "-lc",
            self._build_shell_command(arguments.command),
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

        text = render_process_output(
            stdout=stdout,
            stderr=stderr,
            redact_secrets=security_settings.redact_secrets,
        )

        return ToolResult(
            output=text,
            is_error=process.returncode != 0,
            metadata={"returncode": process.returncode},
        )
