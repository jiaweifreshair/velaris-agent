"""Session persistence helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import time
from hashlib import sha1
from pathlib import Path
from typing import Any
from uuid import uuid4

from openharness.api.usage import UsageSnapshot
from openharness.config.settings import load_settings
from openharness.config.paths import get_sessions_dir
from openharness.engine.messages import ConversationMessage
from velaris_agent.persistence.factory import build_session_repository
from velaris_agent.persistence.postgres_execution import SessionRecord


def get_project_session_dir(cwd: str | Path) -> Path:
    """Return the session directory for a project."""
    path = Path(cwd).resolve()
    digest = sha1(str(path).encode("utf-8")).hexdigest()[:12]
    session_dir = get_sessions_dir() / f"{path.name}-{digest}"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def _load_session_repository():
    """按当前设置加载 session PostgreSQL 仓储。

    该 helper 把“是否启用 PostgreSQL 主线”的判断集中在一处，
    让 save/load/list 等调用点只关心仓储是否可用，而不重复解析设置。
    """

    postgres_dsn = load_settings().storage.postgres_dsn.strip()
    if not postgres_dsn:
        return None
    return build_session_repository(postgres_dsn=postgres_dsn)


def _extract_summary(messages: list[ConversationMessage]) -> str:
    """从首条用户消息提取 session 摘要。"""

    for msg in messages:
        if msg.role == "user" and msg.text.strip():
            return msg.text.strip()[:80]
    return ""


def _write_file_snapshot(*, cwd: str | Path, session_id: str, payload: dict[str, Any]) -> Path:
    """写入文件兼容层，保持现有返回值与本地恢复体验不变。"""

    session_dir = get_project_session_dir(cwd)
    data = json.dumps(payload, indent=2) + "\n"

    latest_path = session_dir / "latest.json"
    latest_path.write_text(data, encoding="utf-8")

    session_path = session_dir / f"session-{session_id}.json"
    session_path.write_text(data, encoding="utf-8")
    return latest_path


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
) -> Path:
    """Persist a session snapshot. Saves both by ID and as latest."""
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
    repository = _load_session_repository()
    if repository is not None:
        timestamp = datetime.now(UTC).isoformat()
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

    latest_path = _write_file_snapshot(cwd=cwd, session_id=sid, payload=payload)
    return latest_path


def load_session_snapshot(cwd: str | Path) -> dict[str, Any] | None:
    """Load the most recent session snapshot for the project."""
    repository = _load_session_repository()
    if repository is not None:
        record = repository.latest_by_cwd(str(Path(cwd).resolve()))
        if record is not None:
            return dict(record.snapshot_json)
    path = get_project_session_dir(cwd) / "latest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_session_snapshots(cwd: str | Path, limit: int = 20) -> list[dict[str, Any]]:
    """List saved sessions for the project, newest first."""
    repository = _load_session_repository()
    if repository is not None:
        records = repository.list_by_cwd(str(Path(cwd).resolve()))
        if records:
            return [_session_summary_from_payload(dict(record.snapshot_json)) for record in records[:limit]]

    session_dir = get_project_session_dir(cwd)
    sessions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # Named session files
    for path in sorted(session_dir.glob("session-*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            sid = data.get("session_id", path.stem.replace("session-", ""))
            seen_ids.add(sid)
            summary = data.get("summary", "")
            if not summary:
                # Extract from first user message
                for msg in data.get("messages", []):
                    if msg.get("role") == "user":
                        texts = [b.get("text", "") for b in msg.get("content", []) if b.get("type") == "text"]
                        summary = " ".join(texts).strip()[:80]
                        if summary:
                            break
            sessions.append({
                "session_id": sid,
                "summary": summary,
                "message_count": data.get("message_count", len(data.get("messages", []))),
                "model": data.get("model", ""),
                "created_at": data.get("created_at", path.stat().st_mtime),
            })
        except (json.JSONDecodeError, OSError):
            continue
        if len(sessions) >= limit:
            break

    # Also include latest.json if it has no corresponding session file
    latest_path = session_dir / "latest.json"
    if latest_path.exists() and len(sessions) < limit:
        try:
            data = json.loads(latest_path.read_text(encoding="utf-8"))
            sid = data.get("session_id", "latest")
            if sid not in seen_ids:
                summary = data.get("summary", "")
                if not summary:
                    for msg in data.get("messages", []):
                        if msg.get("role") == "user":
                            texts = [b.get("text", "") for b in msg.get("content", []) if b.get("type") == "text"]
                            summary = " ".join(texts).strip()[:80]
                            if summary:
                                break
                sessions.append({
                    "session_id": sid,
                    "summary": summary or "(latest session)",
                    "message_count": data.get("message_count", len(data.get("messages", []))),
                    "model": data.get("model", ""),
                    "created_at": data.get("created_at", latest_path.stat().st_mtime),
                })
        except (json.JSONDecodeError, OSError):
            pass

    # Sort by created_at descending
    sessions.sort(key=lambda s: s.get("created_at", 0), reverse=True)
    return sessions[:limit]


def load_session_by_id(cwd: str | Path, session_id: str) -> dict[str, Any] | None:
    """Load a specific session by ID."""
    repository = _load_session_repository()
    if repository is not None:
        record = repository.get(session_id)
        if record is not None:
            return dict(record.snapshot_json)
    session_dir = get_project_session_dir(cwd)
    # Try named session first
    path = session_dir / f"session-{session_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    # Fallback to latest.json if session_id matches
    latest = session_dir / "latest.json"
    if latest.exists():
        data = json.loads(latest.read_text(encoding="utf-8"))
        if data.get("session_id") == session_id or session_id == "latest":
            return data
    return None


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
