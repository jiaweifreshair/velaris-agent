# Unit Of Work

## 说明

本文件将 `Phase 1：默认路径收束 / 最小可信闭环` 拆分为 3 个最小变更单元。

这里的 Unit of Work 不是独立部署服务，而是**可顺序推进、可独立判断完成、可交付到后续 Functional Design / Code Generation 的最小变更单元**。

本次拆分遵循用户确认过的原则：

- 优先做最小但干净且可运行的收束
- 优先统一默认路径语义，而不是扩展平台能力
- 优先锁定边界与 contract，再落到状态链与运行闭环
- 文档同步与验证设计只保留最小必要部分，不再扩成独立大单元

## 总体拆分结果

| Unit | 名称 | 核心目标 | 主要改动边界 |
|------|------|----------|--------------|
| UOW-1 | Architecture Boundary And Core Contract | 锁定 `Velaris` / `OpenHarness` 边界与 execution/state/completion/resume 核心 contract | `src/velaris_agent/velaris/*` 的语义边界、入口层与治理层接口 |
| UOW-2 | Default State Chain And Persistence Unification | 统一默认状态链、持久化角色与恢复边界 | `src/velaris_agent/persistence/*`、`task/outcome/audit`、`session_storage` |
| UOW-3 | Minimal Runtime Convergence | 把前两者落到最小可运行闭环，收束 orchestrator 与工具入口 | `src/velaris_agent/velaris/orchestrator.py`、`src/openharness/tools/biz_execute_tool.py`、最小必要文档 |

## UOW-1 - Architecture Boundary And Core Contract

### 目标

- 明确 `Velaris` 是整体业务决策架构主体
- 明确 `OpenHarness` 是运行时 Harness 基座
- 明确 `execution / state / completion / resume` 四类核心语义由 `Velaris` 主导定义
- 明确“会话”不是“业务执行”，二者只存在引用关系，不是同义关系

### 为什么先做

如果边界没有先钉住，后续对默认状态链、持久化和工具面的收束都会重新陷入“谁才是语义主体”的混乱。
因此它必须作为第一单元。

### 主要范围

- 决策入口层如何接住来自 `OpenHarness` 的业务请求
- 治理层如何从“说明性授权”走向“可执行前置门”
- 执行主语义由谁定义
- 完成语义与恢复语义由谁定义
- 最小桥接边界是什么，哪些信息只能留在 `Velaris`

### 建议主要改动对象

- `src/velaris_agent/velaris/orchestrator.py`
- `src/velaris_agent/velaris/router.py`
- `src/velaris_agent/velaris/authority.py`
- 新增或收束的 execution/state contract 文档化对象（文件名待 Functional Design 确认）
- `src/openharness/tools/biz_execute_tool.py` 的入口桥接语义

### 关键设计问题

1. execution-level 对象是否显式建模为独立 record / payload contract
2. completion 是否需要分层表达为结构完成、约束完成、目标完成
3. resume contract 是否必须显式拆分为 session resume 与 execution resume
4. `OpenHarness -> Velaris` 的桥接层是否只传递标准化请求与结果，而不承载内部执行语义

### 最小交付物

- 一个清晰的边界定义
- 一套 execution/state/completion/resume 的最小术语表
- 一份对 `orchestrator` 入口职责的收束说明
- 一份对 `authority` / `governance` 消费位置的说明

### 最小完成标准

- 能明确回答“谁定义 execution-level 语义”
- 能明确回答“谁拥有 completion / resume 语义”
- 能明确回答“会话 ID 与 execution ID 是否等同”
- 能明确回答“`OpenHarness` 最小只需要知道什么”

### 非目标

- 不在本单元定义完整测试矩阵
- 不在本单元扩展全部工具入口
- 不在本单元做大范围 README 清理
- 不在本单元改造长期学习与偏好系统

### 向后续单元的输出

UOW-1 输出的是“语义主语”，它直接约束 UOW-2 中主状态与派生状态如何划分，以及 UOW-3 中运行时返回结构如何收敛。

## UOW-2 - Default State Chain And Persistence Unification

### 目标

- 统一默认路径下的状态真相源表达
- 明确 `task / outcome / audit / memory / snapshot` 的职责分工
- 明确默认 durable 路径与 PostgreSQL 增强路径的关系
- 明确 `session resume != execution resume`

### 为什么它是第二单元

用户明确强调“持久化应该统一”。
但如果没有 UOW-1 提供的 contract 主语义，就无法判断哪些对象是主状态、哪些只是派生记录。
因此它必须紧跟在边界 contract 之后。

