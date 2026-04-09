"""Tool for triggering local named jobs on demand."""

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
from openharness.services.cron import get_cron_job
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class RemoteTriggerToolInput(BaseModel):
    """Arguments for triggering a local named job."""

    name: str = Field(description="Cron job name")
    timeout_seconds: int = Field(default=120, ge=1, le=600)


class RemoteTriggerTool(BaseTool):
    """Run a registered cron job immediately."""

    name = "remote_trigger"
    description = "Trigger a configured local cron-style job immediately."
    input_model = RemoteTriggerToolInput

    async def execute(  # type: ignore[override]
        self,
        arguments: RemoteTriggerToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        job = get_cron_job(arguments.name)
        if job is None:
            return ToolResult(output=f"Cron job not found: {arguments.name}", is_error=True)

        security_settings = resolve_security_settings(context.metadata.get("security_settings"))
        session_state = resolve_security_session_state(context.metadata.get("security_session_state"))
        permission_prompt = context.metadata.get("permission_prompt")

        cwd = Path(job.get("cwd") or context.cwd).expanduser()
        workdir_error = validate_process_workdir(cwd)
        if workdir_error is not None:
            return ToolResult(output=workdir_error, is_error=True)

        guard_error = await enforce_command_guard(
            str(job["command"]),
            tool_name=self.name,
            security_settings=security_settings,
            session_state=session_state,
            permission_prompt=permission_prompt if callable(permission_prompt) else None,
        )
        if guard_error is not None:
            return ToolResult(output=guard_error, is_error=True)

        process = await asyncio.create_subprocess_exec(
            "/bin/bash",
            "-lc",
            str(job["command"]),
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
                output=f"Remote trigger timed out after {arguments.timeout_seconds} seconds",
                is_error=True,
            )

        body = render_process_output(
            stdout=stdout,
            stderr=stderr,
            redact_secrets=security_settings.redact_secrets,
        )
        return ToolResult(
            output=f"Triggered {arguments.name}\n{body}",
            is_error=process.returncode != 0,
            metadata={"returncode": process.returncode},
        )
