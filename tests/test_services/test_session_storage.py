"""Tests for session persistence."""

from __future__ import annotations

from pathlib import Path

from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock
from velaris_agent.persistence.postgres_execution import SessionRecord
from openharness.services.session_storage import (
    export_session_markdown,
    list_session_snapshots,
    load_session_by_id,
    load_session_snapshot,
    save_session_snapshot,
)


def test_save_and_load_session_snapshot(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()

    path = save_session_snapshot(
        cwd=project,
        model="claude-test",
        system_prompt="system",
        messages=[ConversationMessage(role="user", content=[TextBlock(text="hello")])],
        usage=UsageSnapshot(input_tokens=1, output_tokens=2),
    )

    assert path.exists()
    snapshot = load_session_snapshot(project)
    assert snapshot is not None
    assert snapshot["model"] == "claude-test"
    assert snapshot["usage"]["output_tokens"] == 2


def test_export_session_markdown(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()

    path = export_session_markdown(
        cwd=project,
        messages=[
            ConversationMessage(role="user", content=[TextBlock(text="hello")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="world")]),
        ],
    )

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "OpenHarness Session Transcript" in content
    assert "hello" in content
    assert "world" in content


def test_session_storage_prefers_postgres_repository_when_available(tmp_path: Path, monkeypatch):
    """配置 PostgreSQL 主线后，session save/load/list/by_id 应优先走仓储。"""

    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()

    class FakeSessionRepository:
        def __init__(self) -> None:
            self.records: dict[str, SessionRecord] = {}

        def upsert(self, record: SessionRecord) -> SessionRecord:
            self.records[record.session_id] = record
            return record

        def get(self, session_id: str) -> SessionRecord | None:
            return self.records.get(session_id)

        def latest_by_cwd(self, cwd: str) -> SessionRecord | None:
            matches = [
                record for record in self.records.values() if record.snapshot_json.get("cwd") == cwd
            ]
            if not matches:
                return None
            return sorted(matches, key=lambda item: item.updated_at, reverse=True)[0]

        def list_by_cwd(self, cwd: str) -> list[SessionRecord]:
            matches = [
                record for record in self.records.values() if record.snapshot_json.get("cwd") == cwd
            ]
            return sorted(matches, key=lambda item: item.updated_at, reverse=True)

    repository = FakeSessionRepository()
    monkeypatch.setattr(
        "openharness.services.session_storage._load_session_repository",
        lambda: repository,
        raising=False,
    )

    path = save_session_snapshot(
        cwd=project,
        model="claude-test",
        system_prompt="system",
        messages=[ConversationMessage(role="user", content=[TextBlock(text="hello postgres")])],
        usage=UsageSnapshot(input_tokens=1, output_tokens=2),
        session_id="session-pg-mainline",
    )

    assert path.exists()
    assert repository.records["session-pg-mainline"].source_runtime == "openharness"
    assert repository.records["session-pg-mainline"].snapshot_json["model"] == "claude-test"

    latest = load_session_snapshot(project)
    listed = list_session_snapshots(project)
    by_id = load_session_by_id(project, "session-pg-mainline")

    assert latest is not None
    assert latest["session_id"] == "session-pg-mainline"
    assert listed[0]["session_id"] == "session-pg-mainline"
    assert by_id is not None
    assert by_id["usage"]["output_tokens"] == 2
