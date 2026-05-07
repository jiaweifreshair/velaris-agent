"""Session persistence helpers.

SQLite 主线：session 快照存储在项目内 SQLite（<project>/.velaris-agent/velaris.db）中。
旧的 JSON session 文件（latest.json / session-*.json）已彻底停用，不再读写。
"""

from __future__ import annotations

from datetime import timezone, datetime
import json
import time
from hashlib import sha1
from pathlib import Path
from typing import Any
from uuid import uuid4

from openharness.api.usage import UsageSnapshot
from openharness.config.paths import get_project_database_path, get_sessions_dir
from openharness.engine.messages import ConversationMessage
from velaris_agent.persistence.factory import build_session_repository
from velaris_agent.persistence.sqlite_execution import SessionRecord


def get_project_session_dir(cwd: str | Path) -> Path:
    """返回项目对应的 transcript 导出目录。

    注意：该目录只用于 Markdown transcript 导出，不承载 session snapshot 的正式存储。
    """

    path = Path(cwd).resolve()
    digest = sha1(str(path).encode("utf-8")).hexdigest()[:12]
    session_dir = get_sessions_dir() / f"{path.name}-{digest}"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def _load_session_repository(*, cwd: str | Path):
    """加载项目内 SQLite session 仓储。"""

    database_path = get_project_database_path(cwd)
    repository = build_session_repository(sqlite_database_path=database_path)
    if repository is None:  # pragma: no cover - 工厂异常或未来重构保护
        raise RuntimeError("session repository unavailable")
    return repository


def _extract_summary(messages: list[ConversationMessage]) -> str:
    """从首条用户消息提取 session 摘要。"""

    for msg in messages:
        if msg.role == "user" and msg.text.strip():
            return msg.text.strip()[:80]
    return ""


def _session_summary_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """把完整 session snapshot 缩成列表页需要的摘要结构。"""

    summary = payload.get("summary", "")
    if not summary:
        for msg in payload.get("messages", []):
            if msg.get("role") == "user":
                texts = [b.get("text", "") for b in msg.get("content", []) if b.get("type") == "text"]
                summary = " ".join(texts).strip()[:80]
                if summary:
                    break
    return {
        "session_id": payload.get("session_id", "latest"),
        "summary": summary or "(latest session)",
        "message_count": payload.get("message_count", len(payload.get("messages", []))),
        "model": payload.get("model", ""),
        "created_at": payload.get("created_at", 0),
    }


def save_session_snapshot(
    *,
    cwd: str | Path,
    model: str,
    system_prompt: str,
    messages: list[ConversationMessage],
    usage: UsageSnapshot,
    session_id: str | None = None,
) -> str:
    """持久化一次 session snapshot，并返回 session_id。"""

    sid = session_id or uuid4().hex[:12]
    now = time.time()
    summary = _extract_summary(messages)

    payload = {
        "session_id": sid,
        "cwd": str(Path(cwd).resolve()),
        "model": model,
        "system_prompt": system_prompt,
        "messages": [message.model_dump(mode="json") for message in messages],
        "usage": usage.model_dump(),
        "created_at": now,
        "summary": summary,
        "message_count": len(messages),
    }

    timestamp = datetime.now(timezone.utc).isoformat()
    repository = _load_session_repository(cwd=cwd)
    repository.upsert(
        SessionRecord(
            session_id=sid,
            binding_mode="attached",
            source_runtime="openharness",
            summary=summary,
            message_count=len(messages),
            created_at=timestamp,
            updated_at=timestamp,
            snapshot_json=payload,
        )
    )
    return sid


def load_session_snapshot(cwd: str | Path) -> dict[str, Any] | None:
    """Load the most recent session snapshot for the project."""
    repository = _load_session_repository(cwd=cwd)
    record = repository.latest_by_cwd(str(Path(cwd).resolve()))
    if record is None:
        return None
    return dict(record.snapshot_json)


def list_session_snapshots(cwd: str | Path, limit: int = 20) -> list[dict[str, Any]]:
    """List saved sessions for the project, newest first."""
    repository = _load_session_repository(cwd=cwd)
    records = repository.list_by_cwd(str(Path(cwd).resolve()))
    return [_session_summary_from_payload(dict(record.snapshot_json)) for record in records[:limit]]


def load_session_by_id(cwd: str | Path, session_id: str) -> dict[str, Any] | None:
    """Load a specific session by ID."""
    repository = _load_session_repository(cwd=cwd)
    record = repository.get(session_id)
    if record is None:
        return None
    snapshot = dict(record.snapshot_json)
    if snapshot.get("cwd") and snapshot.get("cwd") != str(Path(cwd).resolve()):
        return None
    return snapshot


def export_session_markdown(
    *,
    cwd: str | Path,
    messages: list[ConversationMessage],
) -> Path:
    """Export the session transcript as Markdown."""
    session_dir = get_project_session_dir(cwd)
    path = session_dir / "transcript.md"
    parts: list[str] = ["# OpenHarness Session Transcript"]
    for message in messages:
        parts.append(f"\n## {message.role.capitalize()}\n")
        text = message.text.strip()
        if text:
            parts.append(text)
        for block in message.tool_uses:
            parts.append(f"\n```tool\n{block.name} {json.dumps(block.input, ensure_ascii=True)}\n```")
        for block in message.content:
            if getattr(block, "type", "") == "tool_result":
                parts.append(f"\n```tool-result\n{block.content}\n```")
    path.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")
    return path