### 主要范围

- 默认路径中什么对象是主状态
- 什么对象只是结果记录或审计记录
- 什么状态必须跨重启恢复
- 什么状态允许从持久化或运行结果重建
- PostgreSQL 增强路径如何只扩容、不补默认语义

### 建议主要改动对象

- `src/velaris_agent/persistence/factory.py`
- `src/velaris_agent/velaris/task_ledger.py`
- `src/velaris_agent/velaris/outcome_store.py`
- `src/velaris_agent/persistence/postgres_runtime.py`
- `src/velaris_agent/persistence/postgres_memory.py`
- `src/openharness/services/session_storage.py`

### 关键设计问题

1. 默认路径下 `DecisionMemory` 是否仍只是长期记忆，而不是运行态真相源
2. `TaskLedger` / `OutcomeStore` / `AuditStore` 在默认路径下分别承担什么角色
3. execution snapshot 是否需要独立于 session snapshot 表达
4. PostgreSQL 开启后，哪些语义保持不变，哪些只是后端增强

### 最小交付物

- 一份默认状态链角色表
- 一份恢复边界表（session / execution / outcome / audit）
- 一份默认 durable 路径与增强路径关系说明
- 一份 persistence 工厂层切换点说明

### 最小完成标准

- 能明确回答“默认路径下什么是主状态”
- 能明确回答“哪些状态必须可恢复，哪些可重建”
- 能明确回答“为什么 session resume 不能等同 execution resume”
- 能明确回答“为什么 PostgreSQL 不是默认语义的必要前提”

### 非目标

- 不引入新的存储中间件
- 不把 PostgreSQL 提升为默认真相源前提
- 不重构长期学习、偏好学习或自进化机制
- 不展开完整故障恢复测试设计

### 向后续单元的输出

UOW-2 输出的是“状态与恢复边界”，它决定 UOW-3 中 `orchestrator` 输出结构、`biz_execute` 返回内容以及最小文档同步的核心口径。

## UOW-3 - Minimal Runtime Convergence

### 目标

- 将前两个单元确定的 contract 与状态链落到最小可运行闭环
- 收束 `VelarisBizOrchestrator` 的输入 / 输出语义
- 收束 `biz_execute` 的工具面输出
- 同步最小必要文档，避免对外叙事继续跑偏

### 为什么它是第三单元

在边界 contract 和默认状态链统一之前，运行时闭环无法稳定；
在二者锁定之后，才值得把最小可运行调用面收敛起来。

### 主要范围

- `VelarisBizOrchestrator` 输出结构是否体现 execution-level 语义
- `biz_execute` 是否只是桥接标准化请求 / 响应
- 失败态、部分完成态与成功态是否有一致表达
- 需要同步哪些最小文档，才能不再把 `Velaris` 说成附属模块

### 建议主要改动对象

- `src/velaris_agent/velaris/orchestrator.py`
- `src/openharness/tools/biz_execute_tool.py`
- `README.md` 中最小必要定位段落
- `aidlc-docs/` 中与本轮收束直接相关的文档

### 关键设计问题

1. 最小闭环返回结构里是否需要显式 execution record
2. task / outcome / result / audit_event_count 之间如何避免语义重叠
3. 工具层错误输出是否应显式暴露 execution 失败语义
4. 哪些文档必须同步，哪些可以延后

### 最小交付物

- 一份最小运行闭环输入/输出收束说明
- 一份工具层桥接语义说明
- 一份最小文档同步清单

### 最小完成标准

- 能明确回答“最小闭环入口返回什么结构才算一致”
- 能明确回答“工具层与业务层的边界在哪里”
- 能明确回答“本轮必须同步哪些文档，哪些可以后续补强”

### 非目标

- 不扩展更多业务场景工具
- 不在本单元展开完整验证矩阵
- 不把 README、设计文档、计划文档全部重写一遍
- 不在本单元直接进入 Code Generation

## 单元整体完成判据

这 3 个工作单元整体完成后，应满足以下条件：

1. `Velaris` / `OpenHarness` 的语义边界稳定
2. 默认状态链、恢复边界与持久化角色稳定
3. 最小运行闭环已经有清晰的收口入口
4. 后续 Functional Design 可以围绕这 3 个单元逐一展开，而不再需要重新拆边界

## 为什么不继续拆得更细

本轮用户明确要求：

- 保持精简
- 最快实现
- 最小但干净且可运行

因此不再把“工具面”“验证设计”“文档对齐”单独扩成更多单元，
而是将其折叠进最小核心主线中处理。
