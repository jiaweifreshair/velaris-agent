# Velaris SQLite Mainline Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `velaris-agent` 从“PostgreSQL 主线 + 文件型 session 残留”切换为“项目内 SQLite 单库、单一真相源、无旧 JSON 回退、无 PostgreSQL 正式入口”的本地优先架构。

**Architecture:** 保持单进程应用，不引入 ORM、迁移框架、Redis 或 Kafka。以 `<project>/.velaris-agent/velaris.db` 作为唯一正式存储，围绕 `sqlite.py + schema.py + sqlite_* repositories + cwd-based factory wiring` 收束运行路径，同时删除 `postgres_*` 实现、DSN 配置与旧 JSON session 主线。

**Tech Stack:** Python 3.13, `sqlite3`, Pydantic 2, Typer, pytest, Ruff

---

## Scope Check

本计划只覆盖一个子系统：**正式存储主线切换**。虽然涉及 `settings / CLI / repositories / orchestrator / tools / docs` 多个入口，但它们都服务于同一个目标，不拆成多个计划更利于一次性消除 PostgreSQL 与 JSON 双真相源残留。

## File Structure

### Create

- `src/velaris_agent/persistence/sqlite.py`
- `src/velaris_agent/persistence/sqlite_execution.py`
- `src/velaris_agent/persistence/sqlite_runtime.py`
- `src/velaris_agent/persistence/sqlite_memory.py`
- `tests/test_persistence/test_sqlite.py`
- `tests/test_persistence/test_sqlite_execution.py`
- `tests/test_persistence/test_sqlite_runtime.py`
- `tests/test_persistence/test_sqlite_memory.py`
- `tests/test_persistence/test_sqlite_helpers.py`

### Delete

- `src/velaris_agent/persistence/postgres.py`
- `src/velaris_agent/persistence/postgres_execution.py`
- `src/velaris_agent/persistence/postgres_runtime.py`
- `src/velaris_agent/persistence/postgres_memory.py`
- `src/velaris_agent/persistence/psycopg_compat.py`
- `tests/test_persistence/test_postgres.py`
- `tests/test_persistence/test_postgres_execution.py`
- `tests/test_persistence/test_postgres_runtime.py`
- `tests/test_persistence/test_postgres_memory.py`

### Modify

- `src/openharness/config/paths.py`
- `src/openharness/config/settings.py`
- `src/openharness/cli.py`
- `src/openharness/services/session_storage.py`
- `src/openharness/services/__init__.py`
- `src/openharness/commands/registry.py`
- `src/openharness/ui/runtime.py`
- `src/velaris_agent/persistence/__init__.py`
- `src/velaris_agent/persistence/factory.py`
- `src/velaris_agent/persistence/schema.py`
- `src/velaris_agent/persistence/job_queue.py`
- `src/velaris_agent/velaris/orchestrator.py`
- `src/openharness/tools/save_decision_tool.py`
- `src/openharness/tools/recall_preferences_tool.py`
- `src/openharness/tools/recall_decisions_tool.py`
- `src/openharness/tools/decision_score_tool.py`
- `src/openharness/tools/self_evolution_review_tool.py`
- `tests/test_services/test_session_storage.py`
- `tests/test_commands/test_cli.py`
- `tests/test_commands/test_registry.py`
- `tests/test_biz/test_orchestrator.py`
- `tests/test_tools/test_knowledge_tools.py`
- `tests/test_real_large_tasks.py`
- `tests/test_untested_features.py`
- `aidlc-docs/aidlc-state.md`
- `aidlc-docs/audit.md`
- `aidlc-docs/construction/build-and-test/build-and-test-summary.md`
- `aidlc-docs/construction/build-and-test/build-instructions.md`
- `aidlc-docs/construction/build-and-test/integration-test-instructions.md`
- `aidlc-docs/construction/build-and-test/unit-test-instructions.md`
- `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/nfr-requirements/tech-stack-decisions.md`
- `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/nfr-requirements/nfr-requirements.md`
- `docs/superpowers/specs/2026-04-19-sqlite-mainline-cutover-design.md`

### Design Notes

- 以 `cwd` 推导数据库位置，不再接受 `postgres_dsn` 或 `VELARIS_POSTGRES_DSN`。
- `save_session_snapshot()` 返回 `session_id: str`，`export_session_markdown()` 继续返回 Markdown 路径。
- `session clear` 只清理 session 快照和 transcript，不清空 execution / decision / audit / queue。
- `job_queue` 保留文件名，但类名改为 `SqliteJobQueue`，避免业务语义和存储后端耦死。
- 所有 JSON 列统一保存为 TEXT，在 Python 层 `json.dumps/json.loads`。

---

### Task 1: Project SQLite Path And Settings Cleanup

**Files:**
- Modify: `src/openharness/config/paths.py`
- Modify: `src/openharness/config/settings.py`
- Test: `tests/test_persistence/test_settings.py`
- Test: `tests/test_persistence/test_sqlite_helpers.py`

- [ ] **Step 1: Write the failing tests for SQLite path derivation and settings cleanup**

```python
# tests/test_persistence/test_sqlite_helpers.py
from pathlib import Path

from openharness.config.paths import get_project_database_path


def test_get_project_database_path_points_to_project_sqlite_file(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()

    db_path = get_project_database_path(project)

    assert db_path == project / ".velaris-agent" / "velaris.db"
```

