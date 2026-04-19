# Business Rules

## 说明

本文件定义 `UOW-1 - Architecture Boundary And Core Contract` 的业务规则、约束逻辑与状态规则。

## BR-1 边界主语规则
- `Velaris` 是业务执行语义主体
- `OpenHarness` 是运行时桥接基座
- 任何 execution / completion / resume contract 都由 `Velaris` 定义

## BR-2 最小桥接规则
- `OpenHarness` 只能提交标准化请求并接收标准化执行包络
- `OpenHarness` 不持有 execution contract 的定义权
- `OpenHarness` 不直接推断内部 completion / resume 逻辑

## BR-3 Execution 创建规则
- 每次业务执行都必须创建独立 `BizExecutionRecord`
- execution_id 必须独立存在，不能等同 task_id
- execution_id 默认也不能等同 session_id

## BR-4 Session 关联规则
- session_id 在 execution 中属于可选引用字段
- 一个 session 可关联多个 execution
- execution 可在缺失活跃 session 的情况下单独恢复

## BR-5 主状态真相源规则
- `execution_status` 是 completion 语义的主真相源
- 任何对外状态判断都必须先看 `execution_status`
- `structural_complete / constraint_complete / goal_complete` 仅作为解释性派生字段

## BR-6 Completion 派生规则
- `completed` 必须可派生为结构、约束、目标全部完成
- `partially_completed` 必须表示至少存在可返回结构，但并非所有目标满足
- `failed` 必须表示执行未成功完成，不要求存在结构化结果
- `blocked` 必须表示真实执行未开始即被 gate 阻断

## BR-7 Planning 完成规则
- capability plan、routing、authority 未准备完成前，不得进入 governance gate
- execution 在 planning 阶段只能处于 `created` 或 `planned`

## BR-8 风险判定主规则
- `Scenario Profile` 是 effective risk level 的主要判定层
- `PolicyRouter` 的 risk.level 作为基础信号输入，可被 scenario 上下文修正
- governance gate 必须消费 effective risk level，而不是只消费 routing 原始风险

## BR-9 高风险阻断规则
- effective risk level = high 时，默认 fail-closed
- 高风险场景不能直接进入真实 scenario 执行
- 必须返回明确 denial reason

## BR-10 中风险降级规则
- effective risk level = medium 时，允许降级继续
- 降级继续不阻止真实执行
- 但必须强制标记 `degraded_mode = true`
- 必须强制记录审计
- completion 解释中必须保留 degraded 语义

## BR-11 低风险放行规则
- effective risk level = low 时，允许正常进入执行
- 是否审计由普通 governance 要求决定

## BR-12 强审计规则
- 只要 gate 决策为 `degraded`，就必须强制记录审计
- 审计失败不能悄悄吞掉 degraded 语义
- 如果业务定义要求“必须审计”，则审计不可用时必须阻断最终执行

## BR-13 Authority 消费规则
- authority plan 不能只作为说明性结果返回
- governance gate 必须消费 required capabilities 与 approval-sensitive capabilities
- 对 capability token 的校验必须发生在真实 scenario 执行之前

## BR-14 Gate 优先级规则
- gate 判断必须在 scenario 执行之前
- 不允许在 scenario 完成后补做 gate 以倒推是否允许执行
- 一旦进入 scenario 执行，即视为 gate 已放行或降级放行

## BR-15 Task 依附规则
- task 是 execution 内部工作记录
- task 不能替代 execution 主实体
- task 状态变化只能解释 execution 的局部进展，不能单独定义 completion 语义

## BR-16 Outcome 依附规则
- outcome 是 execution 结果视图，不是 execution 主体
- outcome 可以缺失而 execution 已存在
- 失败 execution 也可以有 outcome 错误摘要，但仍不改变 execution 主体地位

## BR-17 Resume 语义分离规则
- session resume 与 execution resume 必须显式分离
- session resume 只恢复会话上下文
- execution resume 必须围绕 execution_id 恢复业务执行状态
- session 被恢复不代表某个 execution 自动被恢复

## BR-18 错误分类规则
- `blocked` 属于业务阻断，不等同系统异常
- `failed` 属于执行失败，可包含异常原因
- `partially_completed` 属于有效但不完整的业务结果
- 这三者在 envelope 中必须可区分

## BR-19 Envelope 输出规则
- `Velaris` 对外必须返回统一 `DecisionExecutionEnvelope`
- envelope 中 execution 为主对象
- task / outcome / result / audit 作为 execution 的关联视图输出

## BR-20 兼容性规则
- 本单元虽然引入显式 execution 主体，但不能破坏现有 `biz_execute` 的最小调用方式
- 兼容性应通过 envelope 扩展达成，而不是通过继续让桥接层承载内部语义
