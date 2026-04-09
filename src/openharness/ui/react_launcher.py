"""Launch the default React terminal frontend."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path


def _resolve_npm() -> str:
    """Resolve the npm executable (npm.cmd on Windows)."""
    return shutil.which("npm") or "npm"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_frontend_dir() -> Path:
    """Return the React terminal frontend directory."""
    return _repo_root() / "frontend" / "terminal"


def build_backend_command(
    *,
    cwd: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    api_key: str | None = None,
) -> list[str]:
    """返回 React 前端用于拉起 backend host 的命令。

    敏感的 API key 不再通过命令行参数传递，避免它出现在进程列表或
    前端配置 JSON 中；如有需要，由调用方通过环境变量透传给后端。
    """

    command = [sys.executable, "-m", "velaris_agent", "--backend-only"]
    if cwd:
        command.extend(["--cwd", cwd])
    if model:
        command.extend(["--model", model])
    if base_url:
        command.extend(["--base-url", base_url])
    if system_prompt:
        command.extend(["--system-prompt", system_prompt])
    return command


async def launch_react_tui(
    *,
    prompt: str | None = None,
    cwd: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    api_key: str | None = None,
) -> int:
    """Launch the React terminal frontend as the default UI."""
    frontend_dir = get_frontend_dir()
    package_json = frontend_dir / "package.json"
    if not package_json.exists():
        raise RuntimeError(f"React terminal frontend is missing: {package_json}")

    npm = _resolve_npm()

    if not (frontend_dir / "node_modules").exists():
        install = await asyncio.create_subprocess_exec(
            npm,
            "install",
            "--no-fund",
            "--no-audit",
            cwd=str(frontend_dir),
        )
        if await install.wait() != 0:
            raise RuntimeError("Failed to install React terminal frontend dependencies")

    env = os.environ.copy()
    frontend_config = json.dumps(
        {
            "backend_command": build_backend_command(
                cwd=cwd or str(Path.cwd()),
                model=model,
                base_url=base_url,
                system_prompt=system_prompt,
                api_key=api_key,
            ),
            "initial_prompt": prompt,
        }
    )
    env["VELARIS_FRONTEND_CONFIG"] = frontend_config
    env["OPENHARNESS_FRONTEND_CONFIG"] = frontend_config
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
        env["VELARIS_API_KEY"] = api_key
    process = await asyncio.create_subprocess_exec(
        npm,
        "exec",
        "--",
        "tsx",
        "src/index.tsx",
        cwd=str(frontend_dir),
        env=env,
        stdin=None,
        stdout=None,
        stderr=None,
    )
    return await process.wait()


__all__ = ["build_backend_command", "get_frontend_dir", "launch_react_tui"]
