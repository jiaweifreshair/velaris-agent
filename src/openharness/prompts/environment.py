"""Environment detection for system prompt construction.

Gathers OS, shell, platform, working directory, date, and git info.
"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class EnvironmentInfo:
    """Snapshot of the current runtime environment."""

    os_name: str
    os_version: str
    platform_machine: str
    shell: str
    cwd: str
    home_dir: str
    date: str
    python_version: str
    is_git_repo: bool
    git_branch: str | None = None
    hostname: str = ""
    extra: dict[str, str] = field(default_factory=dict)


def detect_os() -> tuple[str, str]:
    """Return (os_name, os_version) for the current platform."""
    system = platform.system()
    if system == "Linux":
        try:
            import distro  # type: ignore[import-untyped]
            return "Linux", distro.version(pretty=True) or platform.release()
        except ImportError:
            return "Linux", platform.release()
    elif system == "Darwin":
        mac_ver = platform.mac_ver()[0]
        return "macOS", mac_ver or platform.release()
    elif system == "Windows":
        win_ver = platform.version()
        return "Windows", win_ver
    return system, platform.release()


def detect_shell() -> str:
    """Detect the user's shell."""
    shell = os.environ.get("SHELL", "")
    if shell:
        return Path(shell).name

    # Fallback: check for common shells on PATH
    for candidate in ("bash", "zsh", "fish", "sh"):
        if shutil.which(candidate):
            return candidate

    return "unknown"


def detect_git_info(cwd: str) -> tuple[bool, str | None]:
    """Check if cwd is inside a git repo and return (is_git_repo, branch_name)."""
    try:
        start = Path(cwd).resolve()
    except (OSError, RuntimeError):
        return False, None

    for directory in (start, *start.parents):
        git_path = directory / ".git"
        if not git_path.exists():
            continue

        git_dir = _resolve_git_dir(git_path)
        if git_dir is None:
            return True, None

        return True, _read_git_branch(git_dir)

    return False, None


def _resolve_git_dir(git_path: Path) -> Path | None:
    """Return the git metadata directory for normal repos and worktrees."""
    if git_path.is_dir():
        return git_path

    try:
        content = git_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None

    prefix = "gitdir:"
    if not content.lower().startswith(prefix):
        return None

    raw_path = content[len(prefix):].strip()
    git_dir = Path(raw_path)
    if not git_dir.is_absolute():
        git_dir = git_path.parent / git_dir

    try:
        return git_dir.resolve()
    except OSError:
        return git_dir


def _read_git_branch(git_dir: Path) -> str | None:
    """Read the current branch from HEAD without invoking git."""
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None

    prefix = "ref: refs/heads/"
    if not head.startswith(prefix):
        return None

    branch = head[len(prefix):].strip()
    return branch or None


def get_environment_info(cwd: str | None = None) -> EnvironmentInfo:
    """Gather all environment information into an EnvironmentInfo snapshot."""
    if cwd is None:
        cwd = os.getcwd()

    os_name, os_version = detect_os()
    shell = detect_shell()
    is_git, branch = detect_git_info(cwd)

    return EnvironmentInfo(
        os_name=os_name,
        os_version=os_version,
        platform_machine=platform.machine(),
        shell=shell,
        cwd=cwd,
        home_dir=str(Path.home()),
        date=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
        python_version=platform.python_version(),
        is_git_repo=is_git,
        git_branch=branch,
        hostname=platform.node(),
    )