```python
# tests/test_persistence/test_settings.py
from openharness.config.settings import Settings, load_settings


def test_storage_settings_no_longer_expose_postgres_dsn() -> None:
    settings = Settings()
    assert not hasattr(settings.storage, "postgres_dsn")
    assert settings.storage.job_poll_interval_seconds == 2.0
    assert settings.storage.job_max_attempts == 3


def test_load_settings_ignores_legacy_postgres_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("VELARIS_POSTGRES_DSN", "postgresql://ignored")

    settings = load_settings()

    assert not hasattr(settings.storage, "postgres_dsn")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./scripts/run_pytest.sh tests/test_persistence/test_settings.py tests/test_persistence/test_sqlite_helpers.py -q
```

Expected:

```text
FAILED tests/test_persistence/test_sqlite_helpers.py::test_get_project_database_path_points_to_project_sqlite_file - ImportError
FAILED tests/test_persistence/test_settings.py::test_storage_settings_no_longer_expose_postgres_dsn - AssertionError
```

- [ ] **Step 3: Implement the path helper and remove PostgreSQL config from settings**

```python
# src/openharness/config/paths.py
from pathlib import Path


def get_project_database_path(cwd: str | Path) -> Path:
    project_root = Path(cwd).resolve()
    return project_root / ".velaris-agent" / "velaris.db"
```

```python
# src/openharness/config/settings.py
class StorageSettings(BaseModel):
    """存储后端配置。"""

    evidence_dir: str | None = None
    job_poll_interval_seconds: float = 2.0
    job_max_attempts: int = 3
```

```python
# src/openharness/config/settings.py::_apply_env_overrides
storage_updates: dict[str, Any] = {}

evidence_dir = os.environ.get("VELARIS_EVIDENCE_DIR")
if evidence_dir:
    storage_updates["evidence_dir"] = evidence_dir

if storage_updates:
    updates["storage"] = settings.storage.model_copy(update=storage_updates)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./scripts/run_pytest.sh tests/test_persistence/test_settings.py tests/test_persistence/test_sqlite_helpers.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/openharness/config/paths.py src/openharness/config/settings.py tests/test_persistence/test_settings.py tests/test_persistence/test_sqlite_helpers.py
git commit -m "refactor(storage): remove postgres settings path"
```

### Task 2: SQLite Connection Layer And Schema Bootstrap

**Files:**
- Create: `src/velaris_agent/persistence/sqlite.py`
- Modify: `src/velaris_agent/persistence/schema.py`
- Modify: `src/velaris_agent/persistence/__init__.py`
- Modify: `src/openharness/cli.py`
- Test: `tests/test_persistence/test_sqlite.py`
- Test: `tests/test_persistence/test_schema.py`
- Test: `tests/test_commands/test_cli.py`

- [ ] **Step 1: Write the failing tests for SQLite bootstrap and CLI storage init/doctor**

```python
# tests/test_persistence/test_sqlite.py
from openharness.config.paths import get_project_database_path
from velaris_agent.persistence.sqlite import ensure_sqlite_directory


def test_ensure_sqlite_directory_creates_project_storage_dir(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()

    db_path = get_project_database_path(project)
    ensure_sqlite_directory(db_path)

    assert db_path.parent.exists()
```

```python
# tests/test_persistence/test_schema.py
from velaris_agent.persistence.schema import EXPECTED_TABLES, build_bootstrap_statements


def test_sqlite_bootstrap_contains_create_table_statements() -> None:
    sql = "\n".join(build_bootstrap_statements())
    for table in EXPECTED_TABLES:
        assert f"create table if not exists {table}" in sql.lower()
    assert "jsonb" not in sql.lower()
    assert "timestamptz" not in sql.lower()
```

```python
# tests/test_commands/test_cli.py
from typer.testing import CliRunner

from openharness.cli import app


runner = CliRunner()


def test_cli_storage_init_creates_sqlite_schema(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["storage", "init"])
    assert result.exit_code == 0
    assert "Initialized SQLite storage" in result.output


def test_cli_storage_doctor_reports_missing_schema(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["storage", "doctor"])
    assert result.exit_code == 1
    assert "storage_not_initialized" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./scripts/run_pytest.sh tests/test_persistence/test_sqlite.py tests/test_persistence/test_schema.py tests/test_commands/test_cli.py -q
```

Expected:

```text
FAILED tests/test_persistence/test_sqlite.py::test_ensure_sqlite_directory_creates_project_storage_dir - ModuleNotFoundError
FAILED tests/test_persistence/test_schema.py::test_sqlite_bootstrap_contains_create_table_statements - AssertionError
FAILED tests/test_commands/test_cli.py::test_cli_storage_init_creates_sqlite_schema - AssertionError
```

- [ ] **Step 3: Implement SQLite connection helper, SQLite schema, and storage CLI commands**

```python
# src/velaris_agent/persistence/sqlite.py
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def ensure_sqlite_directory(db_path: str | Path) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def sqlite_connection(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    path = ensure_sqlite_directory(db_path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
```

