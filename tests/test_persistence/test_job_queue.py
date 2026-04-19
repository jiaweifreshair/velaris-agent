"""SQLite 任务队列测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import velaris_agent.persistence.job_queue as job_queue_module
from velaris_agent.persistence.job_queue import SqliteJobQueue, run_jobs_once
from velaris_agent.persistence.schema import bootstrap_sqlite_schema
from velaris_agent.persistence.sqlite_helpers import get_project_database_path


def test_sqlite_job_queue_roundtrip(tmp_path: Path) -> None:
    """队列应完成 enqueue / claim / mark_succeeded / get 最小闭环。"""

    database_path = get_project_database_path(tmp_path)
    bootstrap_sqlite_schema(database_path)

    queue = SqliteJobQueue(database_path)
    job_id = queue.enqueue(
        "self_evolution_review",
        "u-save:travel:2",
        {"user_id": "u-save", "scenario": "travel", "window": 10},
    )

    queued = queue.get(job_id)
    assert queued is not None
    assert queued.status == "queued"
    assert queued.payload["user_id"] == "u-save"

    claimed = queue.claim_next(["self_evolution_review"])
    assert claimed is not None
    assert claimed.job_id == job_id
    assert claimed.status == "running"
    assert claimed.attempt_count == 1
    assert claimed.current_run_id is not None

    queue.mark_succeeded(job_id)

    succeeded = queue.get(job_id)
    assert succeeded is not None
    assert succeeded.status == "succeeded"
    assert succeeded.finished_at is not None
    runs = queue.list_runs(job_id)
    assert len(runs) == 1
    assert runs[0].status == "succeeded"
    assert runs[0].attempt_count == 1
    assert runs[0].finished_at is not None


def test_run_jobs_once_processes_self_evolution_jobs_sqlite(tmp_path: Path, monkeypatch) -> None:
    """run_jobs_once 应能在 SQLite 表上顺序执行 self_evolution_review 任务。"""

    database_path = get_project_database_path(tmp_path)
    bootstrap_sqlite_schema(database_path)

    processed_payloads: list[dict[str, Any]] = []

    def fake_run_self_evolution_review_job(*, sqlite_database_path: str, payload: dict[str, Any]):
        """记录 worker 收到的 payload，避免真实执行自进化。"""

        assert sqlite_database_path == str(database_path)
        processed_payloads.append(dict(payload))
        return {"status": "ok"}

    monkeypatch.setattr(
        job_queue_module,
        "_run_self_evolution_review_job",
        fake_run_self_evolution_review_job,
    )

    queue = SqliteJobQueue(database_path)
    first_job_id = queue.enqueue(
        "self_evolution_review",
        "u-save:travel:2",
        {"user_id": "u-save", "scenario": "travel", "window": 10},
    )
    second_job_id = queue.enqueue(
        "self_evolution_review",
        "u-save:travel:4",
        {"user_id": "u-save", "scenario": "travel", "window": 10},
    )

    processed = run_jobs_once(str(database_path), limit=5)

    assert processed == 2
    assert [payload["scenario"] for payload in processed_payloads] == ["travel", "travel"]
    assert queue.get(first_job_id).status == "succeeded"
    assert queue.get(second_job_id).status == "succeeded"
    assert len(queue.list_runs(first_job_id)) == 1
    assert len(queue.list_runs(second_job_id)) == 1

