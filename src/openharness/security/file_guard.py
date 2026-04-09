"""文件系统安全边界：路径解析、敏感文件识别与写入保护。"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_tool_path(base: Path, candidate: str) -> Path:
    """把工具输入路径解析成绝对路径，统一相对路径与 `~` 展开行为。"""

    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


_HOME = str(Path.home())
_PROTECTED_WRITE_PATHS = {
    os.path.realpath(path)
    for path in (
        os.path.join(_HOME, ".ssh", "authorized_keys"),
        os.path.join(_HOME, ".ssh", "id_rsa"),
        os.path.join(_HOME, ".ssh", "id_ed25519"),
        os.path.join(_HOME, ".ssh", "config"),
        os.path.join(_HOME, ".netrc"),
        os.path.join(_HOME, ".pgpass"),
        os.path.join(_HOME, ".npmrc"),
        os.path.join(_HOME, ".pypirc"),
        os.path.join(_HOME, ".bashrc"),
        os.path.join(_HOME, ".zshrc"),
        os.path.join(_HOME, ".profile"),
        os.path.join(_HOME, ".bash_profile"),
        os.path.join(_HOME, ".zprofile"),
        os.path.join(_HOME, ".velaris-agent", "settings.json"),
        os.path.join(_HOME, ".velaris-agent", ".env"),
        "/etc/sudoers",
        "/etc/passwd",
        "/etc/shadow",
    )
}

_PROTECTED_WRITE_PREFIXES = [
    os.path.realpath(path) + os.sep
    for path in (
        os.path.join(_HOME, ".ssh"),
        os.path.join(_HOME, ".aws"),
        os.path.join(_HOME, ".gnupg"),
        os.path.join(_HOME, ".kube"),
        os.path.join(_HOME, ".docker"),
        os.path.join(_HOME, ".azure"),
        os.path.join(_HOME, ".config", "gh"),
        "/etc/sudoers.d",
        "/etc/systemd",
    )
]

_SENSITIVE_READ_SUFFIXES = (
    ".env",
    ".netrc",
    ".pgpass",
    ".npmrc",
    ".pypirc",
)


def is_protected_write_path(path: Path) -> bool:
    """判断路径是否属于禁止直接写入的系统/凭据位置。"""

    resolved = os.path.realpath(str(path))
    if resolved in _PROTECTED_WRITE_PATHS:
        return True
    return any(resolved.startswith(prefix) for prefix in _PROTECTED_WRITE_PREFIXES)


def looks_like_sensitive_read_path(path: Path) -> bool:
    """判断路径是否像敏感读取目标，用于读取后的强制脱敏提示。"""

    resolved = os.path.realpath(str(path))
    basename = os.path.basename(resolved)
    if basename in {"settings.json", "credentials.json"} and ".velaris-agent" in resolved:
        return True
    if basename.startswith("id_") and os.path.dirname(resolved).endswith(".ssh"):
        return True
    return basename.endswith(_SENSITIVE_READ_SUFFIXES)