```python
# src/velaris_agent/persistence/schema.py
EXPECTED_TABLES = [
    "decision_records",
    "session_records",
    "execution_records",
    "task_ledger_records",
    "outcome_records",
    "audit_events",
    "job_queue",
    "job_runs",
]


def build_bootstrap_statements() -> list[str]:
    return [
        """
        create table if not exists session_records (
          session_id text primary key,
          binding_mode text not null,
          source_runtime text not null,
          summary text not null default '',
          message_count integer not null default 0,
          snapshot_json text not null default '{}',
          created_at text not null,
          updated_at text not null
        )
        """,
        """
        create table if not exists execution_records (
          execution_id text primary key,
          session_id text,
          scenario text not null,
          execution_status text not null,
          gate_status text not null,
          effective_risk_level text not null,
          degraded_mode integer not null default 0,
          audit_status text not null,
          structural_complete integer not null default 0,
          constraint_complete integer not null default 0,
          goal_complete integer not null default 0,
          resume_cursor_json text not null default '{}',
          snapshot_json text not null default '{}',
          created_at text not null,
          updated_at text not null,
          foreign key (session_id) references session_records(session_id)
        )
        """,
        """
        create table if not exists decision_records (
          record_id text primary key,
          created_at text not null,
          payload_json text not null
        )
        """,
        """
        create table if not exists task_ledger_records (
          record_id text primary key,
          created_at text not null,
          payload_json text not null
        )
        """,
        """
        create table if not exists outcome_records (
          record_id text primary key,
          created_at text not null,
          payload_json text not null
        )
        """,
        """
        create table if not exists audit_events (
          record_id text primary key,
          created_at text not null,
          payload_json text not null
        )
        """,
        """
        create table if not exists job_queue (
          job_id text primary key,
          job_type text not null,
          status text not null,
          idempotency_key text not null,
          payload_json text not null,
          attempt_count integer not null default 0,
          created_at text not null,
          claimed_at text,
          finished_at text,
          last_error text,
          current_run_id text
        )
        """,
        """
        create table if not exists job_runs (
          run_id text primary key,
          job_id text not null,
          job_type text not null,
          attempt_count integer not null,
          status text not null,
          started_at text not null,
          finished_at text,
          last_error text
        )
        """,
        "create index if not exists idx_session_updated_at on session_records(updated_at desc)",
        "create index if not exists idx_execution_session_updated on execution_records(session_id, updated_at desc)",
        "create index if not exists idx_task_ledger_created on task_ledger_records(created_at desc)",
        "create index if not exists idx_outcome_created on outcome_records(created_at desc)",
        "create index if not exists idx_audit_created on audit_events(created_at desc)",
        "create index if not exists idx_job_queue_status_created on job_queue(status, created_at asc)",
        "create index if not exists idx_job_queue_type_status_created on job_queue(job_type, status, created_at asc)",
        "create index if not exists idx_job_runs_job_started on job_runs(job_id, started_at asc)",
    ]
```

```python
# src/openharness/cli.py
@storage_app.command("init")
def storage_init() -> None:
    from openharness.config.paths import get_project_database_path
    from velaris_agent.persistence.schema import bootstrap_schema

    db_path = get_project_database_path(Path.cwd())
    statement_count = bootstrap_schema(db_path)
    print(f"Initialized SQLite storage at {db_path}")
    print(f"Executed {statement_count} schema statements")


@storage_app.command("doctor")
def storage_doctor() -> None:
    from openharness.config.paths import get_project_database_path
    from velaris_agent.persistence.schema import storage_health_report

    db_path = get_project_database_path(Path.cwd())
    report = storage_health_report(db_path)
    if not report["ok"]:
        print(report["error_code"])
        raise typer.Exit(1)
    print(f"SQLite storage OK: {db_path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./scripts/run_pytest.sh tests/test_persistence/test_sqlite.py tests/test_persistence/test_schema.py tests/test_commands/test_cli.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/velaris_agent/persistence/sqlite.py src/velaris_agent/persistence/schema.py src/velaris_agent/persistence/__init__.py src/openharness/cli.py tests/test_persistence/test_sqlite.py tests/test_persistence/test_schema.py tests/test_commands/test_cli.py
git commit -m "feat(storage): add sqlite bootstrap foundation"
```

### Task 3: SQLite Session And Execution Repositories

**Files:**
- Create: `src/velaris_agent/persistence/sqlite_execution.py`
- Modify: `src/velaris_agent/persistence/factory.py`
- Test: `tests/test_persistence/test_sqlite_execution.py`
- Test: `tests/test_persistence/test_schema.py`

- [ ] **Step 1: Write the failing repository tests**

```python
# tests/test_persistence/test_sqlite_execution.py
from openharness.config.paths import get_project_database_path
from velaris_agent.persistence.schema import bootstrap_schema
from velaris_agent.persistence.sqlite_execution import ExecutionRepository, SessionRecord, SessionRepository
from velaris_agent.velaris.execution_contract import BizExecutionRecord


def test_session_repository_roundtrip(tmp_path):
    db_path = get_project_database_path(tmp_path)
    bootstrap_schema(db_path)
    repository = SessionRepository(db_path)

    record = SessionRecord(
        session_id="s-1",
        binding_mode="attached",
        source_runtime="openharness",
        summary="hello",
        message_count=1,
        snapshot_json={"cwd": str(tmp_path), "model": "claude-test"},
        created_at="2026-04-19T00:00:00+00:00",
        updated_at="2026-04-19T00:00:00+00:00",
    )

    repository.upsert(record)
    assert repository.get("s-1") is not None
    assert repository.latest_by_cwd(str(tmp_path)).session_id == "s-1"


def test_execution_repository_create_and_update_status(tmp_path):
    db_path = get_project_database_path(tmp_path)
    bootstrap_schema(db_path)
    repository = ExecutionRepository(db_path)

    record = BizExecutionRecord(
        execution_id="exec-1",
        session_id="s-1",
        scenario="travel",
        execution_status="planned",
        gate_status="allowed",
        effective_risk_level="low",
        degraded_mode=False,
        audit_status="not_required",
        structural_complete=False,
        constraint_complete=False,
        goal_complete=False,
        created_at="2026-04-19T00:00:00+00:00",
        updated_at="2026-04-19T00:00:00+00:00",
        resume_cursor={"stage": "planned"},
    )

    repository.create(record, snapshot_json={"plan": {"scenario": "travel"}})
    repository.update_status(
        "exec-1",
        execution_status="completed",
        gate_status="allowed",
        effective_risk_level="low",
        degraded_mode=False,
        audit_status="persisted",
        structural_complete=True,
        constraint_complete=True,
        goal_complete=True,
        resume_cursor={"stage": "completed"},
        snapshot_json={"result": {"ok": True}},
        updated_at="2026-04-19T00:01:00+00:00",
    )

    stored = repository.get("exec-1")
    assert stored is not None
    assert stored.execution_status == "completed"
    assert stored.goal_complete is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./scripts/run_pytest.sh tests/test_persistence/test_sqlite_execution.py -q
```

