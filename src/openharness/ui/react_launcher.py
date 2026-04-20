"""Launch the default React terminal frontend."""

from __future__ import annotations

import asyncio
import json
import os
import platform
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


def _normalize_macos_arch(machine: str | None = None) -> str | None:
    """把当前机器架构标准化为 esbuild 在 macOS 上使用的后缀。

    这里专门处理 arm64 与 x64 两个常见值，避免在 Apple Silicon 和
    Intel Mac 之间切换时误用错误的平台二进制包。
    """

    raw = (machine or platform.machine() or "").strip().lower()
    if raw in {"arm64", "aarch64"}:
        return "arm64"
    if raw in {"x86_64", "amd64", "x64"}:
        return "x64"
    return None


def _expected_esbuild_package_dir(frontend_dir: Path) -> Path | None:
    """返回当前 macOS 平台对应的 esbuild 原生包目录。"""

    if sys.platform != "darwin":
        return None
    arch = _normalize_macos_arch()
    if arch is None:
        return None
    return frontend_dir / "node_modules" / "@esbuild" / f"darwin-{arch}"


def _frontend_dependencies_need_refresh(frontend_dir: Path) -> bool:
    """判断前端依赖是否需要重新安装。

    除了 node_modules 缺失，还会检查当前机器对应的 esbuild 原生包是否存在；
    如果 node_modules 是别的架构安装出来的，这里会触发重新安装，避免启动时
    才在 tsx/esbuild 里爆出架构不匹配错误。
    """

    node_modules = frontend_dir / "node_modules"
    if not node_modules.exists():
        return True
    expected_esbuild_dir = _expected_esbuild_package_dir(frontend_dir)
    if expected_esbuild_dir is None:
        return False
    return not expected_esbuild_dir.exists()


def build_backend_command(
    *,
    cwd: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    api_format: str | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    api_key: str | None = None,
    auto_compact_threshold_tokens: int | None = None,
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
    if provider:
        command.extend(["--provider", provider])
    if api_format:
        command.extend(["--api-format", api_format])
    if base_url:
        command.extend(["--base-url", base_url])
    if system_prompt:
        command.extend(["--system-prompt", system_prompt])
    if auto_compact_threshold_tokens is not None:
        command.extend(["--auto-compact-threshold-tokens", str(auto_compact_threshold_tokens)])
    return command


async def launch_react_tui(
    *,
    prompt: str | None = None,
    cwd: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    api_format: str | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    api_key: str | None = None,
    auto_compact_threshold_tokens: int | None = None,
) -> int:
    """Launch the React terminal frontend as the default UI."""
    frontend_dir = get_frontend_dir()
    package_json = frontend_dir / "package.json"
    if not package_json.exists():
        raise RuntimeError(f"React terminal frontend is missing: {package_json}")

    npm = _resolve_npm()

    if _frontend_dependencies_need_refresh(frontend_dir):
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
                    provider=provider,
                    api_format=api_format,
                    base_url=base_url,
                    system_prompt=system_prompt,
                    api_key=api_key,
                    auto_compact_threshold_tokens=auto_compact_threshold_tokens,
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
