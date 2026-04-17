# 路由策略配置文档

## 配置文件
`config/routing-policy.yaml`

## 路由策略

| 策略 | 模式 | 运行时 | 自治度 | 所需能力 |
|------|------|--------|--------|----------|
| local_closed_loop | local | self | auto | read, reason |
| delegated_robotclaw | delegated | robotclaw | supervised | read, write, exec, audit |
| delegated_claude_code | delegated | claude_code | accept_edits | read, write, exec |
| hybrid_robotclaw_claudecode | hybrid | mixed | supervised | read, write, exec, audit |

## 停止策略画像

| 画像 | 触发行为 | 条件 | 适用场景 |
|------|----------|------|----------|
| strict_approval | stop | budget_exhausted, approval_timeout, authority_violation, high_risk_conflict | 高风险任务 |
| balanced | degrade | budget_exhausted, evidence_conflict, runtime_unhealthy | 默认 |
| fast_fail | stop | latency_exhausted, runtime_unhealthy | 低价值探索 |

## 路由规则 (按优先级降序)

| 规则 ID | 优先级 | 条件 | 路由策略 | 停止画像 |
|---------|--------|------|----------|----------|
| R001 | 1000 | risk.level ∈ [high, critical] | delegated_robotclaw | strict_approval |
| R004 | 950 | externalSideEffects=true AND writeCode=true | hybrid | strict_approval |
| R002 | 900 | writeCode=true AND complexity ∈ [medium, complex] | delegated_claude_code | balanced |
| R003 | 850 | requiresAuditTrail=true | delegated_robotclaw | strict_approval |
| R005 | 300 | risk ∈ [low, medium] AND simple AND no side effects | local_closed_loop | fast_fail |
| fallback | 0 | 无规则命中 | local_closed_loop | balanced |

## 路由上下文构建

路由器从 plan 中提取以下字段构建路由上下文：
- `scenario`: 场景名称
- `capabilityDemand.writeCode`: 是否需要写代码
- `capabilityDemand.externalSideEffects`: 是否有外部副作用
- `governance.requiresAuditTrail`: 是否需要审计
- `governance.approval_mode`: 审批模式
- `state.taskComplexity`: 任务复杂度 (simple/medium/complex)
- `risk.level`: 风险等级 (low/medium/high/critical)

## 支持的操作符
eq, ne, gt, gte, lt, lte, in, not_in