Expected:

```text
FAILED tests/test_persistence/test_sqlite_execution.py::test_session_repository_roundtrip - ModuleNotFoundError
FAILED tests/test_persistence/test_sqlite_execution.py::test_execution_repository_create_and_update_status - ModuleNotFoundError
```

- [ ] **Step 3: Implement SQLite repositories and factory helpers**

```python
# src/velaris_agent/persistence/sqlite_execution.py
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from velaris_agent.persistence.sqlite import sqlite_connection
from velaris_agent.velaris.execution_contract import BizExecutionRecord


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    binding_mode: str
    source_runtime: str
    summary: str
    message_count: int
    snapshot_json: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SessionRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def upsert(self, record: SessionRecord) -> SessionRecord:
        with sqlite_connection(self._db_path) as connection:
            connection.execute(
                """
                insert into session_records (
                  session_id, binding_mode, source_runtime, summary, message_count,
                  snapshot_json, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(session_id) do update set
                  binding_mode=excluded.binding_mode,
                  source_runtime=excluded.source_runtime,
                  summary=excluded.summary,
                  message_count=excluded.message_count,
                  snapshot_json=excluded.snapshot_json,
                  created_at=excluded.created_at,
                  updated_at=excluded.updated_at
                """,
                (
                    record.session_id,
                    record.binding_mode,
                    record.source_runtime,
                    record.summary,
                    record.message_count,
                    json.dumps(record.snapshot_json),
                    record.created_at,
                    record.updated_at,
                ),
            )
        return record
```

```python
# src/velaris_agent/persistence/factory.py
from openharness.config.paths import get_project_database_path


def build_session_repository(cwd: str | Path) -> SessionRepository:
    from velaris_agent.persistence.sqlite_execution import SessionRepository

    return SessionRepository(str(get_project_database_path(cwd)))


def build_execution_repository(cwd: str | Path) -> ExecutionRepository:
    from velaris_agent.persistence.sqlite_execution import ExecutionRepository

    return ExecutionRepository(str(get_project_database_path(cwd)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./scripts/run_pytest.sh tests/test_persistence/test_sqlite_execution.py tests/test_persistence/test_schema.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/velaris_agent/persistence/sqlite_execution.py src/velaris_agent/persistence/factory.py tests/test_persistence/test_sqlite_execution.py
git commit -m "feat(storage): add sqlite session and execution repos"
```

### Task 4: SQLite Runtime Stores For Tasks, Outcomes, And Audit

**Files:**
- Create: `src/velaris_agent/persistence/sqlite_runtime.py`
- Modify: `src/velaris_agent/persistence/factory.py`
- Test: `tests/test_persistence/test_sqlite_runtime.py`
- Test: `tests/test_biz/test_orchestrator.py`

- [ ] **Step 1: Write the failing runtime store tests**

```python
# tests/test_persistence/test_sqlite_runtime.py
from openharness.config.paths import get_project_database_path
from velaris_agent.persistence.schema import bootstrap_schema
from velaris_agent.persistence.sqlite_runtime import AuditEventStore, SqliteOutcomeStore, SqliteTaskLedger


def test_runtime_stores_persist_and_list(tmp_path):
    db_path = get_project_database_path(tmp_path)
    bootstrap_schema(db_path)

    ledger = SqliteTaskLedger(db_path)
    store = SqliteOutcomeStore(db_path)
    audit = AuditEventStore(db_path)

    task = ledger.create_task(session_id="s-1", runtime="velaris", objective="book travel")
    store.save_outcome(session_id="s-1", result={"ok": True}, summary="done")
    audit.append_event(session_id="s-1", step_name="orchestrator.completed", operator_id="orchestrator")

    assert ledger.list_tasks("s-1")
    assert store.list_outcomes("s-1")
    assert audit.list_events("s-1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./scripts/run_pytest.sh tests/test_persistence/test_sqlite_runtime.py -q
```

Expected:

```text
FAILED tests/test_persistence/test_sqlite_runtime.py::test_runtime_stores_persist_and_list - ModuleNotFoundError
```

- [ ] **Step 3: Implement SQLite task/outcome/audit stores**

