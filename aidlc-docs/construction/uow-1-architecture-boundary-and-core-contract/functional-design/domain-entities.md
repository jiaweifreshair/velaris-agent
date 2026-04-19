# Domain Entities

## 说明

本文件定义 `UOW-1 - Architecture Boundary And Core Contract` 的核心领域对象。
这些对象是功能设计层的业务抽象，不等于最终代码类名，但会指导后续实现。

## 1. DecisionExecutionRequest

### 定义
从 `OpenHarness` 桥接进入 `Velaris` 的标准化请求。

### 核心字段
- query
- payload
- constraints
- scenario_hint
- session_id（可选）

### 职责
- 统一桥接层输入
- 隔离 `OpenHarness` 与 `Velaris` 内部对象

## 2. BizExecutionRecord

### 定义
业务执行的一等主实体，是 execution-level contract 的核心载体。

### 核心字段
- execution_id
- session_reference（可选）
- scenario
- execution_status
- structural_complete
- constraint_complete
- goal_complete
- degraded_mode
- gate_status
- created_at
- updated_at
- resume_cursor
- routing_snapshot
- authority_snapshot
- task_refs
- outcome_ref
- audit_ref

### 职责
- 作为 execution 真相源
- 聚合执行阶段的主状态
- 承载 completion 解释字段
- 承载 resume 所需核心上下文

## 3. SessionReference

### 定义
execution 对 session 的引用对象，而不是 execution 主体。

### 核心字段
- session_id
- binding_mode（例如 attached / detached）
- source_runtime

### 职责
- 说明 execution 来源于哪个会话上下文
- 支持 execution 与 session 解耦

## 4. ExecutionStatus

### 定义
execution 的主状态枚举。

### 建议取值
- created
- planned
- pending_gate
- blocked
- running
- completed
- partially_completed
- failed

### 职责
- 作为 completion 判断的主真相源
- 对外提供统一状态判断基础

## 5. CompletionDescriptor

### 定义
对 execution 完成程度的解释性描述对象。

### 核心字段
- structural_complete
- constraint_complete
- goal_complete
- explanation

### 职责
- 为 execution_status 提供解释
- 不独立替代 execution_status

## 6. RoutingSnapshot

### 定义
execution 在 planning / routing 阶段绑定的路由快照。

### 核心字段
- selected_strategy
- runtime
- autonomy
- base_risk_level
- stop_profile
- reason_codes

### 职责
- 保留 routing 决策上下文
- 为 effective risk 计算提供基础输入

## 7. AuthorityPlanSnapshot

### 定义
execution 绑定的授权与能力计划快照。

### 核心字段
- approvals_required
- required_capabilities
- capability_tokens

### 职责
- 提供 gate 决策输入
- 保留授权快照供审计与恢复使用

## 8. EffectiveRiskAssessment

### 定义
由 scenario profile 主要判定的有效风险结果。

### 核心字段
- base_risk_level
- effective_risk_level
- assessed_by
- rationale

### 职责
- 将 routing 给出的基础风险与场景上下文结合
- 作为 governance gate 的主要风险输入

## 9. GovernanceGateDecision

### 定义
执行门对 execution 是否可以进入真实执行的判定结果。

### 核心字段
- gate_status: `allowed | degraded | denied`
- effective_risk_level
- requires_forced_audit
- degraded_mode
- reason

### 职责
- 明确 execution 是否可进入 scenario 执行
- 明确是否处于 degraded mode
- 明确拒绝或降级原因

## 10. TaskView

### 定义
execution 关联的工作记录视图。

### 核心字段
- task_id
- role
- runtime
- task_status
- objective

### 职责
- 表达执行中的工作进展
- 不替代 execution 主实体

## 11. OutcomeView

### 定义
execution 关联的结果视图。

### 核心字段
- success
- selected_strategy
- summary
- metrics
- reason_codes

### 职责
- 对外表达业务结果
- 不替代 execution 主实体

## 12. AuditSummary

### 定义
execution 关联的审计摘要。

### 核心字段
- audit_required
- audit_event_count
- degraded_mode
- last_event

### 职责
- 对外表达审计状态
- 为 degraded / denied / failed 结果提供可追踪性

## 13. DecisionExecutionEnvelope

### 定义
`Velaris` 对外返回的统一执行包络。

### 核心字段
- execution: BizExecutionRecord
- plan
- routing: RoutingSnapshot
- authority: AuthorityPlanSnapshot
- gate_decision: GovernanceGateDecision
- tasks: list[TaskView]
- outcome: OutcomeView | None
- result
- audit: AuditSummary

### 职责
- 作为 `Velaris` 唯一公共输出 contract
- 为 `OpenHarness` 提供稳定、统一、可扩展的结果面

## 实体关系

### 关系 1
- 一个 `DecisionExecutionRequest` 触发一个 `BizExecutionRecord`

### 关系 2
- 一个 `BizExecutionRecord` 可选关联一个 `SessionReference`
- 一个 `SessionReference` 可以被多个 `BizExecutionRecord` 引用

### 关系 3
- 一个 `BizExecutionRecord` 必须绑定一个 `RoutingSnapshot`
- 一个 `BizExecutionRecord` 必须绑定一个 `AuthorityPlanSnapshot`
- 一个 `BizExecutionRecord` 必须绑定一个 `GovernanceGateDecision`

### 关系 4
- 一个 `BizExecutionRecord` 可以关联多个 `TaskView`
- 一个 `BizExecutionRecord` 最多关联一个主 `OutcomeView`
- 一个 `BizExecutionRecord` 最多关联一个主 `AuditSummary`

### 关系 5
- `DecisionExecutionEnvelope` 以 `BizExecutionRecord` 为中心聚合全部视图

## 关键建模结论

1. execution 是主实体，task / outcome / audit 是关联视图
2. execution_status 是主状态，CompletionDescriptor 是解释性派生对象
3. routing 风险不是最终真相，Scenario Profile 产生的 EffectiveRiskAssessment 才是 gate 主要输入
4. `OpenHarness` 不拥有这些实体的定义权，只消费 envelope
