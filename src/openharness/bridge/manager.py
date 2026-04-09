"""Track spawned bridge sessions for UI and commands."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from openharness.config.paths import get_data_dir
from openharness.config.settings import SecuritySettings
from openharness.bridge.session_runner import SessionHandle, spawn_session
from openharness.security import redact_sensitive_text
from openharness.security.execution import SecurityPermissionPrompt
from openharness.security.session_state import SecuritySessionState


@dataclass(frozen=True)
class BridgeSessionRecord:
    """UI-safe bridge session snapshot."""

    session_id: str
    command: str
    cwd: str
    pid: int
    status: str
    started_at: float
    output_path: str


class BridgeSessionManager:
    """Manage bridge-run child sessions and capture their output."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionHandle] = {}
        self._commands: dict[str, str] = {}
        self._output_paths: dict[str, Path] = {}
        self._copy_tasks: dict[str, asyncio.Task[None]] = {}

    async def spawn(
        self,
        *,
        session_id: str,
        command: str,
        cwd: str | Path,
        security_settings: SecuritySettings | dict[str, object] | None = None,
        security_session_state: SecuritySessionState | None = None,
        permission_prompt: SecurityPermissionPrompt | None = None,
    ) -> SessionHandle:
        """启动一个 bridge 会话，并把安全配置透传给底层执行器。"""

        handle = await spawn_session(
            session_id=session_id,
            command=command,
            cwd=cwd,
            security_settings=security_settings,
            security_session_state=security_session_state,
            permission_prompt=permission_prompt,
        )
        self._sessions[session_id] = handle
        self._commands[session_id] = command
        output_dir = get_data_dir() / "bridge"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{session_id}.log"
        output_path.write_text("", encoding="utf-8")
        self._output_paths[session_id] = output_path
        self._copy_tasks[session_id] = asyncio.create_task(self._copy_output(session_id, handle))
        return handle

    def list_sessions(self) -> list[BridgeSessionRecord]:
        items: list[BridgeSessionRecord] = []
        for session_id, handle in self._sessions.items():
            process = handle.process
            if process.returncode is None:
                status = "running"
            elif process.returncode == 0:
                status = "completed"
            else:
                status = "failed"
            items.append(
                BridgeSessionRecord(
                    session_id=session_id,
                    command=self._commands.get(session_id, ""),
                    cwd=str(handle.cwd),
                    pid=process.pid or 0,
                    status=status,
                    started_at=handle.started_at,
                    output_path=str(self._output_paths[session_id]),
                )
            )
        return sorted(items, key=lambda item: item.started_at, reverse=True)

    def read_output(
        self,
        session_id: str,
        *,
        max_bytes: int = 12000,
        redact_secrets: bool = True,
    ) -> str:
        """读取 bridge 输出尾部，并按需脱敏后返回给 UI 或命令层。"""

        path = self._output_paths.get(session_id)
        if path is None or not path.exists():
            return ""
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_bytes:
            content = content[-max_bytes:]
        return redact_sensitive_text(content, enabled=redact_secrets)

    async def stop(self, session_id: str) -> None:
        handle = self._sessions.get(session_id)
        if handle is None:
            raise ValueError(f"Unknown bridge session: {session_id}")
        await handle.kill()

    async def _copy_output(self, session_id: str, handle: SessionHandle) -> None:
        path = self._output_paths[session_id]

        async def _copy_stream(stream: asyncio.StreamReader | None) -> None:
            if stream is None:
                return
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    return
                redacted = redact_sensitive_text(
                    chunk.decode("utf-8", errors="replace"),
                    enabled=True,
                ).encode("utf-8", errors="replace")
                with path.open("ab") as stream_handle:
                    stream_handle.write(redacted)

        await asyncio.gather(
            _copy_stream(handle.process.stdout),
            _copy_stream(handle.process.stderr),
        )
        await handle.process.wait()


_DEFAULT_MANAGER: BridgeSessionManager | None = None


def get_bridge_manager() -> BridgeSessionManager:
    """Return the singleton bridge manager."""
    global _DEFAULT_MANAGER
    if _DEFAULT_MANAGER is None:
        _DEFAULT_MANAGER = BridgeSessionManager()
    return _DEFAULT_MANAGER