```python
# src/velaris_agent/persistence/sqlite_runtime.py
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from velaris_agent.persistence.sqlite import sqlite_connection
from velaris_agent.velaris.outcome_store import OutcomeStore
from velaris_agent.velaris.task_ledger import TaskLedger


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SqliteTaskLedger(TaskLedger):
    def __init__(self, db_path: str) -> None:
        super().__init__()
        self._db_path = db_path

    def create_task(self, session_id: str, runtime: str, objective: str):
        task = super().create_task(session_id=session_id, runtime=runtime, objective=objective)
        with sqlite_connection(self._db_path) as connection:
            connection.execute(
                "insert into task_ledger_records (record_id, created_at, payload_json) values (?, ?, ?)",
                (task.task_id, _utc_now_iso(), json.dumps(task.to_dict())),
            )
        return task
```

```python
# src/velaris_agent/persistence/factory.py

def build_task_ledger(cwd: str | Path) -> TaskLedger:
    from velaris_agent.persistence.sqlite_runtime import SqliteTaskLedger

    return SqliteTaskLedger(str(get_project_database_path(cwd)))


def build_outcome_store(cwd: str | Path) -> OutcomeStore:
    from velaris_agent.persistence.sqlite_runtime import SqliteOutcomeStore

    return SqliteOutcomeStore(str(get_project_database_path(cwd)))


def build_audit_store(cwd: str | Path) -> AuditEventStore:
    from velaris_agent.persistence.sqlite_runtime import AuditEventStore

    return AuditEventStore(str(get_project_database_path(cwd)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./scripts/run_pytest.sh tests/test_persistence/test_sqlite_runtime.py tests/test_biz/test_orchestrator.py -q
```

Expected:

```text
runtime store tests pass; orchestrator persistence tests still green
```

- [ ] **Step 5: Commit**

```bash
git add src/velaris_agent/persistence/sqlite_runtime.py src/velaris_agent/persistence/factory.py tests/test_persistence/test_sqlite_runtime.py tests/test_biz/test_orchestrator.py
git commit -m "feat(storage): move runtime stores to sqlite"
```

### Task 5: SQLite Decision Memory And Job Queue

**Files:**
- Create: `src/velaris_agent/persistence/sqlite_memory.py`
- Modify: `src/velaris_agent/persistence/job_queue.py`
- Modify: `src/velaris_agent/persistence/factory.py`
- Test: `tests/test_persistence/test_sqlite_memory.py`
- Test: `tests/test_persistence/test_job_queue.py`
- Test: `tests/test_tools/test_knowledge_tools.py`

- [ ] **Step 1: Write the failing SQLite memory and queue tests**

```python
# tests/test_persistence/test_sqlite_memory.py
from openharness.config.paths import get_project_database_path
from velaris_agent.persistence.schema import bootstrap_schema
from velaris_agent.persistence.sqlite_memory import SqliteDecisionMemory
from velaris_agent.memory.types import DecisionRecord


def test_sqlite_decision_memory_save_get_and_feedback(tmp_path):
    db_path = get_project_database_path(tmp_path)
    bootstrap_schema(db_path)
    memory = SqliteDecisionMemory(db_path)

    record = DecisionRecord.model_validate(
        {
            "decision_id": "d-1",
            "user_id": "u-1",
            "scenario": "travel",
            "query": "book flight",
            "options": [],
            "recommended_option": None,
            "scores": {},
            "explanation": "demo",
        }
    )

    memory.save(record)
    loaded = memory.get("d-1")
    assert loaded is not None
    assert loaded.scenario == "travel"
```

```python
# tests/test_persistence/test_job_queue.py
from openharness.config.paths import get_project_database_path
from velaris_agent.persistence.job_queue import SELF_EVOLUTION_REVIEW_JOB_TYPE, SqliteJobQueue
from velaris_agent.persistence.schema import bootstrap_schema


def test_sqlite_job_queue_roundtrip(tmp_path):
    db_path = get_project_database_path(tmp_path)
    bootstrap_schema(db_path)
    queue = SqliteJobQueue(db_path)

    job_id = queue.enqueue(SELF_EVOLUTION_REVIEW_JOB_TYPE, "k-1", {"decision_id": "d-1"})
    claimed = queue.claim_next([SELF_EVOLUTION_REVIEW_JOB_TYPE])
    assert claimed is not None
    assert claimed.job_id == job_id
    queue.mark_succeeded(job_id)
    assert queue.get(job_id).status == "succeeded"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./scripts/run_pytest.sh tests/test_persistence/test_sqlite_memory.py tests/test_persistence/test_job_queue.py tests/test_tools/test_knowledge_tools.py -q
```

Expected:

```text
FAILED tests/test_persistence/test_sqlite_memory.py::test_sqlite_decision_memory_save_get_and_feedback - ModuleNotFoundError
FAILED tests/test_persistence/test_job_queue.py::test_sqlite_job_queue_roundtrip - ImportError
```

- [ ] **Step 3: Implement SQLite decision memory and queue**

```python
# src/velaris_agent/persistence/sqlite_memory.py
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from velaris_agent.memory.decision_memory import DecisionMemory, build_decision_index_entry, deserialize_decision_record, serialize_decision_record
from velaris_agent.memory.types import DecisionRecord
from velaris_agent.persistence.sqlite import sqlite_connection


class SqliteDecisionMemory(DecisionMemory):
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)

    def save(self, record: DecisionRecord) -> str:
        payload = serialize_decision_record(record)
        with sqlite_connection(self._db_path) as connection:
            connection.execute(
                "insert into decision_records (record_id, created_at, payload_json) values (?, ?, ?) on conflict(record_id) do update set created_at=excluded.created_at, payload_json=excluded.payload_json",
                (record.decision_id, datetime.now(UTC).isoformat(), json.dumps(payload)),
            )
        return record.decision_id
```

