# Velaris SQLite 主线切换设计

> 目标：把 `velaris-agent` 从“PostgreSQL 主线 + 文件型 session 兼容残留”收束为“项目内 SQLite 单库、单一真相源、无旧 JSON 回退、无 PostgreSQL 正式入口”的本地优先架构。

## 1. 设计背景

当前仓库已经完成了一轮以 `execution / session / task / outcome / audit` 为中心的持久化收束，但这轮收束是建立在 PostgreSQL 主线之上的：

- `src/velaris_agent/persistence/postgres_execution.py`
- `src/velaris_agent/persistence/postgres_runtime.py`
- `src/velaris_agent/persistence/postgres_memory.py`
- `src/velaris_agent/persistence/job_queue.py`
- `src/openharness/services/session_storage.py`
- `src/openharness/cli.py`
- `src/openharness/config/settings.py`

与此同时，仓库仍残留两类会破坏统一心智模型的旧路径：

1. 项目内 `.velaris-agent/session-*.json` 与 `latest.json` 的文件型 session 快照
2. 通过 `VELARIS_POSTGRES_DSN` 与 `storage.postgres_dsn` 控制的 PostgreSQL 条件分支

这会带来三个直接问题：

1. 运行主线并不真正唯一，存在数据库、文件、内存三种语义入口
2. 本地单机使用需要额外数据库环境，违背“最小可信闭环”的目标
3. 恢复、审计、工具 wiring 与测试口径被 PostgreSQL/文件兼容逻辑拖复杂

用户已明确确认本轮目标：

- `SQLite` 取代 `PostgreSQL` 成为默认且唯一官方主线
- 数据库文件固定在项目内 `.velaris-agent/velaris.db`
- 旧 JSON session 文件彻底切断，不做导入兼容
- PostgreSQL 主线与相关测试本轮直接物理删除
- 覆盖范围不只包含主运行链，还包含 `decision_memory`、`job_queue` 与相关工具 wiring

因此，这次改造不是“新增 SQLite 选项”，而是一次正式的主线切换与历史路径清除。

## 2. 设计目标

### 2.1 本轮目标

1. 以项目内 SQLite 单库作为唯一正式存储主线
2. 让 `session / execution / task / outcome / audit / decision_memory / job_queue` 全部进入同一数据库
3. 删除 `postgres_*` 实现、`psycopg` 兼容层、DSN 配置与相关正式测试
4. 删除旧 JSON session 文件读写逻辑，避免双真相源
5. 统一 CLI、settings、factory、tools、AI-DLC 文档口径
6. 保持现有 `DecisionExecutionEnvelope`、治理门、审计与 fail-closed 语义不变

### 2.2 非目标

1. 不做 PostgreSQL 到 SQLite 的迁移工具
2. 不保留双写或回退兼容
3. 不借本轮重构整个领域模型
4. 不把 `task / outcome / audit / decision` 的 payload 风格一次性全部改成显式列
5. 不引入 ORM、迁移框架、Redis、Kafka 等额外基础设施

## 3. 核心设计决策

| 编号 | 决策 | 结论 |
| --- | --- | --- |
| D-01 | 官方主线存储 | SQLite 成为唯一官方主线 |
| D-02 | 数据库位置 | 每个项目固定为 `.velaris-agent/velaris.db` |
| D-03 | 旧 session 文件 | 不再读写 `latest.json` 和 `session-*.json` |
| D-04 | PostgreSQL 主线 | 本轮直接物理删除，不保留 deprecated 壳 |
| D-05 | schema 初始化 | 通过 `velaris storage init` 显式初始化 |
| D-06 | 运行时后端选择 | 不再根据 DSN 分叉，运行时默认总是构建 SQLite 仓储 |
| D-07 | 错误策略 | 所有存储错误 fail-closed，不静默回退到文件或内存 |

## 4. 目标架构

### 4.1 目标形态

```text
Project Root
├─ .velaris-agent/
│  └─ velaris.db
├─ OpenHarness Runtime / CLI / Tools
│  └─ Velaris orchestration / storage factories
└─ SQLite single source of truth
   ├─ session_records
   ├─ execution_records
   ├─ decision_records
   ├─ task_ledger_records
   ├─ outcome_records
   ├─ audit_events
   ├─ job_queue
   └─ job_runs
```

### 4.2 设计原则

1. **项目隔离优先**，数据库跟项目走，不走全局单库
2. **单一真相源优先**，不同时维护 SQLite、JSON、内存三套正式状态
3. **显式失败优先**，不靠“无感降级”掩盖未初始化或库损坏问题
4. **小步重构优先**，先切主线，再逐步精炼表结构

