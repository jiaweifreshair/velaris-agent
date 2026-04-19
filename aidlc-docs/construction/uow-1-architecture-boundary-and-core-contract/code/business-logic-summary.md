# UOW-1 代码总结 - Business Logic

## 范围
本文件总结 `UOW-1 - Architecture Boundary And Core Contract` 在业务编排层的落地结果，覆盖 execution contract、governance gate、effective risk、pre-execution barrier 接入，以及 envelope-first 输出主路径。

## 关键实现文件
- `src/velaris_agent/velaris/execution_contract.py`
- `src/velaris_agent/velaris/orchestrator.py`
- `src/velaris_agent/velaris/persistence_barrier.py`
- `src/velaris_agent/velaris/payload_redactor.py`
- `src/velaris_agent/velaris/failure_classifier.py`

## 已落地设计对照

### 1. execution 是一等对象
- 已用 `DecisionExecutionRequest / BizExecutionRecord / GovernanceGateDecision / DecisionExecutionEnvelope / AuditSummary` 显式建模。
- `execution_status`、`gate_status`、`effective_risk_level`、`audit_status` 成为主语义字段。
- 工具层兼容字段只保留 `session_id / result / outcome / audit_event_count` 四个 alias。

### 2. governance gate 进入 orchestrator 主路径
- 编排器已拆成四段：
  1. planning / routing / authority / effective risk / gate 的纯内存阶段
  2. `PreExecutionPersistenceBarrier` 的集中落库与 fail-closed 阶段
  3. scenario 执行与 task / outcome 推进阶段
  4. envelope 组装与 audit 收束阶段
- 高风险返回 `denied` 并阻断真实 scenario 执行。
- 中风险返回 `degraded`，允许继续执行，但必须带审计语义。
- 低风险返回 `allowed`，按普通治理要求继续执行。

### 3. effective risk 改为 scenario profile 真相源
- `routing.trace.routing_context.risk.level` 仅作为基础信号保留。
- orchestrator 新增 scenario-profile 风险收束逻辑：
  - `tokencost -> low`
  - `travel / lifegoal / procurement -> medium`
  - `robotclaw -> high`
- 若调用方显式传入 `constraints.risk_level` 或 `constraints.risk.level`，则优先采用显式风险输入。
- 这解决了“`requires_audit = true` 被错误等同于 `high risk`”的问题，使 procurement 默认回到 `degraded` 而不是 `denied`。

### 4. fail-closed 在 scenario 之前发生
- `PreExecutionPersistenceBarrier` 在真实 scenario 前完成 session / execution / audit 的集中持久化。
- PostgreSQL 不可用、关键写入失败或 barrier 分类为基础设施故障时，主流程直接 fail-closed。
- 中风险 degraded 路径先把 `audit_status` 置为 `pending`，随后由主流程继续推进为 `persisted` 或 `failed`。

### 5. envelope-first 输出统一
- orchestrator 对外只返回 `DecisionExecutionEnvelope.to_tool_payload()`。
- 结果中统一包含：
  - `envelope.execution`
  - `envelope.plan`
  - `envelope.routing`
  - `envelope.authority`
  - `envelope.gate_decision`
  - `envelope.tasks`
  - `envelope.outcome`
  - `envelope.result`
  - `envelope.audit`

## 测试覆盖点
- `tests/test_biz/test_execution_contract.py`
- `tests/test_biz/test_payload_redactor.py`
- `tests/test_biz/test_failure_classifier.py`
- `tests/test_biz/test_persistence_barrier.py`
- `tests/test_biz/test_orchestrator.py`

重点覆盖：
- execution contract 的序列化与最小 alias
- payload 默认脱敏
- fail-closed 分类
- barrier 对 `pending / persisted / failed` 的推进
- procurement / robotclaw / tokencost / lifegoal 的 gate 语义
- scenario profile 对 effective risk 的修正
- operator trace 摘要进入 audit payload

## 剩余风险
- PostgreSQL 真实集成路径依赖 `VELARIS_TEST_POSTGRES_DSN`，未配置时相关集成用例会跳过。
- 当前 scenario profile 风险仍为编排层内联实现；后续若场景数量继续增加，建议再抽离为独立 `effective risk assessor` 组件。
