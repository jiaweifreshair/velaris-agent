# Velaris Phase 1 Persistence Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持 `Velaris Agent` 品牌和现有 OpenHarness 兼容面的前提下，把 `DecisionMemory / TaskLedger / OutcomeStore` 从文件/内存态升级为“单体 + PostgreSQL + 应用内 worker”的最小生产化持久化基座，并补齐审计与系统健康能力。

**Architecture:** 继续保持单进程应用；新增 `psycopg` 直连 PostgreSQL，不引入 SQLAlchemy、Alembic、Redis、Kafka、ClickHouse。在线请求直接写 PostgreSQL，后台任务通过 `job_queue / job_run` 表和应用内 worker 异步处理，证据附件继续写本地目录。所有新持久化能力通过工厂层按配置切换，避免一次性破坏现有文件后端和测试。

**Tech Stack:** Python 3.11, `psycopg` 3, PostgreSQL, Pydantic 2, Typer, pytest

---

## Execution Status

- 更新时间：2026-04-16
- 当前状态：`Task 1` review blocker 已收口，准备进入下一阶段计划拆分
- 已修复问题：
  - `persistence` 包与 schema/bootstrap 改为 lazy import，不再在 import 阶段强绑 `psycopg`
  - 严格审计场景下，审计链路不可用会显式失败，不再静默降级
  - `job_runs` 已接入最小执行历史闭环，队列不再只有当前状态
- 已验证命令：

```bash
./scripts/run_pytest.sh tests/test_persistence/test_schema.py tests/test_persistence/test_postgres.py tests/test_persistence/test_postgres_memory.py tests/test_persistence/test_postgres_runtime.py tests/test_persistence/test_job_queue.py tests/test_biz/test_orchestrator.py -q
./scripts/run_pytest.sh tests/test_tools/test_knowledge_tools.py -q
```

- 已验证结果：
  - 持久化与编排子集：`18 passed, 3 skipped`
  - 知识工具回归：`3 passed`

## File Structure

### New Files

- `src/velaris_agent/persistence/__init__.py`
- `src/velaris_agent/persistence/postgres.py`
- `src/velaris_agent/persistence/schema.py`
- `src/velaris_agent/persistence/factory.py`
- `src/velaris_agent/persistence/postgres_memory.py`
- `src/velaris_agent/persistence/postgres_runtime.py`
- `src/velaris_agent/persistence/job_queue.py`
- `src/velaris_agent/persistence/health.py`
- `tests/test_persistence/conftest.py`
- `tests/test_persistence/test_settings.py`
- `tests/test_persistence/test_schema.py`
- `tests/test_persistence/test_postgres_memory.py`
- `tests/test_persistence/test_postgres_runtime.py`
- `tests/test_persistence/test_job_queue.py`

### Modified Files

- `pyproject.toml`
- `src/openharness/config/settings.py`
- `src/openharness/cli.py`
- `src/openharness/tools/save_decision_tool.py`
- `src/openharness/tools/recall_preferences_tool.py`
- `src/openharness/tools/recall_decisions_tool.py`
- `src/openharness/tools/decision_score_tool.py`
- `src/openharness/tools/self_evolution_review_tool.py`
- `src/velaris_agent/memory/decision_memory.py`
- `src/velaris_agent/velaris/task_ledger.py`
- `src/velaris_agent/velaris/outcome_store.py`
- `src/velaris_agent/velaris/orchestrator.py`
- `tests/test_memory/test_decision_memory.py`
- `tests/test_biz/test_orchestrator.py`
- `tests/test_commands/test_cli.py`
- `README.md`
- `docs/ARCHITECTURE.md`

### Design Notes

- 保留当前 `DecisionMemory` 文件后端，作为默认兼容实现。
- PostgreSQL 后端只在 `VELARIS_POSTGRES_DSN` 或 `settings.storage.postgres_dsn` 配置存在时启用。
- 先做手写 SQL + 极薄 repository，不引入 ORM。
- 所有数据库表都必须包含 `created_at` / `updated_at` / 幂等键或唯一键策略。

---

### Task 1: Storage Config And Schema Bootstrap

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/openharness/config/settings.py`
- Modify: `src/openharness/cli.py`
- Create: `src/velaris_agent/persistence/__init__.py`
- Create: `src/velaris_agent/persistence/postgres.py`
- Create: `src/velaris_agent/persistence/schema.py`
- Test: `tests/test_persistence/test_settings.py`
- Test: `tests/test_persistence/test_schema.py`
- Test: `tests/test_commands/test_cli.py`

- [ ] **Step 1: Write the failing settings and schema bootstrap tests**

```python
# tests/test_persistence/test_settings.py
from openharness.config.settings import Settings


