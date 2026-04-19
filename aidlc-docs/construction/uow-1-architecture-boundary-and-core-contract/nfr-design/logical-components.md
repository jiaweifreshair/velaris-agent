# Logical Components

## 1. 文档目标

本文件基于 `UOW-1` 已批准的 Functional Design 与 NFR Requirements / NFR Design Answers，
定义支持这些非功能模式落地的逻辑组件。

这些组件是逻辑职责划分，不等于最终类名或模块名，
但会直接指导下一阶段 Code Generation 的目录、对象边界与职责拆分。

## 2. 逻辑组件总览

| 组件 | 类型 | 主要职责 |
| --- | --- | --- |
| `ExecutionRepository` | 持久化组件 | 管理 execution 主表写入、状态推进、恢复读取 |
| `SessionRepository` | 持久化组件 | 管理 session snapshot / reference 的 PostgreSQL 存储 |
| `TaskRepository` | 持久化组件 | 管理 task 显式结构记录 |
| `OutcomeRepository` | 持久化组件 | 管理 outcome 显式结构记录 |
| `AuditRepository` | 持久化组件 | 管理 audit 事件显式结构记录 |
| `PlanningGateAssembler` | 领域组装组件 | 在内存中完成 planning、routing、authority、effective risk、gate 草案 |
| `PreExecutionPersistenceBarrier` | 协调组件 | 在进入真实 scenario 前执行集中落库屏障 |
| `AuditStatusTracker` | 状态组件 | 维护 execution 上的 `audit_status` 推进 |
| `EnvelopeAssembler` | 输出组装组件 | 以 execution 为中心组装 `DecisionExecutionEnvelope` |
| `CompatibilityAliasAdapter` | 兼容组件 | 在最外层补少量兼容 alias |
| `PayloadRedactor` | 安全组件 | 对持久化内容、日志与对外输出统一脱敏 |
| `PersistenceFailureClassifier` | 错误分类组件 | 把数据库故障、治理阻断与业务失败区分成稳定语义 |

## 3. 组件详细说明

### 3.1 ExecutionRepository

#### 职责

- 创建 `BizExecutionRecord` 的 PostgreSQL 主记录
- 推进 `execution_status / gate_status / audit_status`
- 读取 execution 恢复所需核心上下文
- 持有 completion 三层派生字段与 resume_cursor

#### 关键输入

- `DecisionExecutionRequest` 的标准化结果
- `PlanningGateAssembler` 输出的 route / authority / gate 草案
- scenario 执行后的 result / completion 派生结果

#### 关键输出

- 已持久化的 execution 主记录
- execution 恢复快照

#### 约束

- execution 是所有 NFR 路径的主真相源
- `audit_status` 必须由该组件可查询且可推进

### 3.2 SessionRepository

#### 职责

- 把 session snapshot / reference 从文件链路迁移到 PostgreSQL 主线
- 维护 `session_id` 与 `execution_id` 的关联边界
- 支持“一个 session 关联多个 execution”

#### 约束

- session 是独立实体，不替代 execution
- session 恢复不自动等价于 execution 恢复

### 3.3 TaskRepository

#### 职责

- 管理 task 显式结构表
- 记录 task 的 runtime、role、objective、status、depends_on
- 支撑 execution 级别的工作视图

#### 约束

- task 不能定义主状态，只能解释 execution 局部进度
- 以 `execution_id` 为主关联键，必要时保留 `session_id` 辅助查询

### 3.4 OutcomeRepository

#### 职责

- 管理 outcome 显式结构表
- 持久化 `success / summary / selected_strategy / metrics / reason_codes`
- 支撑 envelope 中的 outcome view

#### 约束

- outcome 不是 execution 主体
- failure summary 与 result summary 都必须先经过脱敏再持久化

### 3.5 AuditRepository

#### 职责

- 持久化高风险同步审计与普通 / 补审计记录
- 按 `execution_id` 与 `session_id` 提供可追踪查询
- 支撑 `AuditSummary` 聚合

#### 约束

- 审计最终落点必须是 PostgreSQL
- 中风险补审计的最终成功与失败都必须能由该组件反映

### 3.6 PlanningGateAssembler

#### 职责

- 在内存中完成以下组装：
  - capability plan
  - routing
  - authority
  - effective risk
  - gate 草案
- 将这些中间结果整理为集中落库所需的标准化结构

#### 约束

- 该组件只负责“算”，不负责“决定是否真正执行”
- 真正的执行许可要由 `PreExecutionPersistenceBarrier` 成功后才成立

### 3.7 PreExecutionPersistenceBarrier

#### 职责

- 承接 `PlanningGateAssembler` 输出
- 在进入真实 scenario 前完成一次集中持久化屏障
- 若任一关键写入失败，则返回 `fail-closed`

#### 建议写入集合

- session 主记录 / reference
- execution 主记录
- gate 快照或 execution 中的 gate 列字段
- 高风险必须的前置审计记录

#### 约束

- 这是本单元最关键的 NFR 逻辑组件
- 其失败必须被 `PersistenceFailureClassifier` 稳定分类为基础设施故障，而不是业务失败

