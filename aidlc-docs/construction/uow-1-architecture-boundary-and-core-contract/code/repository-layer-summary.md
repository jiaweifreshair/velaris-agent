# UOW-1 代码总结 - Repository Layer

## 范围
本文件总结 `UOW-1` 在持久化主线上的收束，包括 PostgreSQL 显式结构表、execution/session 仓储、runtime 仓储兼容、session 主线切换，以及写入前脱敏。

## 关键实现文件
- `src/velaris_agent/persistence/schema.py`
- `src/velaris_agent/persistence/postgres_execution.py`
- `src/velaris_agent/persistence/postgres_runtime.py`
- `src/velaris_agent/persistence/factory.py`
- `src/velaris_agent/persistence/__init__.py`
- `src/openharness/services/session_storage.py`

## 已落地设计对照

### 1. PostgreSQL 成为正式主存储
- schema bootstrap 已显式创建 `session_records` 与 `execution_records`。
- `task / outcome / audit` 继续作为卫星表存在，但已和 execution 主实体语义对齐。
- `ExecutionRepository / SessionRepository` 在 `postgres_execution.py` 中正式实现。

### 2. session / execution 不再依赖松散 payload 表达
- `SessionRecord` 保存会话级恢复信息与最小 snapshot。
- `BizExecutionRecord` 通过 `ExecutionRepository` 落库，显式保存：
  - `execution_status`
  - `gate_status`
  - `effective_risk_level`
  - `degraded_mode`
  - `audit_status`
  - 三层 completion 字段
  - `resume_cursor`
- execution snapshot 保留在 `snapshot_json` 中，关系字段则保持结构化列。

### 3. 主流程写入前默认脱敏
- `postgres_runtime.py` 已接入 `PayloadRedactor`。
- outcome / audit / snapshot 进入 PostgreSQL 前会先经过默认脱敏规则，避免明文敏感字段被长期持久化。

### 4. session_storage 切换到 PostgreSQL 主线
- `session_storage.py` 在检测到 PostgreSQL 仓储可用时，优先通过 `SessionRepository` 完成保存、读取与列出。
- 文件系统只保留兼容缓存和 Markdown 导出角色，不再是正式主线。

### 5. 工厂与导出面统一
- `factory.py` 已新增 execution / session 仓储构建入口。
- `persistence.__init__` 已暴露新的仓储实现，避免 orchestrator 和服务层绕过工厂手写依赖。

## 测试覆盖点
- `tests/test_persistence/test_schema.py`
- `tests/test_persistence/test_postgres_runtime.py`
- `tests/test_persistence/test_postgres_execution.py`
- `tests/test_services/test_session_storage.py`
- `tests/test_biz/test_persistence_barrier.py`

重点覆盖：
- schema bootstrap 是否包含 execution/session 结构表
- execution repository 的 create / update / load / list 语义
- runtime 仓储是否和显式 execution 结构兼容
- session storage 是否优先走 PostgreSQL 仓储
- barrier 在集中落库失败时是否 fail-closed

## 剩余风险
- 真实 PostgreSQL 集成用例依赖环境变量，默认开发机上可能被跳过。
- 当前 session 文件兼容层仍然存在双写以外的旁路读取入口，后续可继续收紧，让 PostgreSQL 成为唯一默认恢复源。
