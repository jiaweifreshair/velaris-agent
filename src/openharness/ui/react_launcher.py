"""Launch the default React terminal frontend."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shutil
import sys
from pathlib import Path

from openharness.config.paths import get_logs_dir

_LOG_FILE_NAME = "velaris.log"


def _resolve_npm() -> str:
    """Resolve the npm executable (npm.cmd on Windows)."""
    return shutil.which("npm") or "npm"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_frontend_dir() -> Path:
    """Return the React terminal frontend directory."""
    return _repo_root() / "frontend" / "terminal"


def _normalize_macos_arch(machine: str | None = None) -> str | None:
    raw = (machine or platform.machine() or "").strip().lower()
    if raw in {"arm64", "aarch64"}:
        return "arm64"
    if raw in {"x86_64", "amd64", "x64"}:
        return "x64"
    return None


def _expected_esbuild_package_dir(frontend_dir: Path) -> Path | None:
    if sys.platform != "darwin":
        return None
    arch = _normalize_macos_arch()
    if arch is None:
        return None
    return frontend_dir / "node_modules" / "@esbuild" / f"darwin-{arch}"


def _frontend_dependencies_need_refresh(frontend_dir: Path) -> bool:
    node_modules = frontend_dir / "node_modules"
    if not node_modules.exists():
        return True
    expected_esbuild_dir = _expected_esbuild_package_dir(frontend_dir)
    if expected_esbuild_dir is None:
        return False
    return not expected_esbuild_dir.exists()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(logger_name: str = "velaris") -> logging.Logger:
    """Configure logging to file + optional console.

    Log file : ~/.velaris-agent/logs/velaris.log
    Console  : stderr, enabled when VELARIS_LOG_TO_CONSOLE=1

    Returns the module-level logger so the caller can log immediately.
    """
    logs_dir = get_logs_dir()
    log_file = logs_dir / _LOG_FILE_NAME

    raw_level = os.environ.get("VELARIS_LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, raw_level, logging.INFO)

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.handlers.clear()

    # File handler — always on
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    # Console handler — opt-in via env var
    if os.environ.get("VELARIS_LOG_TO_CONSOLE", "0") == "1":
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        console_handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(console_handler)

    logger.propagate = False
    logger.info(
        "logging initialised — file=%s, level=%s",
        log_file,
        raw_level,
    )
    return logger


# ---------------------------------------------------------------------------
# Backend command builder
# ---------------------------------------------------------------------------

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
    """返回 React 前端用于拉起 backend host 的命令。"""
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


# ---------------------------------------------------------------------------
# npm install helper — shows live output via rich
# ---------------------------------------------------------------------------

async def _install_frontend_deps(frontend_dir: Path, npm: str) -> None:
    """Run ``npm install`` and stream output to the terminal.

    Raises
    ------
    RuntimeError
        When ``npm install`` exits with a non-zero return code.
    """
    from rich.console import Console

    logger = logging.getLogger("velaris.launcher")
    console = Console(stderr=True)

    console.print(
        "[bold cyan]⚡ Velaris[/bold cyan] — installing frontend dependencies "
        "(first run only, may take 10–30 s) …",
        highlight=False,
    )
    logger.info("starting npm install in %s", frontend_dir)

    process = await asyncio.create_subprocess_exec(
        npm,
        "install",
        "--no-fund",
        "--no-audit",
        cwd=str(frontend_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    # Stream output if the subprocess provides a pipe; fall back to wait().
    stdout = getattr(process, "stdout", None)
    if stdout is None:
        retcode = await process.wait()
    else:
        async for raw_line in stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            if line:
                console.print(f"  [dim]{line}[/dim]", highlight=False)
                logger.debug("[npm] %s", line)
        retcode = await process.wait()
    if retcode != 0:
        msg = f"npm install failed (exit {retcode})"
        logger.error(msg)
        raise RuntimeError(msg)

    console.print("[bold green]✓[/bold green] Frontend dependencies ready.", highlight=False)
    logger.info("npm install completed successfully")


# ---------------------------------------------------------------------------
# Main launcher
# ---------------------------------------------------------------------------

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
    demo_mode: str | None = None,
    demo_case_index: int | None = None,
    demo_cases: list[dict[str, object]] | None = None,
) -> int:
    """Launch the React terminal frontend as the default UI."""
    logger = setup_logging()

    frontend_dir = get_frontend_dir()
    package_json = frontend_dir / "package.json"
    if not package_json.exists():
        raise RuntimeError(f"React terminal frontend is missing: {package_json}")

    npm = _resolve_npm()

    if _frontend_dependencies_need_refresh(frontend_dir):
        try:
            await _install_frontend_deps(frontend_dir, npm)
        except RuntimeError:
            logger.exception("frontend dependency installation failed")
            raise

    # Prepare environment for the React TUI process.
    env = os.environ.copy()
    frontend_config_payload: dict[str, object] = {
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
    if demo_mode is not None:
        frontend_config_payload["demo_mode"] = demo_mode
    if demo_case_index is not None:
        frontend_config_payload["demo_case_index"] = demo_case_index
    if demo_cases is not None:
        frontend_config_payload["demo_cases"] = demo_cases

    frontend_config = json.dumps(frontend_config_payload, ensure_ascii=False)
    env["VELARIS_FRONTEND_CONFIG"] = frontend_config
    env["OPENHARNESS_FRONTEND_CONFIG"] = frontend_config
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
        env["VELARIS_API_KEY"] = api_key

    # Direct backend stdout/stderr to the log file via a real file descriptor.
    logs_dir = get_logs_dir()
    log_file_path = logs_dir / _LOG_FILE_NAME
    log_fd = os.open(log_file_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    logger.info("launching React TUI (stdout/stderr → %s)", log_file_path)

    process = await asyncio.create_subprocess_exec(
        npm,
        "exec",
        "--",
        "tsx",
        "src/index.tsx",
        cwd=str(frontend_dir),
        env=env,
        stdin=None,
        stdout=log_fd,
        stderr=log_fd,
    )
    retcode = await process.wait()
    os.close(log_fd)
    logger.info("React TUI exited with code %d", retcode)
    return retcode


__all__ = ["build_backend_command", "get_frontend_dir", "launch_react_tui", "setup_logging"]