## 5. 模块替换设计

### 5.1 新增模块

- `src/velaris_agent/persistence/sqlite.py`
  - 提供 SQLite 连接、事务上下文、基础 `PRAGMA`
- `src/velaris_agent/persistence/sqlite_execution.py`
  - 提供 `SessionRecord / SessionRepository / ExecutionRepository`
- `src/velaris_agent/persistence/sqlite_runtime.py`
  - 提供 `TaskLedger / OutcomeStore / AuditStore` 的 SQLite 实现
- `src/velaris_agent/persistence/sqlite_memory.py`
  - 提供 `DecisionMemory` 的 SQLite 实现

### 5.2 删除模块

本轮直接删除以下 PostgreSQL 主线文件：

- `src/velaris_agent/persistence/postgres.py`
- `src/velaris_agent/persistence/postgres_execution.py`
- `src/velaris_agent/persistence/postgres_runtime.py`
- `src/velaris_agent/persistence/postgres_memory.py`
- `src/velaris_agent/persistence/psycopg_compat.py`

### 5.3 保留但重写的模块

- `src/velaris_agent/persistence/job_queue.py`
  - 保留文件职责，但类名改为 `SqliteJobQueue`
  - 改为基于 SQLite 的显式队列表实现
- `src/velaris_agent/persistence/factory.py`
  - 从“按 `postgres_dsn` 条件切换”改为“按项目路径统一构建 SQLite 仓储”
- `src/velaris_agent/persistence/schema.py`
  - 从 PostgreSQL DDL 改为 SQLite DDL
- `src/openharness/services/session_storage.py`
  - 从“文件服务 + PostgreSQL 优先”改为“项目会话仓储门面”
- `src/openharness/cli.py`
  - `storage` 子命令彻底改为 SQLite 口径
- `src/openharness/config/settings.py`
  - 删除 `storage.postgres_dsn`

### 5.4 包导出策略

`src/velaris_agent/persistence/__init__.py` 不再暴露 `postgres_connection` 或 `postgres_execution`。  
对外只保留 SQLite 主线相关导出，避免后续调用点继续从包入口误拿 PostgreSQL 语义。

## 6. SQLite 连接与事务设计

### 6.1 连接 helper

`sqlite.py` 负责三件事：

1. 解析数据库路径
2. 返回带事务语义的 `sqlite3.Connection`
3. 在连接建立时设置统一 `PRAGMA`

### 6.2 连接配置

每次连接建立后，统一执行：

- `PRAGMA foreign_keys = ON`
- `PRAGMA journal_mode = WAL`
- `PRAGMA synchronous = NORMAL`
- `PRAGMA busy_timeout = 5000`

原因：

1. `foreign_keys = ON` 保证 `execution -> session` 约束真实生效
2. `WAL` + `NORMAL` 在单机多读少写场景更稳
3. `busy_timeout` 避免临时锁竞争直接变成硬错误

### 6.3 JSON 策略

本轮所有 JSON 字段统一在 Python 层做 `json.dumps/json.loads`。  
SQLite 不作为 JSON 语义执行引擎的强依赖，避免把实现绑在 `json_extract` 等特性上。

## 7. 数据路径设计

### 7.1 数据库路径

数据库文件固定为：

```text
<project-root>/.velaris-agent/velaris.db
```

对应新增路径 helper，建议放在：

- `src/openharness/config/paths.py`

建议新增函数：

- `get_project_database_path(cwd: str | Path) -> Path`

### 7.2 目录行为

- `.velaris-agent/` 目录不存在时，运行时可自动创建目录
- `velaris.db` 文件不存在时，连接可自动创建文件
- schema 不自动隐式补齐，正式通过 `velaris storage init` 创建表结构

这样可以把“目录存在”和“schema 已初始化”这两个状态清楚地区分开。

## 8. 表结构设计

### 8.1 `session_records`

保留显式结构：

- `session_id TEXT PRIMARY KEY`
- `binding_mode TEXT NOT NULL`
- `source_runtime TEXT NOT NULL`
- `summary TEXT NOT NULL DEFAULT ''`
- `message_count INTEGER NOT NULL DEFAULT 0`
- `snapshot_json TEXT NOT NULL DEFAULT '{}'`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

说明：

- `snapshot_json` 保存完整快照
- 列表页所需字段使用显式列，避免每次都反序列化全部消息

