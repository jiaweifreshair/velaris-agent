# UOW-1 Code Generation Plan

## 说明

本文件是 `UOW-1 - Architecture Boundary And Core Contract` 的 **Code Generation 单一执行真相源**。
进入实现阶段后，所有代码修改、测试补充、文档落点和进度更新都必须以本计划为准。

- **项目类型**: Brownfield
- **工作区根目录**: `/Users/apus/Documents/UGit/velaris-agent`
- **单元目标**: 把 `UOW-1` 已批准的 Functional Design / NFR Requirements / NFR Design 落到最小可运行的 execution contract、PostgreSQL 主线、fail-closed 屏障与 envelope-first 输出
- **代码生成原则**:
  - 优先修改现有文件，不创建 `_new` / `_modified` 之类重复文件
  - 严格中文注释与中文总结
  - 先写失败测试，再写实现，遵循 TDD
  - 只触达本单元真正拥有的边界：`execution / gate / audit / session / envelope`

## 单元上下文与追踪

### 本单元实现的需求映射

- **Core FR**:
  - `FR-1` 定位收束
  - `FR-2` 一等执行单元
  - `FR-4` 完成 contract
- **Supporting FR**:
  - `FR-6` 授权到执行门
- **关键 NFR**:
  - `NFR-UOW1-01` PostgreSQL 主存储
  - `NFR-UOW1-02` fail-closed
  - `NFR-UOW1-03` 高风险同步审计 / 中风险补审计可追踪
  - `NFR-UOW1-05` payload 脱敏与最小暴露
  - `NFR-UOW1-06` envelope-first 薄兼容
  - `NFR-UOW1-07` 可验证性与单一主语义源

### 本单元依赖与接口

- **上游既有依赖**:
  - `src/velaris_agent/biz/engine.py` 提供 capability planning 与 scenario 执行能力
  - `src/velaris_agent/velaris/router.py` 提供 routing
  - `src/velaris_agent/velaris/authority.py` 提供 authority plan
- **本单元拥有的接口 / contract**:
  - `DecisionExecutionRequest`
  - `BizExecutionRecord`
  - `GovernanceGateDecision`
  - `DecisionExecutionEnvelope`
- **本单元数据库实体**:
  - `execution`
  - `session`
  - `task`
  - `outcome`
  - `audit`

### 预期修改 / 新增文件

#### 预计修改
- `src/velaris_agent/persistence/schema.py`
- `src/velaris_agent/persistence/factory.py`
- `src/velaris_agent/persistence/postgres_runtime.py`
- `src/velaris_agent/persistence/__init__.py`
- `src/velaris_agent/velaris/orchestrator.py`
- `src/openharness/services/session_storage.py`
- `src/openharness/tools/biz_execute_tool.py`
- `tests/test_persistence/test_schema.py`
- `tests/test_persistence/test_postgres_runtime.py`
- `tests/test_services/test_session_storage.py`
- `tests/test_biz/test_orchestrator.py`
- `tests/test_tools/test_biz_execute_tool.py`

#### 预计新增
- `src/velaris_agent/velaris/execution_contract.py`
- `src/velaris_agent/velaris/persistence_barrier.py`
- `src/velaris_agent/velaris/payload_redactor.py`
- `src/velaris_agent/velaris/failure_classifier.py`
- `src/velaris_agent/persistence/postgres_execution.py`
- `tests/test_biz/test_execution_contract.py`
- `tests/test_biz/test_persistence_barrier.py`
- `tests/test_biz/test_payload_redactor.py`
- `tests/test_biz/test_failure_classifier.py`
- `tests/test_persistence/test_postgres_execution.py`
- `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/code/business-logic-summary.md`
- `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/code/repository-layer-summary.md`
- `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/code/api-layer-summary.md`

## 代码生成步骤

### Step 1 - 建立 execution contract 的失败测试
- [x] 新增 `tests/test_biz/test_execution_contract.py`
- [x] 为 `DecisionExecutionRequest / BizExecutionRecord / GovernanceGateDecision / DecisionExecutionEnvelope` 写失败测试
- [x] 覆盖主状态、三层 completion 派生字段、`gate_status`、最小 alias 所需字段
- [x] 追踪需求: `FR-2`, `FR-4`, `NFR-UOW1-06`, `NFR-UOW1-07`

### Step 2 - 实现 execution contract 与基础安全 / 错误组件
- [x] 新增 `src/velaris_agent/velaris/execution_contract.py`
- [x] 新增 `src/velaris_agent/velaris/payload_redactor.py`
- [x] 新增 `src/velaris_agent/velaris/failure_classifier.py`
- [x] 在这些文件中落地 execution-level contract、默认脱敏规则与基础错误分类
- [x] 追踪需求: `FR-1`, `FR-2`, `FR-4`, `NFR-UOW1-05`, `NFR-UOW1-07`

### Step 3 - 业务逻辑层单元测试回绿
- [x] 运行并修复 `tests/test_biz/test_execution_contract.py`
- [x] 新增 `tests/test_biz/test_payload_redactor.py`
- [x] 新增 `tests/test_biz/test_failure_classifier.py`
- [x] 确认 contract、脱敏与错误分类测试全部通过
- [x] 追踪需求: `NFR-UOW1-05`, `NFR-UOW1-07`

### Step 4 - 建立 PostgreSQL execution / session 显式结构的失败测试
- [x] 新增 `tests/test_persistence/test_postgres_execution.py`
- [x] 修改 `tests/test_persistence/test_schema.py`
- [x] 为显式 `execution / session` 表结构、主键 / 关联键、状态字段和 bootstrap 行为写失败测试
- [x] 追踪需求: `NFR-UOW1-01`, `NFR-UOW1-02`, `NFR-UOW1-03`

