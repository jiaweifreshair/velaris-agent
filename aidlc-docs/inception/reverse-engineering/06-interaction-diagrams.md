# 交互图 — 业务事务跨组件实现

## 1. 完整决策闭环 (biz_execute)

```
用户
 │
 ▼
QueryEngine ──────────────────────────────────────────────────────
 │  submit_message("帮我选 offer")
 │
 ▼
BizExecuteTool
 │  execute(query, payload)
 │
 ▼
VelarisBizOrchestrator.execute()
 │
 ├─► build_capability_plan(query)          [BizEngine L1]
 │     └─ infer_scenario() → "career"
 │     └─ 生成 plan: {scenario, capabilities, weights, governance}
 │
 ├─► PolicyRouter.route(plan, query)       [Router L2]
 │     └─ 加载 routing-policy.yaml
 │     └─ 构建路由上下文 (risk, complexity, capabilities)
 │     └─ 匹配规则 → RoutingDecision
 │
 ├─► AuthorityService.issue_plan()         [Authority L2]
 │     └─ 检查敏感能力 (write/exec/audit)
 │     └─ 签发 CapabilityToken
 │
 ├─► TaskLedger.create_task()              [Ledger L4]
 │     └─ 状态: queued → running
 │
 ├─► run_scenario("career", payload)       [BizEngine L3]
 │     └─ _run_lifegoal_scenario()
 │     └─ score_options(options, weights)
 │     └─ 返回推荐 + 评分明细
 │
 ├─► TaskLedger.update_status("completed") [Ledger L4]
 │
 └─► OutcomeStore.record()                 [Outcome L4]
       └─ 记录 session_id, scenario, success, metrics
```

## 2. 偏好学习闭环

```
save_decision 被调用
 │
 ▼
DecisionMemory.save(record)
 │  └─ 写 records/dec-xxxx.json
 │  └─ 更新 index.jsonl
 │
 ▼
[每 10 条触发]
SelfEvolutionEngine.review()
 │
 ├─► DecisionMemory.list_by_user()
 │     └─ 获取最近 N 条决策
 │
 ├─► _compute_accept_rate()
 │     └─ user_choice.id == recommended.id 的比例
 │
 ├─► _compute_avg_feedback()
 │     └─ 平均满意度
 │
 ├─► _compute_drift()
 │     └─ 用户选择 vs 推荐的维度差值
 │
 └─► _build_actions()
       └─ 生成优化动作 (adjust_weight / improve_explanation / ...)
       └─ 持久化报告到 ~/.velaris/evolution/reports/
```

## 3. 个性化权重获取

```
recall_preferences 被调用
 │
 ▼
PreferenceLearner.compute_preferences(user_id, scenario)
 │
 ├─► DecisionMemory.list_by_user()
 │     └─ 获取历史决策
 │
 ├─► _learn_weights(records, scenario)
 │     └─ 遍历有反馈的决策
 │     └─ 提取 chosen vs recommended 的维度差异
 │     └─ 贝叶斯先验 + 指数衰减加权
 │     └─ 归一化
 │
 ├─► _detect_patterns(records)
 │     └─ 识别行为模式 ("偏好最低价" 等)
 │
 └─► 返回 UserPreferences
       └─ weights, common_patterns, known_biases, satisfaction
```

## 4. 策略路由决策

```
PolicyRouter.route(plan, query)
 │
 ├─► _load_policy(routing-policy.yaml)
 │
 ├─► _build_routing_context(plan, query)
 │     └─ 提取: scenario, writeCode, externalSideEffects
 │     └─ 推断: taskComplexity, riskLevel
 │
 ├─► 遍历 rules (按 priority 降序)
 │     └─ _matches(rule.when, context)
 │     └─ 第一个匹配的规则胜出
 │
 ├─► 未匹配 → 使用 fallback
 │
 └─► 返回 RoutingDecision
       └─ selected_strategy, runtime, required_capabilities
       └─ stop_profile, confidence, reason_codes
```

## 5. 商旅推荐场景

```
travel_recommend 被调用
 │
 ▼
_run_travel_scenario(payload)
 │
 ├─► _extract_budget_from_query()
 │     └─ 从自然语言提取预算约束
 │
 ├─► _extract_route_from_query()
 │     └─ 提取出发地/目的地
 │
 ├─► 遍历 options
 │     └─ _build_travel_option() → 构建标准化选项
 │     └─ _score_travel_option_route() → 路线匹配评分
 │
 ├─► score_options(options, weights)
 │     └─ 多维加权评分
 │
 └─► 返回排序推荐 + 评分明细 + 解释
```

## 6. 技能沉淀闭环

```
QueryEngine.submit_message()
 │
 ├─► run_query() → 流式推理 + 工具调用
 │     └─ 统计 tool_calls_this_turn
 │
 └─► _maybe_schedule_skill_review()
       │  (tool_calls >= skill_review_interval)
       │
       ▼
       _run_background_skill_review() [后台异步]
         └─ 只暴露 skill + skill_manage 工具
         └─ 注入 SKILL_REVIEW_PROMPT
         └─ LLM 自主决定是否创建/更新技能
         └─ 权限: FULL_AUTO (无需用户确认)
```

## 7. 利益相关者对齐

```
build_capability_plan(query, stakeholder_map=...)
 │
 ├─► _build_stakeholder_context(stakeholder_map)
 │     └─ 提取所有利益相关者的权重和约束
 │
 ├─► _merge_stakeholder_weights(stakeholders, base_weights)
 │     └─ 按影响力加权融合各方权重
 │
 └─► plan 中包含融合后的权重
       └─ 后续评分使用融合权重
```