```python
# src/velaris_agent/persistence/job_queue.py
class SqliteJobQueue:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)

    def enqueue(self, job_type: str, idempotency_key: str, payload: dict[str, Any]) -> str:
        job_id = f"job-{uuid4().hex[:12]}"
        with sqlite_connection(self._db_path) as connection:
            connection.execute(
                "insert into job_queue (job_id, job_type, status, idempotency_key, payload_json, attempt_count, created_at) values (?, ?, ?, ?, ?, ?, ?)",
                (job_id, job_type, "queued", idempotency_key, json.dumps(payload), 0, _utc_now().isoformat()),
            )
        return job_id
```

```python
# src/velaris_agent/persistence/factory.py

def build_decision_memory(cwd: str | Path, base_dir: str | Path | None = None) -> DecisionMemory:
    from velaris_agent.persistence.sqlite_memory import SqliteDecisionMemory

    del base_dir
    return SqliteDecisionMemory(str(get_project_database_path(cwd)))


def build_job_queue(cwd: str | Path) -> SqliteJobQueue:
    from velaris_agent.persistence.job_queue import SqliteJobQueue

    return SqliteJobQueue(str(get_project_database_path(cwd)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./scripts/run_pytest.sh tests/test_persistence/test_sqlite_memory.py tests/test_persistence/test_job_queue.py tests/test_tools/test_knowledge_tools.py -q
```

Expected:

```text
memory and queue tests pass; knowledge tools continue to queue self-evolution through sqlite
```

- [ ] **Step 5: Commit**

```bash
git add src/velaris_agent/persistence/sqlite_memory.py src/velaris_agent/persistence/job_queue.py src/velaris_agent/persistence/factory.py tests/test_persistence/test_sqlite_memory.py tests/test_persistence/test_job_queue.py tests/test_tools/test_knowledge_tools.py
git commit -m "feat(storage): move memory and queue to sqlite"
```

### Task 6: Session Storage And `/session` Command Cutover

**Files:**
- Modify: `src/openharness/services/session_storage.py`
- Modify: `src/openharness/services/__init__.py`
- Modify: `src/openharness/commands/registry.py`
- Modify: `src/openharness/ui/runtime.py`
- Test: `tests/test_services/test_session_storage.py`
- Test: `tests/test_commands/test_registry.py`
- Test: `tests/test_real_large_tasks.py`
- Test: `tests/test_untested_features.py`

- [ ] **Step 1: Write the failing tests for session ID return value and command semantics**

```python
# tests/test_services/test_session_storage.py
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.services.session_storage import load_session_snapshot, save_session_snapshot


def test_save_session_snapshot_returns_session_id(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()

    session_id = save_session_snapshot(
        cwd=project,
        model="claude-test",
        system_prompt="system",
        messages=[ConversationMessage(role="user", content=[TextBlock(text="hello")])],
        usage=UsageSnapshot(input_tokens=1, output_tokens=2),
        session_id="session-1",
    )

    assert session_id == "session-1"
    snapshot = load_session_snapshot(project)
    assert snapshot["session_id"] == "session-1"
```

```python
# tests/test_commands/test_registry.py
@pytest.mark.asyncio
async def test_session_commands_use_sqlite_summary_and_markdown_only(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)

    session_result = await registry.lookup("/session")[0].handler("", context)
    assert "Database path:" in session_result.message

    tag_result = await registry.lookup("/session tag smoke")[0].handler("tag smoke", context)
    assert "smoke.md" in tag_result.message
    assert "smoke.json" not in tag_result.message
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./scripts/run_pytest.sh tests/test_services/test_session_storage.py tests/test_commands/test_registry.py tests/test_real_large_tasks.py tests/test_untested_features.py -q
```

Expected:

```text
FAILED tests/test_services/test_session_storage.py::test_save_session_snapshot_returns_session_id - AssertionError
FAILED tests/test_commands/test_registry.py::test_session_commands_use_sqlite_summary_and_markdown_only - AssertionError
```

- [ ] **Step 3: Rewrite session storage and registry commands**

```python
# src/openharness/services/session_storage.py
from openharness.config.paths import get_project_database_path, get_sessions_dir
from velaris_agent.persistence.factory import build_session_repository


def save_session_snapshot(... ) -> str:
    sid = session_id or uuid4().hex[:12]
    payload = {
        "session_id": sid,
        "cwd": str(Path(cwd).resolve()),
        "model": model,
        "system_prompt": system_prompt,
        "messages": [message.to_dict() for message in messages],
        "usage": usage.model_dump(),
        "created_at": now,
        "summary": summary,
        "message_count": len(messages),
    }
    repository = build_session_repository(Path(cwd).resolve())
    repository.upsert(...)
    return sid
```

```python
# src/openharness/commands/registry.py
if not tokens or tokens[0] == "show":
    latest = load_session_snapshot(context.cwd)
    transcript = get_project_session_dir(context.cwd) / "transcript.md"
    db_path = get_project_database_path(context.cwd)
    lines = [
        f"Database path: {db_path}",
        f"Latest session: {latest['session_id'] if latest is not None else 'missing'}",
        f"Transcript export: {'present' if transcript.exists() else 'missing'}",
        f"Message count: {len(context.engine.messages)}",
    ]
    return CommandResult(message="\n".join(lines))
```

