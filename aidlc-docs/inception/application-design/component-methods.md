# Component Methods

## 说明

这里定义的是高层方法签名与职责，不展开详细业务规则。
详细规则将在后续 `Functional Design` 阶段补充。

## 1. Velaris Decision Gateway

### `submit_decision_request(...)`
- **目的**: 接收外部业务请求并启动一次 Velaris 决策执行
- **输入**:
  - `query: str`
  - `payload: dict[str, Any]`
  - `constraints: dict[str, Any] | None`
  - `scenario: str | None`
  - `session_id: str | None`
- **输出**:
  - `DecisionExecutionResult`

### `build_response_payload(...)`
- **目的**: 统一输出给工具层/调用方的结果结构
- **输入**:
  - `execution`
  - `plan`
  - `routing`
  - `authority`
  - `task`
  - `outcome`
  - `result`
- **输出**:
  - `dict[str, Any]`

## 2. Goal-To-Plan Compiler

### `infer_scenario(query: str, scenario: str | None = None) -> str`
- **目的**: 识别业务场景

### `build_capability_plan(...) -> dict[str, Any]`
- **目的**: 生成结构化决策 plan

### `merge_stakeholder_weights(...) -> dict[str, float]`
- **目的**: 融合 stakeholder 影响权重

## 3. Governance Router

### `route(plan: dict[str, Any], query: str) -> RoutingDecision`
- **目的**: 根据治理策略生成路由决策

### `issue_plan(required_capabilities: list[str], governance: dict[str, Any]) -> AuthorityPlan`
- **目的**: 生成授权计划与能力令牌

### `validate_execution_gate(...) -> ValidationResult`
- **目的**: 校验执行是否满足治理前置条件
- **说明**: 这是本轮建议新增或补强的方法语义

## 4. Biz Execution Service

### `start_execution(...) -> BizExecutionRecord`
- **目的**: 创建一次业务执行对象

### `run_execution(...) -> BizExecutionResult`
- **目的**: 推进业务执行主流程

### `finalize_execution(...) -> BizExecutionRecord`
- **目的**: 写入完成态/失败态/部分完成态

### `resume_execution(execution_id: str) -> BizExecutionRecord | None`
- **目的**: 恢复业务执行对象

## 5. Execution State Contract

### `create_execution_record(...) -> BizExecutionRecord`
- **目的**: 构造统一执行对象

### `mark_structural_complete(...)`
- **目的**: 标记结构完成

### `mark_constraint_complete(...)`
- **目的**: 标记约束完成

### `mark_goal_complete(...)`
- **目的**: 标记目标完成

### `derive_outcome_snapshot(...) -> OutcomeRecord`
- **目的**: 生成结果快照

### `derive_audit_snapshot(...) -> dict[str, Any]`
- **目的**: 生成审计快照

## 6. Scenario Profile Layer

### `run_scenario(scenario: str, payload: dict[str, Any]) -> dict[str, Any]`
- **目的**: 分发执行具体场景

### `normalize_candidates(...) -> list[dict[str, Any]]`
- **目的**: 标准化候选项

### `score_candidates(...) -> list[dict[str, Any]]`
- **目的**: 生成评分结果

### `build_scenario_summary(...) -> str`
- **目的**: 生成面向结果层的摘要

## 7. Memory And Learning Service

### `save_decision(record: DecisionRecord) -> str`
- **目的**: 保存决策记录

### `recall_similar(...) -> list[DecisionRecord]`
- **目的**: 召回相似历史决策

### `compute_preferences(...) -> UserPreferences`
- **目的**: 更新个性化偏好

### `review_self_evolution(...) -> EvolutionReport`
- **目的**: 生成自进化复盘报告

## 8. Persistence And Recovery Service

### `build_decision_memory(...)`
- **目的**: 按配置构建决策记忆后端

### `build_task_ledger(...)`
- **目的**: 构建任务账本后端

### `build_outcome_store(...)`
- **目的**: 构建 outcome 后端

### `build_audit_store(...)`
- **目的**: 构建审计仓储

### `load_session_snapshot(...)`
- **目的**: 加载会话快照

### `load_execution_snapshot(...)`
- **目的**: 加载执行快照
- **说明**: 本轮建议新增或补强该语义