### 3.8 AuditStatusTracker

#### 职责

- 维护 `execution.audit_status`
- 在中风险 degraded 路径上表达 `pending / persisted / failed`
- 为恢复流程提供二次补审计锚点

#### 典型推进

- 高风险成功写前置审计后：`persisted`
- 中风险返回前未补成：`pending`
- 后续补成：`persisted`
- 多次补写后仍失败：`failed`

### 3.9 EnvelopeAssembler

#### 职责

- 以 execution 为中心聚合：
  - execution
  - routing
  - authority
  - gate_decision
  - task views
  - outcome view
  - result view
  - audit summary
- 形成正式 `DecisionExecutionEnvelope`

#### 约束

- envelope 是唯一主输出 contract
- 所有对外视图都应围绕 execution 组织，而不是平铺散列

### 3.10 CompatibilityAliasAdapter

#### 职责

- 在 envelope 组装完成后，补最小兼容 alias
- 本单元仅保留：
  - `session_id`
  - `result`
  - `outcome`
  - `audit_event_count`

#### 约束

- 不得重新把 `plan / routing / authority / task` 长期抬回顶层承诺
- 适配必须保持“薄”，不能在桥接层重新定义业务语义

### 3.11 PayloadRedactor

#### 职责

- 对持久化 payload、审计 payload、错误摘要、结构化日志与对外 envelope 统一执行脱敏
- 应用白名单 / 黑名单规则，确保默认不持久化原始敏感内容

#### 约束

- 该组件应在“落库前”和“对外返回前”都可复用
- 调试便利性不能覆盖最小暴露原则

### 3.12 PersistenceFailureClassifier

#### 职责

- 将异常统一映射为稳定错误语义：
  - `infrastructure_unavailable`
  - `gate_denied`
  - `execution_failed`
- 为 envelope / tool error / audit summary 提供一致错误分类

#### 约束

- 不允许仅返回原始异常文本作为唯一错误面
- 必须明确区分“数据库没写成”和“治理不允许执行”

## 4. 组件关系

### 主路径关系

1. `OpenHarness` 提交标准化请求
2. `PlanningGateAssembler` 在内存中生成 plan / routing / authority / effective risk / gate 草案
3. `PreExecutionPersistenceBarrier` 调用：
   - `SessionRepository`
   - `ExecutionRepository`
   - `AuditRepository`（高风险前置）
4. 若屏障成功，进入真实 scenario 执行
5. 执行中与执行后分别调用：
   - `TaskRepository`
   - `OutcomeRepository`
   - `AuditStatusTracker`
   - `AuditRepository`
6. 结束后由 `EnvelopeAssembler` 生成主 contract
7. `CompatibilityAliasAdapter` 补最小 alias
8. `PayloadRedactor` 在落库前 / 返回前做最终脱敏把关
9. `PersistenceFailureClassifier` 在异常路径统一归类错误语义

## 5. 逻辑时序（文本版）

```text
Step 1: OpenHarness -> Velaris 标准化请求
Step 2: PlanningGateAssembler 纯内存完成 planning / routing / authority / effective risk / gate 草案
Step 3: PreExecutionPersistenceBarrier 集中落库 execution / session / 必要 gate 与前置审计
Step 4: 若屏障失败 -> PersistenceFailureClassifier 输出 infrastructure_unavailable，并 fail-closed
Step 5: 若屏障成功 -> scenario 执行
Step 6: TaskRepository / OutcomeRepository / AuditRepository 写入执行结果
Step 7: AuditStatusTracker 推进 audit_status
Step 8: EnvelopeAssembler 组装 DecisionExecutionEnvelope
Step 9: CompatibilityAliasAdapter 补 session_id / result / outcome / audit_event_count
Step 10: PayloadRedactor 确认对外最小暴露后返回
```

## 6. 对下一阶段 Code Generation 的直接指导

1. 持久化实现需要从“最小 payload 表”转向“execution / session / task / outcome / audit 显式结构表”。
2. orchestrator 需要显式拆出：
   - planning / gate 纯内存阶段
   - pre-execution persistence barrier
   - envelope assembler
3. `biz_execute` 需要从“直接 json.dumps 平铺 payload”转为“envelope 主输出 + 极少数 alias”。
4. session 持久化要从 `openharness.services.session_storage` 的文件路径迁移到 PostgreSQL 主线。
5. 错误处理与审计推进要引入稳定状态字段，而不是继续依赖 `audit_event_count` 的单一数值表达。

## 7. 本阶段逻辑组件结论

本单元最终采用的逻辑组件组合是：

- 以 `ExecutionRepository` 为主真相源中心
- 以 `PreExecutionPersistenceBarrier` 作为 fail-closed 核心屏障
- 以 `AuditStatusTracker` 承接中风险补审计追踪
- 以 `EnvelopeAssembler + CompatibilityAliasAdapter` 完成 contract 收束与最小兼容
- 以 `PayloadRedactor + PersistenceFailureClassifier` 保证安全最小暴露与错误语义一致