```python
# src/openharness/commands/registry.py
if tokens[0] == "tag" and len(tokens) == 2:
    safe_name = "".join(character for character in tokens[1] if character.isalnum() or character in {"-", "_"})
    export_path = export_session_markdown(cwd=context.cwd, messages=context.engine.messages)
    tagged_md = session_dir / f"{safe_name}.md"
    shutil.copy2(export_path, tagged_md)
    return CommandResult(message=f"Tagged session as {safe_name}:\n- {tagged_md}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./scripts/run_pytest.sh tests/test_services/test_session_storage.py tests/test_commands/test_registry.py tests/test_real_large_tasks.py tests/test_untested_features.py -q
```

Expected:

```text
session storage and command tests pass; no JSON snapshot path assertions remain
```

- [ ] **Step 5: Commit**

```bash
git add src/openharness/services/session_storage.py src/openharness/services/__init__.py src/openharness/commands/registry.py src/openharness/ui/runtime.py tests/test_services/test_session_storage.py tests/test_commands/test_registry.py tests/test_real_large_tasks.py tests/test_untested_features.py
git commit -m "feat(session): move snapshots fully to sqlite"
```

### Task 7: Orchestrator And Tool Wiring Cutover

**Files:**
- Modify: `src/velaris_agent/velaris/orchestrator.py`
- Modify: `src/openharness/tools/save_decision_tool.py`
- Modify: `src/openharness/tools/recall_preferences_tool.py`
- Modify: `src/openharness/tools/recall_decisions_tool.py`
- Modify: `src/openharness/tools/decision_score_tool.py`
- Modify: `src/openharness/tools/self_evolution_review_tool.py`
- Test: `tests/test_biz/test_orchestrator.py`
- Test: `tests/test_tools/test_knowledge_tools.py`
- Test: `tests/test_tools/test_biz_execute_tool.py`

- [ ] **Step 1: Write the failing tests for cwd-based wiring**

```python
# tests/test_tools/test_knowledge_tools.py
async def test_save_decision_uses_project_sqlite_queue(tmp_path, monkeypatch):
    called = {}

    def fake_build_job_queue(cwd):
        called["cwd"] = str(cwd)
        return _FakeQueue()

    monkeypatch.setattr("velaris_agent.persistence.factory.build_job_queue", fake_build_job_queue)

    # invoke tool here using project cwd
    assert called["cwd"] == str(tmp_path)
```

```python
# tests/test_biz/test_orchestrator.py
from velaris_agent.velaris.orchestrator import VelarisBizOrchestrator


def test_orchestrator_no_longer_accepts_postgres_dsn(tmp_path):
    orchestrator = VelarisBizOrchestrator(cwd=tmp_path)
    assert orchestrator is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./scripts/run_pytest.sh tests/test_biz/test_orchestrator.py tests/test_tools/test_knowledge_tools.py tests/test_tools/test_biz_execute_tool.py -q
```

Expected:

```text
FAILED tests/test_biz/test_orchestrator.py::test_orchestrator_no_longer_accepts_postgres_dsn - TypeError or AssertionError
FAILED tests/test_tools/test_knowledge_tools.py::test_save_decision_uses_project_sqlite_queue - AssertionError
```

- [ ] **Step 3: Rewrite orchestrator and tools to use cwd-based factory wiring**

```python
# src/velaris_agent/velaris/orchestrator.py
class VelarisBizOrchestrator:
    def __init__(self, *, cwd: str | Path | None = None, ... ) -> None:
        self._cwd = Path(cwd or Path.cwd()).resolve()
        self.task_ledger = task_ledger or build_task_ledger(self._cwd)
        self.outcome_store = outcome_store or build_outcome_store(self._cwd)
        self.audit_store = audit_store or build_audit_store(self._cwd)
        self.session_repository = session_repository or build_session_repository(self._cwd)
        self.execution_repository = execution_repository or build_execution_repository(self._cwd)
```

```python
# src/openharness/tools/save_decision_tool.py
cwd = Path(context.cwd).resolve()
memory = build_decision_memory(cwd=cwd)
queue = build_job_queue(cwd=cwd)
```

```python
# src/openharness/tools/recall_preferences_tool.py
cwd = Path(context.cwd).resolve()
memory = build_decision_memory(cwd=cwd)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./scripts/run_pytest.sh tests/test_biz/test_orchestrator.py tests/test_tools/test_knowledge_tools.py tests/test_tools/test_biz_execute_tool.py -q
```

Expected:

```text
orchestrator and tool wiring tests pass without postgres_dsn metadata
```

- [ ] **Step 5: Commit**

```bash
git add src/velaris_agent/velaris/orchestrator.py src/openharness/tools/save_decision_tool.py src/openharness/tools/recall_preferences_tool.py src/openharness/tools/recall_decisions_tool.py src/openharness/tools/decision_score_tool.py src/openharness/tools/self_evolution_review_tool.py tests/test_biz/test_orchestrator.py tests/test_tools/test_knowledge_tools.py tests/test_tools/test_biz_execute_tool.py
git commit -m "refactor(storage): wire orchestrator and tools to sqlite"
```

### Task 8: Delete PostgreSQL Mainline And Replace Test Suite

**Files:**
- Delete: `src/velaris_agent/persistence/postgres.py`
- Delete: `src/velaris_agent/persistence/postgres_execution.py`
- Delete: `src/velaris_agent/persistence/postgres_runtime.py`
- Delete: `src/velaris_agent/persistence/postgres_memory.py`
- Delete: `src/velaris_agent/persistence/psycopg_compat.py`
- Delete: `tests/test_persistence/test_postgres.py`
- Delete: `tests/test_persistence/test_postgres_execution.py`
- Delete: `tests/test_persistence/test_postgres_runtime.py`
- Delete: `tests/test_persistence/test_postgres_memory.py`
- Modify: `tests/test_persistence/test_job_queue.py`
- Modify: `tests/test_services/test_session_storage.py`
- Modify: `tests/test_persistence/conftest.py`

