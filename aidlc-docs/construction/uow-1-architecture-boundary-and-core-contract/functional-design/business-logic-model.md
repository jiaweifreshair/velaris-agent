# Business Logic Model

## 目标

本设计针对 `UOW-1 - Architecture Boundary And Core Contract`，
用技术无关的方式定义以下业务逻辑：

1. `Velaris` 如何作为业务语义主体接收请求
2. `OpenHarness` 如何保持最小桥接边界
3. `execution` 如何成为一等对象
4. `governance gate` 如何在执行前消费授权与风险结果
5. `completion` 如何以主状态枚举为真相源，同时保留三层完成解释
6. `session` 与 `execution` 如何解耦但保持关联

## 业务主线模型

### 1. 标准化请求进入 Velaris

`OpenHarness` 只负责把外部调用转成标准化请求并提交给 `Velaris`。

它允许携带的信息只有：
- query
- payload
- constraints
- scenario hint
- session_id（可选）

它不负责：
- 定义 execution contract
- 定义 completion 语义
- 定义 resume 语义
- 判定 governance gate 是否放行

因此，`OpenHarness -> Velaris` 的最小桥接关系是：

- `OpenHarness` 提交 `DecisionExecutionRequest`
- `Velaris` 返回 `DecisionExecutionEnvelope`

## 2. Execution 作为一等对象

每次业务执行都必须先创建独立的 `BizExecutionRecord`。

它不是 task 的别名，也不是 outcome 的别名，而是业务执行的主对象。

### BizExecutionRecord 的职责
- 持有 execution_id
- 持有 session 引用（可选）
- 持有当前 execution_status
- 持有 completion 解释字段
- 持有 routing / authority / gate / scenario / result 的聚合引用
- 持有 resume 所需的最小上下文

### 关键关系
- 一个 session 可以关联多个 execution
- 一个 execution 可以脱离 session 单独恢复
- task / outcome / audit 都围绕 execution 展开
- task 是执行中的工作记录，不是 execution 主体
- outcome 是结果表达，不是 execution 主体

## 3. 执行主流程

### Phase A - Request Intake
1. 接收 `DecisionExecutionRequest`
2. 标准化 query / payload / constraints / scenario hint
3. 创建 `BizExecutionRecord`
4. 将 execution 状态置为 `created`

### Phase B - Planning And Boundary Binding
1. 生成 capability plan
2. 绑定 scenario
3. 生成 routing 决策
4. 生成 authority plan
5. 将 execution 状态推进为 `planned`

### Phase C - Effective Risk Assessment
1. `PolicyRouter` 给出基础 routing 风险上下文
2. `Scenario Profile` 根据具体场景上下文计算 `effective_risk_level`
3. 该风险等级成为 governance gate 的主输入
4. execution 状态推进为 `pending_gate`

这里采用“scenario profile 为主要风险判定层”的规则，
但允许复用 routing 输出作为基础风险信号，而不是完全忽略 routing。

### Phase D - Governance Gate
根据 `effective_risk_level` 做 gate 决策：

- **high risk** -> fail-closed
- **medium risk** -> 允许降级继续
- **low risk** -> 正常继续

#### high risk
- 直接阻断真实执行
- 返回 gate denied 结果
- execution 状态进入 `blocked`

#### medium risk
- 允许继续完整执行
- 必须强制记录审计
- 必须显式标记 `degraded_mode = true`
- completion 结果中必须体现“降级运行”语义

#### low risk
- 正常继续执行
- 审计要求由 governance 普通规则决定

### Phase E - Scenario Execution
1. 若 gate 放行，则进入 scenario 执行
2. 执行中状态置为 `running`
3. 生成 task / operator trace / intermediate facts
4. 聚合结果并生成 outcome 候选

### Phase F - Completion Derivation
1. 根据 execution 结果确定主状态枚举
2. 从主状态与运行结果中派生三层完成字段：
   - structural_complete
   - constraint_complete
   - goal_complete
3. 写回 `BizExecutionRecord`
4. 生成 `DecisionExecutionEnvelope`

## 4. Completion 混合模型

用户选择的 completion 模型为：
- 保留主状态枚举
- 保留三层完成字段
- 但以主状态枚举作为主真相源

### 主状态枚举
建议 Functional Design 中采用以下 execution_status：
- `created`
- `planned`
- `pending_gate`
- `blocked`
- `running`
- `completed`
- `partially_completed`
- `failed`

### 三层完成字段
- `structural_complete`
- `constraint_complete`
- `goal_complete`

### 主从关系
- `execution_status` 是主真相源
- 三层完成字段是解释性派生字段
- 三层字段不拥有独立覆盖主状态的权力
- 任意对 completion 的外部判断，都必须以主状态枚举为准

### 派生原则
- `completed` 通常意味着三层字段都为 true
- `partially_completed` 至少意味着 structural_complete 为 true，但约束或目标未全部满足
- `failed` 不要求 structural_complete 为 true
- `blocked` 表示执行未被允许进入真实运行阶段

## 5. Session 与 Execution 的关系

### 建模原则
- session 是对话 / 调用上下文容器
- execution 是业务执行实体
- session 可以没有 execution
- execution 可以引用 session，也可以独立恢复

### 业务含义
- 一个长 session 内可能发生多次业务执行
- execution resume 必须以 execution_id 为中心
- session resume 只负责恢复会话上下文，不自动等价于恢复某个 execution

## 6. Governance Gate 模型

### 输入
- routing decision
- authority plan
- effective risk level
- capability demand
- governance flags
- scenario execution intent

### 输出
`GovernanceGateDecision` 应至少表达：
- gate_status: `allowed | degraded | denied`
- effective_risk_level
- requires_forced_audit
- degraded_mode
- denial_reason / degradation_reason

### 消费位置
该 gate 必须在进入真实 scenario 执行前消费。
也就是说：
- 不能在 outcome 已生成后再补做 gate 判断
- 不能只把 authority 结果留在说明层而不参与执行放行

## 7. DecisionExecutionEnvelope

`Velaris` 对外返回的统一包络应聚合：
- execution
- plan
- routing
- authority
- gate_decision
- task view
- outcome view
- result view
- audit summary

### 为什么需要 envelope
因为：
- `OpenHarness` 不应理解 Velaris 内部对象间全部关系
- 但调用方仍需要一个统一、稳定、可扩展的结果面
- envelope 是桥接层的唯一公共 contract

## 8. 错误语义模型

### blocked
- gate 决策拒绝执行
- 不是系统异常
- 应作为业务阻断结果表达

### failed
- 已进入执行流程，但运行异常或关键约束失败
- 属于执行失败

### partially_completed
- 已生成有效结构结果
- 但未满足全部约束或目标
- 仍属于可返回结果

## 9. 本单元对后续单元的输出

UOW-1 Functional Design 输出以下后续约束：

1. UOW-2 必须围绕 `BizExecutionRecord` 来判断主状态、派生记录与恢复边界
2. UOW-2 必须把 session snapshot 与 execution snapshot 分离
3. UOW-3 必须以 `DecisionExecutionEnvelope` 作为最小运行闭环输出目标
4. 后续 NFR 设计要围绕 `blocked / degraded / failed / partially_completed / completed` 的一致语义做质量约束