### Step 5 - 实现 repository 层与 schema 收束
- [x] 修改 `src/velaris_agent/persistence/schema.py`，把最小 payload bootstrap 收束为显式结构表 bootstrap
- [x] 新增 `src/velaris_agent/persistence/postgres_execution.py`，实现 `ExecutionRepository / SessionRepository`
- [x] 修改 `src/velaris_agent/persistence/postgres_runtime.py`，让 `task / outcome / audit` 迁移到显式结构或与显式结构兼容的仓储实现
- [x] 修改 `src/velaris_agent/persistence/factory.py` 与 `src/velaris_agent/persistence/__init__.py`，把 PostgreSQL 提升为正式主线并暴露新仓储入口
- [x] 追踪需求: `FR-2`, `FR-6`, `NFR-UOW1-01`, `NFR-UOW1-02`, `NFR-UOW1-03`

### Step 6 - repository 层测试回绿
- [x] 运行并修复 `tests/test_persistence/test_schema.py`
- [x] 运行并修复 `tests/test_persistence/test_postgres_runtime.py`
- [x] 运行并修复 `tests/test_persistence/test_postgres_execution.py`
- [x] 确认 execution / session / task / outcome / audit 的 PostgreSQL 主线闭环可验证
- [x] 追踪需求: `NFR-UOW1-01`, `NFR-UOW1-02`, `NFR-UOW1-03`, `NFR-UOW1-07`

### Step 7 - 建立 session PostgreSQL 化与 fail-closed 屏障的失败测试
- [x] 修改 `tests/test_services/test_session_storage.py`，为 session PostgreSQL 主线与恢复语义写失败测试
- [x] 新增 `tests/test_biz/test_persistence_barrier.py`，为 `PreExecutionPersistenceBarrier` 的集中落库屏障和 fail-closed 行为写失败测试
- [x] 追踪需求: `FR-2`, `FR-6`, `NFR-UOW1-01`, `NFR-UOW1-02`

### Step 8 - 实现 session 持久化与 pre-execution persistence barrier
- [x] 修改 `src/openharness/services/session_storage.py`，把 session snapshot 主线迁移到 PostgreSQL
- [x] 新增 `src/velaris_agent/velaris/persistence_barrier.py`
- [x] 在 `persistence_barrier.py` 中实现“先算后集中落库”的 pre-execution barrier、`audit_status` 初始推进和 fail-closed 分类
- [x] 追踪需求: `FR-2`, `FR-6`, `NFR-UOW1-01`, `NFR-UOW1-02`, `NFR-UOW1-03`

### Step 9 - 修改 orchestrator 为 envelope-first 主路径
- [x] 修改 `src/velaris_agent/velaris/orchestrator.py`
- [x] 把 orchestrator 拆成：planning / gate 内存阶段、pre-execution barrier、scenario 执行、outcome / audit 推进、envelope 组装
- [x] 让 orchestrator 以 `DecisionExecutionEnvelope` 为主输出，而非旧平铺 payload
- [x] 让高风险同步审计、中风险 `audit_status = pending|persisted|failed` 的规则进入主路径
- [x] 追踪需求: `FR-1`, `FR-2`, `FR-4`, `FR-6`, `NFR-UOW1-02`, `NFR-UOW1-03`, `NFR-UOW1-06`

### Step 10 - orchestrator 与 API/tool 层测试回绿
- [x] 修改 `tests/test_biz/test_orchestrator.py`，让测试围绕 `execution / gate_decision / audit_status / envelope` 断言
- [x] 修改 `src/openharness/tools/biz_execute_tool.py`，让其返回 envelope 主输出 + 极少数 alias
- [x] 修改 `tests/test_tools/test_biz_execute_tool.py`，验证 `biz_execute` 的 envelope-first 兼容输出
- [x] 确认 orchestrator/tool 测试全部回绿
- [x] 追踪需求: `FR-1`, `FR-2`, `FR-4`, `FR-6`, `NFR-UOW1-06`, `NFR-UOW1-07`

### Step 11 - 代码生成阶段文档总结
- [x] 新增 `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/code/business-logic-summary.md`
- [x] 新增 `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/code/repository-layer-summary.md`
- [x] 新增 `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/code/api-layer-summary.md`
- [x] 在总结文档中记录修改文件、关键设计对照、测试覆盖点与剩余风险
- [x] 追踪需求: `FR-7`, `NFR-UOW1-07`

### Step 12 - 本单元生成收尾检查
- [x] 校验本计划所有触达路径均在工作区根目录内，无重复文件或临时副本
- [x] 校验测试文件与实现文件一一对应
- [x] 校验 envelope 主输出、PostgreSQL 主存储、fail-closed 与默认脱敏四条主线均已落地
- [x] 为下一阶段 `Build & Test` 准备实际构建与测试入口说明
- [x] 追踪需求: `NFR-UOW1-01`, `NFR-UOW1-02`, `NFR-UOW1-05`, `NFR-UOW1-06`, `NFR-UOW1-07`

## 计划摘要

- **总步骤数**: 12
- **实现重点**: execution contract、PostgreSQL 显式结构表、pre-execution persistence barrier、audit_status 补审计、envelope-first 输出
- **测试重点**: contract 测试、repository/schema 测试、session/barrier 测试、orchestrator/tool focused tests
- **预计范围**: 中到高；涉及持久化层、业务编排层、工具层和测试层的协同改动
- **本计划审批后，Code Generation 必须严格按上述步骤顺序执行**