### 8.2 `execution_records`

保留显式结构：

- `execution_id TEXT PRIMARY KEY`
- `session_id TEXT NULL`
- `scenario TEXT NOT NULL`
- `execution_status TEXT NOT NULL`
- `gate_status TEXT NOT NULL`
- `effective_risk_level TEXT NOT NULL`
- `degraded_mode INTEGER NOT NULL DEFAULT 0`
- `audit_status TEXT NOT NULL`
- `structural_complete INTEGER NOT NULL DEFAULT 0`
- `constraint_complete INTEGER NOT NULL DEFAULT 0`
- `goal_complete INTEGER NOT NULL DEFAULT 0`
- `resume_cursor_json TEXT NOT NULL DEFAULT '{}'`
- `snapshot_json TEXT NOT NULL DEFAULT '{}'`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

外键：

- `session_id REFERENCES session_records(session_id)`

说明：

- execution 是运行时主语义对象，因此显式列必须完整
- `resume_cursor_json` 与 `snapshot_json` 继续用 JSON 文本保存，避免本轮扩表过度

### 8.3 `decision_records`

本轮延续 payload 风格：

- `record_id TEXT PRIMARY KEY`
- `created_at TEXT NOT NULL`
- `payload_json TEXT NOT NULL`

说明：

- 决策记忆的核心工作是“换主线数据库”，不是本轮重做 schema

### 8.4 `task_ledger_records`

- `record_id TEXT PRIMARY KEY`
- `created_at TEXT NOT NULL`
- `payload_json TEXT NOT NULL`

### 8.5 `outcome_records`

- `record_id TEXT PRIMARY KEY`
- `created_at TEXT NOT NULL`
- `payload_json TEXT NOT NULL`

### 8.6 `audit_events`

- `record_id TEXT PRIMARY KEY`
- `created_at TEXT NOT NULL`
- `payload_json TEXT NOT NULL`

### 8.7 `job_queue`

本轮改成显式列，不再把关键查询字段藏在 JSON 里：

- `job_id TEXT PRIMARY KEY`
- `job_type TEXT NOT NULL`
- `status TEXT NOT NULL`
- `idempotency_key TEXT NOT NULL`
- `payload_json TEXT NOT NULL`
- `attempt_count INTEGER NOT NULL DEFAULT 0`
- `created_at TEXT NOT NULL`
- `claimed_at TEXT NULL`
- `finished_at TEXT NULL`
- `last_error TEXT NULL`
- `current_run_id TEXT NULL`

### 8.8 `job_runs`

- `run_id TEXT PRIMARY KEY`
- `job_id TEXT NOT NULL`
- `job_type TEXT NOT NULL`
- `attempt_count INTEGER NOT NULL`
- `status TEXT NOT NULL`
- `started_at TEXT NOT NULL`
- `finished_at TEXT NULL`
- `last_error TEXT NULL`

### 8.9 索引

第一轮就建立以下索引：

- `session_records(updated_at DESC)`
- `execution_records(session_id, updated_at DESC)`
- `task_ledger_records(created_at DESC)`
- `outcome_records(created_at DESC)`
- `audit_events(created_at DESC)`
- `job_queue(status, created_at ASC)`
- `job_queue(job_type, status, created_at ASC)`
- `job_runs(job_id, started_at ASC)`

## 9. settings 与 factory 设计

### 9.1 settings 变更

`StorageSettings` 删除：

- `postgres_dsn`

`StorageSettings` 保留：

- `evidence_dir`
- `job_poll_interval_seconds`
- `job_max_attempts`

原因：

1. SQLite 路径由项目路径推导，不属于全局 settings
2. 一旦继续保留 `postgres_dsn`，调用点就会反复把“后端可选”当成合理前提

### 9.2 factory 变更

所有 factory 从“按 DSN 条件切换”改为“按 cwd 统一构建 SQLite”：

- `build_decision_memory(cwd=...)`
- `build_task_ledger(cwd=...)`
- `build_outcome_store(cwd=...)`
- `build_audit_store(cwd=...)`
- `build_session_repository(cwd=...)`
- `build_execution_repository(cwd=...)`
- `build_job_queue(cwd=...)`

目标：

- 任何运行路径默认都有数据库主线
- 不再通过“有没有 DSN”来决定是否持久化

## 10. CLI 设计

### 10.1 `velaris storage init`

新语义：

- 初始化当前项目 `.velaris-agent/velaris.db`
- 创建全部必需表与索引

输出示例：

