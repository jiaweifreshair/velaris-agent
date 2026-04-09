"""Minimal bridge session spawner."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

from openharness.config.settings import SecuritySettings
from openharness.security import (
    SecuritySessionState,
    enforce_command_guard,
    resolve_security_session_state,
    resolve_security_settings,
    validate_process_workdir,
)
from openharness.security.execution import SecurityPermissionPrompt


@dataclass
class SessionHandle:
    """Handle for a spawned bridge session."""

    session_id: str
    process: asyncio.subprocess.Process
    cwd: Path
    started_at: float = field(default_factory=time.time)

    async def kill(self) -> None:
        """Terminate the session process."""
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=3)
        except asyncio.TimeoutError:
            self.process.kill()
            await self.process.wait()


async def spawn_session(
    *,
    session_id: str,
    command: str,
    cwd: str | Path,
    security_settings: SecuritySettings | dict[str, object] | None = None,
    security_session_state: SecuritySessionState | None = None,
    permission_prompt: SecurityPermissionPrompt | None = None,
) -> SessionHandle:
    """启动 bridge 管理的子会话，并在执行前套用统一安全守卫。"""

    resolved_settings = resolve_security_settings(security_settings)
    resolved_session_state = resolve_security_session_state(security_session_state)
    workdir_error = validate_process_workdir(cwd)
    if workdir_error is not None:
        raise ValueError(workdir_error)
    guard_error = await enforce_command_guard(
        command,
        tool_name="bridge_spawn",
        security_settings=resolved_settings,
        session_state=resolved_session_state,
        permission_prompt=permission_prompt,
    )
    if guard_error is not None:
        raise ValueError(guard_error)

    resolved_cwd = Path(cwd).expanduser().resolve()
    process = await asyncio.create_subprocess_exec(
        "/bin/bash",
        "-lc",
        command,
        cwd=str(resolved_cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return SessionHandle(session_id=session_id, process=process, cwd=resolved_cwd)