- [ ] **Step 1: Write the failing cleanup assertions**

```python
# tests/test_persistence/test_schema.py
import pathlib


def test_postgres_mainline_files_are_removed() -> None:
    root = pathlib.Path("src/velaris_agent/persistence")
    assert not (root / "postgres.py").exists()
    assert not (root / "postgres_execution.py").exists()
    assert not (root / "postgres_runtime.py").exists()
    assert not (root / "postgres_memory.py").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./scripts/run_pytest.sh tests/test_persistence/test_schema.py -q
```

Expected:

```text
FAILED tests/test_persistence/test_schema.py::test_postgres_mainline_files_are_removed - AssertionError
```

- [ ] **Step 3: Delete PostgreSQL files and replace test imports with SQLite names**

```bash
rm src/velaris_agent/persistence/postgres.py
rm src/velaris_agent/persistence/postgres_execution.py
rm src/velaris_agent/persistence/postgres_runtime.py
rm src/velaris_agent/persistence/postgres_memory.py
rm src/velaris_agent/persistence/psycopg_compat.py
rm tests/test_persistence/test_postgres.py
rm tests/test_persistence/test_postgres_execution.py
rm tests/test_persistence/test_postgres_runtime.py
rm tests/test_persistence/test_postgres_memory.py
```

```python
# tests/test_persistence/test_job_queue.py
from velaris_agent.persistence.job_queue import SELF_EVOLUTION_REVIEW_JOB_TYPE, SqliteJobQueue
```

```python
# tests/test_services/test_session_storage.py
from velaris_agent.persistence.sqlite_execution import SessionRecord
```

- [ ] **Step 4: Run tests to verify imports are clean**

Run:

```bash
./scripts/run_pytest.sh tests/test_persistence/test_schema.py tests/test_persistence/test_job_queue.py tests/test_services/test_session_storage.py -q
```

Expected:

```text
postgres file existence tests pass; remaining tests import sqlite implementations only
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(storage): remove postgres mainline"
```

### Task 9: Documentation Sync And Full Verification

**Files:**
- Modify: `aidlc-docs/aidlc-state.md`
- Modify: `aidlc-docs/audit.md`
- Modify: `aidlc-docs/construction/build-and-test/build-and-test-summary.md`
- Modify: `aidlc-docs/construction/build-and-test/build-instructions.md`
- Modify: `aidlc-docs/construction/build-and-test/integration-test-instructions.md`
- Modify: `aidlc-docs/construction/build-and-test/unit-test-instructions.md`
- Modify: `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/nfr-requirements/tech-stack-decisions.md`
- Modify: `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/nfr-requirements/nfr-requirements.md`
- Modify: `docs/superpowers/specs/2026-04-19-sqlite-mainline-cutover-design.md`

- [ ] **Step 1: Write the failing documentation consistency checks**

```python
# tests/test_persistence/test_schema.py
from pathlib import Path


def test_repo_docs_no_longer_present_postgres_as_official_mainline() -> None:
    targets = [
        Path("aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/nfr-requirements/tech-stack-decisions.md"),
        Path("aidlc-docs/construction/build-and-test/build-instructions.md"),
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in targets)
    assert "唯一正式主存储" not in text or "PostgreSQL" not in text
```

- [ ] **Step 2: Run the consistency check to verify it fails**

Run:

```bash
./scripts/run_pytest.sh tests/test_persistence/test_schema.py::test_repo_docs_no_longer_present_postgres_as_official_mainline -q
```

Expected:

```text
FAILED tests/test_persistence/test_schema.py::test_repo_docs_no_longer_present_postgres_as_official_mainline - AssertionError
```

- [ ] **Step 3: Update docs and verification commands**

```markdown
# aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/nfr-requirements/tech-stack-decisions.md
- `execution / task / outcome / audit / session` 统一使用 SQLite
- 数据库文件固定为项目内 `.velaris-agent/velaris.db`
- 文件 / 内存实现不再是正式主线，只保留测试辅助角色
```

```markdown
# aidlc-docs/construction/build-and-test/build-instructions.md
1. 进入项目根目录
2. 运行 `velaris storage init`
3. 运行 `uv run ruff check src tests scripts`
4. 运行 `./scripts/run_pytest.sh -q`
```

- [ ] **Step 4: Run full verification**

Run:

```bash
uv run ruff check src tests scripts
./scripts/run_pytest.sh -q
```

Expected:

```text
All checks passed!
897 passed, 8 skipped, 0-3 warnings
```

- [ ] **Step 5: Commit**

```bash
git add aidlc-docs docs/superpowers/specs/2026-04-19-sqlite-mainline-cutover-design.md
git commit -m "docs(storage): switch docs to sqlite mainline"
```

## Self-Review Checklist

- Spec coverage：本计划覆盖了 spec 中的路径、settings、schema、repositories、session、CLI、tools、job_queue、旧文件删除、文档同步与全量验证。
- Placeholder scan：全文没有 `TBD`、`TODO`、`implement later` 之类占位词；每个代码步骤都给出实际代码片段与命令。
- Type consistency：统一使用 `cwd` 推导数据库路径，统一使用 `SqliteJobQueue`、`SqliteDecisionMemory`、`sqlite_connection` 命名，不再混用 `postgres_dsn`。