```text
Initialized SQLite storage at /path/to/project/.velaris-agent/velaris.db
Created 8 tables and 8 indexes.
```

### 10.2 `velaris storage jobs run-once --limit N`

新语义：

- 直接读取当前项目 SQLite `job_queue`
- 运行最小 worker

不再需要 DSN，不再依赖外部数据库服务。

### 10.3 `velaris storage doctor`

建议新增命令，检查：

1. `.velaris-agent/` 是否存在
2. `velaris.db` 是否存在
3. 必需表是否齐全
4. schema 是否完整

原因：

- SQLite 本地模式下，真正影响可用性的不是 DSN，而是文件和 schema 状态

### 10.4 `/session` 与 `/tag` 命令语义调整

旧实现把 session 快照当作 JSON 文件管理，因此 `/session` 与 `/tag` 的输出完全基于文件目录。
切换到 SQLite 后，相关命令需要明确改成“数据库主线 + Markdown 导出辅线”：

- `/session`
  - 显示当前项目数据库路径、最近 session ID、消息数、最近 transcript 导出状态
- `/session path`
  - 返回当前项目 SQLite 数据库路径，而不是旧的 session JSON 目录
- `/session ls`
  - 列出 SQLite 中最近的 session 摘要，而不是列目录文件名
- `/session tag NAME`
  - 导出当前 transcript 为 `NAME.md`
  - 不再生成 `NAME.json`
- `/tag NAME`
  - 复用 `/session tag NAME` 的新语义
- `/session clear`
  - 只清理 `session_records` 中的会话快照，并删除 transcript 导出文件
  - 不清空 `execution / decision / audit / job_queue` 等其它正式数据

这样可以避免“清理会话”误删整库，同时保留用户已经形成的 Markdown 导出习惯。

## 11. 运行时流程设计

### 11.1 session 主线

`session_storage.py` 完整切换为 SQLite：

- `save_session_snapshot()` 只写 `session_records`
- `load_session_snapshot()` 只从 `session_records` 读最新记录
- `list_session_snapshots()` 只从 `session_records` 列表查询
- `load_session_by_id()` 只从 `session_records` 读取

同时明确两个 API 决策：

- `save_session_snapshot()` 改为返回 `session_id: str`，不再伪装成“已写入文件路径”
- `export_session_markdown()` 继续返回 Markdown 导出文件路径，作为人类可读导出能力保留

为控制范围，本轮允许保留 `get_project_session_dir()` 作为 transcript 导出目录 helper，
但它的职责必须收窄为“Markdown 导出目录”，不再承载正式 session snapshot 存储语义

不再写：

- `latest.json`
- `session-<id>.json`

不再读：

- 任何旧 JSON session 文件

### 11.2 orchestrator 主线

`VelarisBizOrchestrator` 不再接 `postgres_dsn`。  
所有 runtime repository 统一通过 `cwd` 或运行时路径上下文构建 SQLite 仓储。

保持不变的语义：

- `DecisionExecutionEnvelope`
- `GovernanceGateDecision`
- `PreExecutionPersistenceBarrier`
- fail-closed 错误传播

### 11.3 tools wiring

所有依赖 `context.metadata["postgres_dsn"]` 的工具 wiring 一律删除。  
工具层只传运行上下文，factory 根据项目路径自行定位 SQLite 数据库。

重点覆盖：

- `save_decision`
- `recall_preferences`
- `recall_decisions`
- `decision_score`
- `self_evolution_review`

### 11.4 `decision_memory`

`DecisionMemory` 的 SQLite 实现成为正式主线。  
文件型 `DecisionMemory` 不再是正式运行路径，只保留为测试或后续独立清理对象。

### 11.5 `job_queue`

`job_queue` 改为 SQLite 队列主线。  
自进化 worker 的调度仍保持最小闭环，不引入消息中间件。

## 12. 错误语义设计

### 12.1 错误分类

保留并扩展以下稳定错误面：

- `storage_not_initialized`
  - 数据库文件存在，但 schema 不完整或关键表缺失
- `storage_unavailable`
  - 数据库无法打开、目录权限异常、数据库损坏、锁超时
- `gate_denied`
  - 治理门拒绝执行
- `execution_failed`
  - 真实业务执行失败

### 12.2 行为约束

1. `storage_not_initialized` 必须给出明确操作提示，例如执行 `velaris storage init`
2. `storage_unavailable` 必须做脱敏处理，不泄露多余敏感信息
3. 所有 storage 错误都不回退到文件或内存