def test_settings_support_postgres_storage_env(monkeypatch):
    monkeypatch.setenv("VELARIS_POSTGRES_DSN", "postgresql://velaris:secret@localhost:5432/velaris")
    monkeypatch.setenv("VELARIS_EVIDENCE_DIR", "/tmp/velaris-evidence")

    settings = Settings()
    updated = settings.__class__.model_validate(settings.model_dump())

    # 先故意断言未来字段，当前实现应失败
    assert updated.storage.postgres_dsn.endswith("/velaris")
    assert updated.storage.evidence_dir == "/tmp/velaris-evidence"


def test_storage_defaults_stay_single_process():
    settings = Settings()
    assert settings.storage.job_poll_interval_seconds == 2.0
    assert settings.storage.job_max_attempts == 3
```

```python
# tests/test_persistence/test_schema.py
from velaris_agent.persistence.schema import EXPECTED_TABLES, build_bootstrap_statements


def test_bootstrap_schema_contains_required_tables():
    sql = "\n".join(build_bootstrap_statements())
    for table in EXPECTED_TABLES:
        assert f"create table if not exists {table}" in sql.lower()
```

```python
# tests/test_commands/test_cli.py
def test_cli_storage_init_invokes_bootstrap(monkeypatch, runner):
    from openharness.cli import app

    called = {"value": False}

    def _fake_bootstrap(dsn: str) -> int:
        called["value"] = True
        assert dsn.endswith("/velaris")
        return 8

    monkeypatch.setenv("VELARIS_POSTGRES_DSN", "postgresql://velaris:secret@localhost:5432/velaris")
    monkeypatch.setattr("velaris_agent.persistence.schema.bootstrap_schema", _fake_bootstrap)

    result = runner.invoke(app, ["storage", "init"])
    assert result.exit_code == 0
    assert "initialized" in result.output.lower()
    assert called["value"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_persistence/test_settings.py tests/test_persistence/test_schema.py tests/test_commands/test_cli.py -q
```

Expected:

```text
FAILED tests/test_persistence/test_settings.py::test_settings_support_postgres_storage_env - AttributeError: 'Settings' object has no attribute 'storage'
FAILED tests/test_persistence/test_schema.py::test_bootstrap_schema_contains_required_tables - ModuleNotFoundError: No module named 'velaris_agent.persistence'
FAILED tests/test_commands/test_cli.py::test_cli_storage_init_invokes_bootstrap - No such command 'storage'
```

- [ ] **Step 3: Implement storage settings, bootstrap SQL, and the CLI command**

```toml
# pyproject.toml
dependencies = [
    "anthropic>=0.40.0",
    "openai>=1.54.0",
    "rich>=13.0.0",
    "prompt-toolkit>=3.0.0",
    "textual>=0.80.0",
    "typer>=0.12.0",
    "pydantic>=2.0.0",
    "httpx>=0.27.0",
    "websockets>=12.0",
    "mcp>=1.0.0",
    "pyperclip>=1.9.0",
    "pyyaml>=6.0",
    "watchfiles>=0.20.0",
    "psycopg[binary]>=3.2.1",
]
```

```diff
# src/openharness/config/settings.py
+class StorageSettings(BaseModel):
+    """Velaris 持久化配置。"""
+
+    postgres_dsn: str = ""
+    evidence_dir: str | None = None
+    job_poll_interval_seconds: float = 2.0
+    job_max_attempts: int = 3
+
 class Settings(BaseModel):
+    storage: StorageSettings = Field(default_factory=StorageSettings)
```

```python
# src/openharness/config/settings.py::_apply_env_overrides
storage_updates: dict[str, Any] = {}
postgres_dsn = os.environ.get("VELARIS_POSTGRES_DSN")
if postgres_dsn:
    storage_updates["postgres_dsn"] = postgres_dsn

evidence_dir = os.environ.get("VELARIS_EVIDENCE_DIR")
if evidence_dir:
    storage_updates["evidence_dir"] = evidence_dir

if storage_updates:
    updates["storage"] = settings.storage.model_copy(update=storage_updates)
```

```python
# src/velaris_agent/persistence/schema.py
EXPECTED_TABLES = [
    "decision_records",
    "task_ledger_records",
    "outcome_records",
    "audit_events",
    "job_queue",
    "job_runs",
]


def build_bootstrap_statements() -> list[str]:
    return [
        """
        create table if not exists decision_records (
            decision_id text primary key,
            user_id text not null,
            scenario text not null,
            record_json jsonb not null,
            created_at timestamptz not null,
            updated_at timestamptz not null
        )
        """,
        """
        create table if not exists task_ledger_records (
            task_id text primary key,
            session_id text not null,
            record_json jsonb not null,
            created_at timestamptz not null,
            updated_at timestamptz not null
        )
        """,
        """
        create table if not exists outcome_records (
            session_id text not null,
            created_at timestamptz not null,
            record_json jsonb not null
        )
        """,
        """
        create table if not exists audit_events (
            event_id text primary key,
            session_id text not null,
            step_name text not null,
            operator_id text not null,
            payload_json jsonb not null,
            created_at timestamptz not null
        )
        """,
        """
        create table if not exists job_queue (
            job_id text primary key,
            job_type text not null,
            idempotency_key text not null unique,
            payload_json jsonb not null,
            status text not null,
            available_at timestamptz not null,
            created_at timestamptz not null,
            updated_at timestamptz not null
        )
        """,
        """
        create table if not exists job_runs (
            run_id text primary key,
            job_id text not null,
            status text not null,
            error_text text,
            started_at timestamptz not null,
            finished_at timestamptz
        )
        """,
    ]
```

```python
# src/velaris_agent/persistence/postgres.py
from contextlib import contextmanager
import psycopg


@contextmanager
def postgres_connection(dsn: str):
    conn = psycopg.connect(dsn, autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

```python
# src/openharness/cli.py
storage_app = typer.Typer(help="Velaris storage maintenance commands.")
app.add_typer(storage_app, name="storage")


@storage_app.command("init")
def storage_init_cmd() -> None:
    from openharness.config import load_settings
    from velaris_agent.persistence.schema import bootstrap_schema

    settings = load_settings()
    dsn = settings.storage.postgres_dsn
    if not dsn:
        raise typer.BadParameter("VELARIS_POSTGRES_DSN 未配置")
    count = bootstrap_schema(dsn)
    print(f"Storage initialized: {count} statements applied")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/test_persistence/test_settings.py tests/test_persistence/test_schema.py tests/test_commands/test_cli.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/openharness/config/settings.py src/openharness/cli.py src/velaris_agent/persistence/__init__.py src/velaris_agent/persistence/postgres.py src/velaris_agent/persistence/schema.py tests/test_persistence/test_settings.py tests/test_persistence/test_schema.py tests/test_commands/test_cli.py
git commit -m "feat(storage): add postgres bootstrap foundation"
```

---

### Task 2: Add PostgreSQL Decision Memory Behind A Factory

**Files:**
- Create: `src/velaris_agent/persistence/factory.py`
- Create: `src/velaris_agent/persistence/postgres_memory.py`
- Modify: `src/velaris_agent/memory/decision_memory.py`
- Modify: `src/openharness/tools/save_decision_tool.py`
- Modify: `src/openharness/tools/recall_preferences_tool.py`
- Modify: `src/openharness/tools/recall_decisions_tool.py`
- Modify: `src/openharness/tools/decision_score_tool.py`
- Modify: `src/openharness/tools/self_evolution_review_tool.py`
- Test: `tests/test_persistence/conftest.py`
- Test: `tests/test_persistence/test_postgres_memory.py`
- Test: `tests/test_memory/test_decision_memory.py`

- [ ] **Step 1: Write the failing repository and factory tests**

```python
# tests/test_persistence/conftest.py
import os
import pytest


@pytest.fixture
def postgres_dsn():
    dsn = os.environ.get("VELARIS_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("VELARIS_TEST_POSTGRES_DSN not set")
    return dsn
```

```python
# tests/test_persistence/test_postgres_memory.py
from datetime import datetime, timezone

from velaris_agent.memory.types import DecisionRecord
from velaris_agent.persistence.schema import bootstrap_schema
from velaris_agent.persistence.postgres_memory import PostgresDecisionMemory


def test_postgres_decision_memory_save_get_and_feedback(postgres_dsn):
    bootstrap_schema(postgres_dsn)
    memory = PostgresDecisionMemory(postgres_dsn)
    record = DecisionRecord(
        decision_id="dec-pg-001",
        user_id="u1",
        scenario="travel",
        query="北京到上海",
        recommended={"id": "opt-a"},
        alternatives=[],
        explanation="推荐 A",
        created_at=datetime.now(timezone.utc),
    )

    assert memory.save(record) == "dec-pg-001"
    assert memory.get("dec-pg-001").decision_id == "dec-pg-001"

    updated = memory.update_feedback(
        "dec-pg-001",
        user_choice={"id": "opt-b"},
        user_feedback=4.6,
    )
    assert updated is not None
    assert updated.user_feedback == 4.6
```

```python
# tests/test_memory/test_decision_memory.py
def test_decision_memory_file_backend_still_works(tmp_path):
    mem = DecisionMemory(base_dir=tmp_path / "decisions")
    assert mem.list_by_user("nobody") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_persistence/test_postgres_memory.py tests/test_memory/test_decision_memory.py -q
```

Expected:

```text
FAILED tests/test_persistence/test_postgres_memory.py::test_postgres_decision_memory_save_get_and_feedback - ModuleNotFoundError: No module named 'velaris_agent.persistence.postgres_memory'
```

- [ ] **Step 3: Implement the Postgres repository and tool factory**

```python
# src/velaris_agent/persistence/postgres_memory.py
from datetime import datetime, timezone

from velaris_agent.memory.types import DecisionRecord
from velaris_agent.persistence.postgres import postgres_connection


class PostgresDecisionMemory:
    """与现有 DecisionMemory API 对齐的 PostgreSQL 后端。"""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def save(self, record: DecisionRecord) -> str:
        now = datetime.now(timezone.utc)
        payload = record.model_dump(mode="json")
        with postgres_connection(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into decision_records (
                    decision_id, user_id, scenario, record_json, created_at, updated_at
                ) values (%s, %s, %s, %s::jsonb, %s, %s)
                on conflict (decision_id) do update
                set record_json = excluded.record_json,
                    updated_at = excluded.updated_at
                """,
                (
                    record.decision_id,
                    record.user_id,
                    record.scenario,
                    json.dumps(payload, ensure_ascii=False),
                    record.created_at,
                    now,
                ),
            )
        return record.decision_id
```

```python
# src/velaris_agent/persistence/factory.py
from pathlib import Path

from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.persistence.postgres_memory import PostgresDecisionMemory


def build_decision_memory(*, postgres_dsn: str = "", base_dir: str | Path | None = None):
    if postgres_dsn:
        return PostgresDecisionMemory(postgres_dsn)
    return DecisionMemory(base_dir=base_dir)
```

```python
# src/openharness/tools/save_decision_tool.py
from velaris_agent.persistence.factory import build_decision_memory


base_dir = context.metadata.get("decision_memory_dir")
memory = build_decision_memory(
    postgres_dsn=str(context.metadata.get("postgres_dsn", "")),
    base_dir=base_dir,
)
```

```python
# src/openharness/tools/recall_preferences_tool.py / recall_decisions_tool.py / decision_score_tool.py / self_evolution_review_tool.py
memory = build_decision_memory(
    postgres_dsn=str(context.metadata.get("postgres_dsn", "")),
    base_dir=context.metadata.get("decision_memory_dir"),
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/test_persistence/test_postgres_memory.py tests/test_memory/test_decision_memory.py tests/test_tools/test_decision_tools.py -q
```

Expected:

```text
targeted tests pass; postgres integration tests may be skipped when VELARIS_TEST_POSTGRES_DSN is not configured
```

Notes:

- 当 `VELARIS_TEST_POSTGRES_DSN` 未设置时，PostgreSQL 集成测试允许 `skip`
- 现有文件后端测试必须继续通过，证明兼容没破

- [ ] **Step 5: Commit**

```bash
git add src/velaris_agent/persistence/factory.py src/velaris_agent/persistence/postgres_memory.py src/velaris_agent/memory/decision_memory.py src/openharness/tools/save_decision_tool.py src/openharness/tools/recall_preferences_tool.py src/openharness/tools/recall_decisions_tool.py src/openharness/tools/decision_score_tool.py src/openharness/tools/self_evolution_review_tool.py tests/test_persistence/conftest.py tests/test_persistence/test_postgres_memory.py tests/test_memory/test_decision_memory.py
git commit -m "feat(memory): add postgres-backed decision memory"
```

---

### Task 3: Persist Task Ledger, Outcome Store, And Audit Events

**Files:**
- Create: `src/velaris_agent/persistence/postgres_runtime.py`
- Modify: `src/velaris_agent/velaris/task_ledger.py`
- Modify: `src/velaris_agent/velaris/outcome_store.py`
- Modify: `src/velaris_agent/velaris/orchestrator.py`
- Modify: `src/velaris_agent/persistence/factory.py`
- Test: `tests/test_persistence/test_postgres_runtime.py`
- Test: `tests/test_biz/test_orchestrator.py`

- [ ] **Step 1: Write the failing runtime persistence tests**

```python
# tests/test_persistence/test_postgres_runtime.py
from velaris_agent.persistence.postgres_runtime import (
    AuditEventStore,
    PostgresOutcomeStore,
    PostgresTaskLedger,
)
from velaris_agent.persistence.schema import bootstrap_schema


def test_runtime_repositories_persist_and_list(postgres_dsn):
    bootstrap_schema(postgres_dsn)
    ledger = PostgresTaskLedger(postgres_dsn)
    outcome_store = PostgresOutcomeStore(postgres_dsn)
    audit_store = AuditEventStore(postgres_dsn)

    task = ledger.create_task(
        session_id="session-1",
        runtime="local",
        role="biz_executor",
        objective="采购比价",
    )
    ledger.update_status(task.task_id, "completed")
    outcome_store.record(
        session_id="session-1",
        scenario="procurement",
        selected_strategy="local_closed_loop",
        success=True,
        reason_codes=["R001"],
        summary="推荐完成",
    )
    audit_store.append_event(
        session_id="session-1",
        step_name="orchestrator.completed",
        operator_id="VelarisBizOrchestrator",
        payload={"task_id": task.task_id},
    )

    assert len(ledger.list_by_session("session-1")) == 1
    assert len(outcome_store.list_by_session("session-1")) == 1
    assert len(audit_store.list_by_session("session-1")) == 1
```

```python
# tests/test_biz/test_orchestrator.py
def test_orchestrator_persists_audit_trace(postgres_dsn):
    from openharness.velaris.orchestrator import VelarisBizOrchestrator
    from velaris_agent.persistence.postgres_runtime import (
        AuditEventStore,
        PostgresOutcomeStore,
        PostgresTaskLedger,
    )
    from velaris_agent.persistence.schema import bootstrap_schema

    bootstrap_schema(postgres_dsn)
    audit_store = AuditEventStore(postgres_dsn)
    orchestrator = VelarisBizOrchestrator(
        task_ledger=PostgresTaskLedger(postgres_dsn),
        outcome_store=PostgresOutcomeStore(postgres_dsn),
        audit_store=audit_store,
    )

    result = orchestrator.execute(
        query="我每月 OpenAI 成本 2000 美元，想降到 800",
        constraints={"target_monthly_cost": 800},
        payload={
            "current_monthly_cost": 2000,
            "target_monthly_cost": 800,
            "suggestions": [
                {
                    "id": "switch-tier",
                    "title": "分层路由",
                    "estimated_saving": 900,
                    "quality_retention": 0.88,
                    "execution_speed": 0.9,
                    "effort": "medium",
                }
            ],
        },
        session_id="session-audit",
    )

    assert result["task"]["status"] == "completed"
    assert result["audit_event_count"] >= 2
    assert len(audit_store.list_by_session("session-audit")) >= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_persistence/test_postgres_runtime.py tests/test_biz/test_orchestrator.py -q
```

Expected:

```text
FAILED tests/test_persistence/test_postgres_runtime.py::test_runtime_repositories_persist_and_list - cannot import name 'PostgresTaskLedger'
FAILED tests/test_biz/test_orchestrator.py::test_orchestrator_persists_audit_trace - VelarisBizOrchestrator.__init__() got an unexpected keyword argument 'audit_store'
```

- [ ] **Step 3: Implement runtime repositories and audit writes**

```python
# src/velaris_agent/persistence/postgres_runtime.py
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from velaris_agent.velaris.task_ledger import TaskLedgerRecord
from velaris_agent.velaris.outcome_store import OutcomeRecord
from velaris_agent.persistence.postgres import postgres_connection


class PostgresTaskLedger:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def create_task(self, session_id: str, runtime: str, role: str, objective: str, depends_on: list[str] | None = None) -> TaskLedgerRecord:
        timestamp = datetime.now(UTC).isoformat()
        record = TaskLedgerRecord(
            task_id=f"task-{uuid4().hex[:12]}",
            session_id=session_id,
            runtime=runtime,
            role=role,
            objective=objective,
            status="queued",
            depends_on=depends_on or [],
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._upsert(record)
        return record
```

```python
# src/velaris_agent/persistence/postgres_runtime.py
class AuditEventStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def append_event(self, *, session_id: str, step_name: str, operator_id: str, payload: dict) -> str:
        event_id = f"audit-{uuid4().hex[:12]}"
        with postgres_connection(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into audit_events (
                    event_id, session_id, step_name, operator_id, payload_json, created_at
                ) values (%s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    event_id,
                    session_id,
                    step_name,
                    operator_id,
                    json.dumps(payload, ensure_ascii=False),
                    datetime.now(UTC),
                ),
            )
        return event_id

    def list_by_session(self, session_id: str) -> list[dict]:
        with postgres_connection(self._dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select event_id, step_name, operator_id, payload_json, created_at
                from audit_events
                where session_id = %s
                order by created_at asc
                """,
                (session_id,),
            )
            rows = cur.fetchall()
        return [dict(row) for row in rows]
```

```python
# src/velaris_agent/velaris/orchestrator.py
class VelarisBizOrchestrator:
    def __init__(
        self,
        router: PolicyRouter | None = None,
        authority_service: AuthorityService | None = None,
        task_ledger: TaskLedger | None = None,
        outcome_store: OutcomeStore | None = None,
        audit_store: AuditEventStore | None = None,
    ) -> None:
        self.router = router or PolicyRouter()
        self.authority_service = authority_service or AuthorityService()
        self.task_ledger = task_ledger or TaskLedger()
        self.outcome_store = outcome_store or OutcomeStore()
        self.audit_store = audit_store
```

```python
# src/velaris_agent/velaris/orchestrator.py
if self.audit_store is not None:
    self.audit_store.append_event(
        session_id=resolved_session_id,
        step_name="orchestrator.routed",
        operator_id="VelarisBizOrchestrator",
        payload={"scenario": plan["scenario"], "routing": routing.to_dict()},
    )

if self.audit_store is not None:
    self.audit_store.append_event(
        session_id=resolved_session_id,
        step_name="orchestrator.completed",
        operator_id="VelarisBizOrchestrator",
        payload={"task_id": completed_task.task_id, "success": True},
    )

result = {
    "session_id": resolved_session_id,
    "plan": plan,
    "routing": routing.to_dict(),
    "authority": authority.to_dict(),
    "task": completed_task.to_dict(),
    "outcome": outcome.to_dict(),
    "result": scenario_result,
    "audit_event_count": (
        len(self.audit_store.list_by_session(resolved_session_id))
        if self.audit_store is not None
        else 0
    ),
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/test_persistence/test_postgres_runtime.py tests/test_biz/test_orchestrator.py -q
```

Expected:

```text
targeted tests pass; postgres integration tests may be skipped when VELARIS_TEST_POSTGRES_DSN is not configured
```

- [ ] **Step 5: Commit**

```bash
git add src/velaris_agent/persistence/postgres_runtime.py src/velaris_agent/velaris/task_ledger.py src/velaris_agent/velaris/outcome_store.py src/velaris_agent/velaris/orchestrator.py src/velaris_agent/persistence/factory.py tests/test_persistence/test_postgres_runtime.py tests/test_biz/test_orchestrator.py
git commit -m "feat(runtime): persist ledger outcome and audit events"
```

---

### Task 4: Add Database-Backed Job Queue And Move Self-Evolution Off The Hot Path

**Files:**
- Create: `src/velaris_agent/persistence/job_queue.py`
- Modify: `src/openharness/tools/save_decision_tool.py`
- Modify: `src/velaris_agent/evolution/self_evolution.py`
- Modify: `src/velaris_agent/persistence/factory.py`
- Modify: `src/openharness/cli.py`
- Test: `tests/test_persistence/test_job_queue.py`
- Test: `tests/test_tools/test_knowledge_tools.py`
- Test: `tests/test_commands/test_cli.py`

- [ ] **Step 1: Write the failing queue and worker tests**

```python
# tests/test_persistence/test_job_queue.py
from velaris_agent.persistence.job_queue import PostgresJobQueue
from velaris_agent.persistence.schema import bootstrap_schema


def test_job_queue_enqueue_claim_complete(postgres_dsn):
    bootstrap_schema(postgres_dsn)
    queue = PostgresJobQueue(postgres_dsn, max_attempts=3)

    job_id = queue.enqueue(
        job_type="self_evolution_review",
        idempotency_key="u1:travel:10",
        payload={"user_id": "u1", "scenario": "travel", "window": 20},
    )
    claimed = queue.claim_next(["self_evolution_review"])
    assert claimed is not None
    assert claimed.job_id == job_id

    queue.mark_succeeded(job_id)
    assert queue.get(job_id).status == "succeeded"
```

```python
# tests/test_tools/test_knowledge_tools.py
@pytest.mark.asyncio
async def test_save_decision_enqueue_review_instead_of_inline_run(tmp_path: Path, monkeypatch) -> None:
    from openharness.tools.base import ToolExecutionContext
    from openharness.tools.save_decision_tool import SaveDecisionInput, SaveDecisionTool

    queued: list[dict] = []

    class FakeQueue:
        def __init__(self, dsn: str, max_attempts: int = 3) -> None:
            self._dsn = dsn
            self._max_attempts = max_attempts

        def enqueue(self, *, job_type: str, idempotency_key: str, payload: dict) -> str:
            queued.append(
                {
                    "job_type": job_type,
                    "idempotency_key": idempotency_key,
                    "payload": payload,
                }
            )
            return "job-001"

    monkeypatch.setattr("velaris_agent.persistence.job_queue.PostgresJobQueue", FakeQueue)

    context = ToolExecutionContext(
        cwd=tmp_path,
        metadata={
            "decision_memory_dir": str(tmp_path / "decisions"),
            "postgres_dsn": "postgresql://ignored-for-mock",
            "evolution_review_interval": 1,
        },
    )

    result = await SaveDecisionTool().execute(
        SaveDecisionInput(
            user_id="u-save",
            scenario="travel",
            query="机票方案选择",
            recommended={"id": "cheap", "label": "便宜方案"},
            alternatives=[{"id": "fast", "label": "快速方案"}],
            options_discovered=[{"id": "cheap"}, {"id": "fast"}],
            weights_used={"price": 0.6, "comfort": 0.4},
            explanation="预算优先",
        ),
        context,
    )

    data = json.loads(result.output)
    assert data["self_evolution"]["triggered"] is False
    assert data["self_evolution"]["queued"] is True
    assert queued[0]["job_type"] == "self_evolution_review"
```

```python
# tests/test_commands/test_cli.py
def test_cli_storage_jobs_run_once(monkeypatch, runner):
    from openharness.cli import app

    monkeypatch.setenv("VELARIS_POSTGRES_DSN", "postgresql://velaris:secret@localhost:5432/velaris")
    monkeypatch.setattr("velaris_agent.persistence.job_queue.run_jobs_once", lambda dsn, limit: 2)

    result = runner.invoke(app, ["storage", "jobs", "run-once", "--limit", "5"])
    assert result.exit_code == 0
    assert "processed: 2" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_persistence/test_job_queue.py tests/test_tools/test_knowledge_tools.py tests/test_commands/test_cli.py -q
```

Expected:

```text
FAILED tests/test_persistence/test_job_queue.py::test_job_queue_enqueue_claim_complete - ModuleNotFoundError: No module named 'velaris_agent.persistence.job_queue'
FAILED tests/test_tools/test_knowledge_tools.py::test_save_decision_enqueue_review_instead_of_inline_run - queued field missing
FAILED tests/test_commands/test_cli.py::test_cli_storage_jobs_run_once - No such command 'storage jobs'
```

- [ ] **Step 3: Implement the queue, worker hook, and CLI runner**

```python
# src/velaris_agent/persistence/job_queue.py
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    job_type: str
    status: str
    payload: dict
    attempts: int


class PostgresJobQueue:
    def __init__(self, dsn: str, max_attempts: int = 3) -> None:
        self._dsn = dsn
        self._max_attempts = max_attempts
```

```python
# src/openharness/tools/save_decision_tool.py
if review_interval > 0 and current_count % review_interval == 0 and context.metadata.get("postgres_dsn"):
    from velaris_agent.persistence.job_queue import PostgresJobQueue

    queue = PostgresJobQueue(
        str(context.metadata["postgres_dsn"]),
        max_attempts=int(context.metadata.get("job_max_attempts", 3)),
    )
    queue.enqueue(
        job_type="self_evolution_review",
        idempotency_key=f"{arguments.user_id}:{arguments.scenario}:{current_count}",
        payload={
            "user_id": arguments.user_id,
            "scenario": arguments.scenario,
            "window": max(10, review_interval * 2),
        },
    )
    self_evolution_payload = {
        "triggered": False,
        "queued": True,
        "next_trigger_in": 0,
    }
```

```python
# src/openharness/cli.py
jobs_app = typer.Typer(help="Run Velaris background jobs.")
storage_app.add_typer(jobs_app, name="jobs")


@jobs_app.command("run-once")
def storage_jobs_run_once(limit: int = typer.Option(10, "--limit", min=1)) -> None:
    from openharness.config import load_settings
    from velaris_agent.persistence.job_queue import run_jobs_once

    settings = load_settings()
    processed = run_jobs_once(settings.storage.postgres_dsn, limit=limit)
    print(f"Processed: {processed}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/test_persistence/test_job_queue.py tests/test_tools/test_knowledge_tools.py tests/test_commands/test_cli.py -q
```

Expected:

```text
targeted tests pass; postgres integration tests may be skipped when VELARIS_TEST_POSTGRES_DSN is not configured
```

- [ ] **Step 5: Commit**

```bash
git add src/velaris_agent/persistence/job_queue.py src/openharness/tools/save_decision_tool.py src/velaris_agent/evolution/self_evolution.py src/velaris_agent/persistence/factory.py src/openharness/cli.py tests/test_persistence/test_job_queue.py tests/test_tools/test_knowledge_tools.py tests/test_commands/test_cli.py
git commit -m "feat(jobs): move self-evolution to postgres queue"
```

---

### Task 5: Add Health Commands, Readiness Checks, And Docs

**Files:**
- Create: `src/velaris_agent/persistence/health.py`
- Modify: `src/openharness/cli.py`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Test: `tests/test_persistence/test_schema.py`
- Test: `tests/test_commands/test_cli.py`

- [ ] **Step 1: Write the failing health and readiness tests**

```python
# tests/test_persistence/test_schema.py
from velaris_agent.persistence.health import StorageHealthReport


def test_storage_health_report_detects_missing_dsn():
    report = StorageHealthReport(
        status="degraded",
        checks=[{"name": "postgres_dsn", "ok": False, "detail": "missing"}],
    )
    assert report.status == "degraded"
```

```python
# tests/test_commands/test_cli.py
def test_cli_storage_doctor_reports_health(monkeypatch, runner):
    from openharness.cli import app

    monkeypatch.setenv("VELARIS_POSTGRES_DSN", "postgresql://velaris:secret@localhost:5432/velaris")
    monkeypatch.setattr(
        "velaris_agent.persistence.health.collect_storage_health",
        lambda dsn: {
            "status": "ok",
            "checks": [
                {"name": "postgres", "ok": True, "detail": "reachable"},
                {"name": "audit_tables", "ok": True, "detail": "ready"},
            ],
        },
    )

    result = runner.invoke(app, ["storage", "doctor"])
    assert result.exit_code == 0
    assert "status: ok" in result.output.lower()
    assert "audit_tables" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_persistence/test_schema.py tests/test_commands/test_cli.py -q
```

Expected:

```text
FAILED tests/test_persistence/test_schema.py::test_storage_health_report_detects_missing_dsn - ModuleNotFoundError: No module named 'velaris_agent.persistence.health'
FAILED tests/test_commands/test_cli.py::test_cli_storage_doctor_reports_health - No such command 'storage doctor'
```

- [ ] **Step 3: Implement health checks and docs**

```python
# src/velaris_agent/persistence/health.py
from pydantic import BaseModel, Field

from velaris_agent.persistence.postgres import postgres_connection


class StorageHealthReport(BaseModel):
    status: str
    checks: list[dict] = Field(default_factory=list)


def collect_storage_health(dsn: str) -> dict:
    if not dsn:
        return {
            "status": "degraded",
            "checks": [{"name": "postgres_dsn", "ok": False, "detail": "missing"}],
        }

    checks: list[dict] = []
    try:
        with postgres_connection(dsn) as conn, conn.cursor() as cur:
            cur.execute("select 1")
            cur.execute("select count(*) from information_schema.tables where table_name = 'audit_events'")
            audit_table_ready = cur.fetchone()[0] == 1
        checks.append({"name": "postgres", "ok": True, "detail": "reachable"})
        checks.append(
            {
                "name": "audit_tables",
                "ok": audit_table_ready,
                "detail": "ready" if audit_table_ready else "missing",
            }
        )
    except Exception as exc:
        checks.append({"name": "postgres", "ok": False, "detail": str(exc)})

    status = "ok" if checks and all(item["ok"] for item in checks) else "degraded"
    return {"status": status, "checks": checks}
```

```python
# src/openharness/cli.py
@storage_app.command("doctor")
def storage_doctor_cmd() -> None:
    from openharness.config import load_settings
    from velaris_agent.persistence.health import collect_storage_health

    settings = load_settings()
    report = collect_storage_health(settings.storage.postgres_dsn)
    print(f"status: {report['status']}")
    for check in report["checks"]:
        marker = "ok" if check["ok"] else "fail"
        print(f"- {check['name']}: {marker} ({check['detail']})")
```

```markdown
# README.md
## Storage bootstrap

```bash
export VELARIS_POSTGRES_DSN=postgresql://velaris:secret@localhost:5432/velaris
velaris storage init
velaris storage doctor
velaris storage jobs run-once --limit 10
```
```

```markdown
# docs/ARCHITECTURE.md
- `DecisionMemory` 默认仍可走文件后端；
- 生产模式下通过 `Settings.storage.postgres_dsn` 切换到 PostgreSQL repository；
- 后台任务使用 `job_queue / job_run` + 应用内 worker，不引入外部消息队列。
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/test_persistence/test_schema.py tests/test_commands/test_cli.py tests/test_biz/test_orchestrator.py -q
```

Expected:

```text
targeted tests pass
```

- [ ] **Step 5: Commit**

```bash
git add src/velaris_agent/persistence/health.py src/openharness/cli.py README.md docs/ARCHITECTURE.md tests/test_persistence/test_schema.py tests/test_commands/test_cli.py
git commit -m "feat(ops): add storage health and doctor commands"
```

---

## Final Verification

- [ ] Run the focused Phase 1 test suite

```bash
pytest \
  tests/test_persistence/test_settings.py \
  tests/test_persistence/test_schema.py \
  tests/test_persistence/test_postgres_memory.py \
  tests/test_persistence/test_postgres_runtime.py \
  tests/test_persistence/test_job_queue.py \
  tests/test_memory/test_decision_memory.py \
  tests/test_tools/test_decision_tools.py \
  tests/test_tools/test_knowledge_tools.py \
  tests/test_biz/test_orchestrator.py \
  tests/test_commands/test_cli.py \
  -q
```

Expected:

```text
all targeted tests pass; postgres integration tests may be skipped when VELARIS_TEST_POSTGRES_DSN is not configured
```

- [ ] Run lint and compile checks

```bash
ruff check src tests
python -m compileall src
```

Expected:

```text
0 lint errors
0 compile errors
```

- [ ] Manual smoke checks

```bash
export VELARIS_POSTGRES_DSN=postgresql://velaris:secret@localhost:5432/velaris
velaris storage init
velaris storage doctor
velaris storage jobs run-once --limit 5
```

Expected:

```text
Storage initialized: <n> statements applied
status: ok
Processed: <n>
```