## 13. 删除范围

### 13.1 正式代码删除

- `src/velaris_agent/persistence/postgres.py`
- `src/velaris_agent/persistence/postgres_execution.py`
- `src/velaris_agent/persistence/postgres_runtime.py`
- `src/velaris_agent/persistence/postgres_memory.py`
- `src/velaris_agent/persistence/psycopg_compat.py`

### 13.2 正式测试删除或替换

以下 PostgreSQL 测试文件本轮直接删除，并由 SQLite 版本替代：

- `tests/test_persistence/test_postgres.py`
- `tests/test_persistence/test_postgres_execution.py`
- `tests/test_persistence/test_postgres_runtime.py`
- `tests/test_persistence/test_postgres_memory.py`

### 13.3 配置与环境变量清理

彻底删除：

- `VELARIS_POSTGRES_DSN`
- 所有 `postgres_dsn` 参数
- 所有基于 DSN 的 metadata 透传
- 所有 `psycopg` 驱动存在性相关逻辑

## 14. 文档同步范围

本轮必须同步以下文档口径：

- `aidlc-docs/aidlc-state.md`
- `aidlc-docs/audit.md`
- `aidlc-docs/construction/.../nfr-requirements/*.md`
- `aidlc-docs/construction/.../nfr-design/*.md`
- `aidlc-docs/construction/build-and-test/*.md`
- 与 PostgreSQL 主线相关的说明、命令示例、验收口径

原则：

- 正式主线统一改为 SQLite
- 历史审计记录允许保留“曾经使用 PostgreSQL”的事实，但必须显式标明已经过时

## 15. 实施顺序

本轮实现建议按以下顺序推进：

1. 路径与配置主线切换
   - 新增数据库路径 helper
   - 删除 `storage.postgres_dsn`
   - 改写 `factory.py`
2. schema 与基础连接层切换
   - 新增 `sqlite.py`
   - 改写 `schema.py`
   - 改写 `storage init`
3. 主运行链切换
   - `session_storage.py`
   - `sqlite_execution.py`
   - `sqlite_runtime.py`
   - `orchestrator.py`
4. 正式运行能力切换
   - `sqlite_memory.py`
   - `job_queue.py`
   - tools wiring
5. 清理与收尾
   - 删除全部 PostgreSQL 主线代码与测试
   - 更新 AI-DLC 文档
   - 运行全量验证

## 16. 风险与控制

### 16.1 主要风险

1. 删除 PostgreSQL 后遗漏调用点，导致运行时 import error
2. `session_storage.py` 签名或返回值仍假设“文件已写入”
3. 旧测试或工具断言还在引用 `postgres_dsn`
4. SQLite 队列语义改写时破坏幂等与运行状态流转

### 16.2 控制手段

1. 全仓搜索残留：
   - `rg -n "postgres|postgresql|psycopg|postgres_dsn|VELARIS_POSTGRES_DSN" src tests aidlc-docs`
2. 明确把 `session_storage.py` 定位成“仓储门面”而不是“文件服务”
3. 先切路径与 schema，再切运行时 wiring，最后删除旧实现
4. `job_queue` 保持现有业务语义，只替换存储层

## 17. 验收标准

本轮完成必须同时满足以下条件：

1. `uv run ruff check src tests scripts` 通过
2. `./scripts/run_pytest.sh -q` 通过
3. `velaris storage init` 可成功初始化当前项目 `.velaris-agent/velaris.db`
4. `velaris storage jobs run-once --limit N` 可从 SQLite 队列运行
5. session 保存、列出、读取全部只经过 SQLite
6. orchestrator 主路径、envelope-first 输出、barrier 语义保持成立
7. 正式代码与正式测试不再依赖 PostgreSQL
8. 正式运行路径不再读取旧 JSON session 文件

## 18. 设计结论

这次改造的本质不是“增加一个更轻的数据库选项”，而是：

把 `velaris-agent` 收束成一个真正本地优先、项目内单库、单一真相源的运行时架构。

切换完成后，开发者对系统的心智模型将明显变简单：

- 在哪个项目里运行 Velaris，就使用哪个项目自己的 SQLite 库
- 所有正式状态都在 `.velaris-agent/velaris.db`
- 没有 PostgreSQL 条件分支
- 没有旧 JSON session 回退
- 没有“默认文件模式”和“增强数据库模式”的双语义系统

这正是本轮“SQLite 取代 PostgreSQL 成为唯一官方主线，且直接切断旧路径”的目标落地方式。
