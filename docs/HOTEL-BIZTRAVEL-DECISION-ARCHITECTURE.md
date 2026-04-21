# 酒店用户 / 商旅用户场景下的 Velaris-Agent 目标态架构

## 1. 结论

这条路成立，但成立的前提不是“再做一个会聊天的旅行助手”，而是把 `velaris-agent` 明确收敛为一个**共享决策内核**：

- 对酒店用户：输出“适合这个住客的推荐组合与决策依据”，帮助酒店把礼宾、交通、附加服务做成智能化会员体验。
- 对商旅用户：输出“在预算、时间、偏好、企业策略之间的最优 bundle”，帮助用户在复杂出行链路里更快确认。
- 对平台层：输出“结构化排序结果 + 可审计依据 + 回写闭环”，而不是把下单、支付、售后全部塞进 `velaris-agent`。

一句话定义：

`velaris-agent = 面向酒店用户与商旅用户的多场景联合决策内核，而不是强运营履约系统`

## 2. 为什么这条路成立

### 2.1 成立点

这类产品真正可卖的，不是单一聊天能力，而是下面三件事同时成立：

1. 你掌握了一部分酒店、航司、本地服务的供给关系，可以把能力 skill 化。
2. 用户侧确实存在高价值、低容错、跨多个场景的决策需求，例如“航班 + 酒店 + 接送 + 鲜花 + 咖啡”。
3. 平台能解释“为什么这样推荐”，而不是只给一个黑盒答案。

### 2.2 不成立的边界

如果把目标理解成“纯 C 端订阅聊天机器人”，这条路会很弱，因为：

- 商旅是低频高价值，不是高频娱乐型订阅。
- 用户愿意为“省下确认成本、减少误机/误约风险、提升体验”付费，而不是只为“能聊天”付费。
- 供给侧签约和组织策略才是壁垒，聊天 UI 不是。

## 3. 当前仓库的短板

基于当前实现，`velaris-agent` 还更接近“单场景评分器”，核心短板有四个：

1. `src/velaris_agent/biz/engine.py` 仍以 `travel / tokencost / robotclaw / procurement` 的场景分支为主，`travel` 只做平面候选排序，不做跨类 bundle 联合决策。
2. `src/velaris_agent/decision/operators/registry.py` 当前只把 `procurement` 接入 decision graph，其余场景仍走 legacy path。
3. `DecisionMemory + PreferenceLearner` 主要学习用户个人偏好，还没有把“酒店租户策略 / 企业商旅策略 / 会员权益策略”作为一等输入持续参与排序。
4. 编排与治理链条已经有了，但“可行性过滤”和“解释生成”还没有稳定承接酒店用户 / 商旅用户这类多场景联合决策。

## 4. 目标定位

优化后的 `velaris-agent` 只做三件事：

1. **接收标准化候选集**：来自 `velaris-platform-agent`、领域 agent、supplier skill 或外部协议层。
2. **做确定性过滤 + 联合排序**：先剔除时间窗、预算、顺路性、企业策略不满足的组合，再做个性化排序。
3. **产出结构化决策依据**：必须解释推荐原因、未选原因、权衡项和不确定性。

不做的事：

- 不直接承接前端 UI。
- 不直接做支付和售后。
- 不直接变成 supplier orchestration 大总管。

## 5. 目标态分层

### 5.1 上游入口层

上游依然由 `velaris-platform-agent` 或其他 Chat Surface 承接：

- 酒店会员礼宾 Chat
- 商旅订阅 Chat
- 企业差旅入口

这一层负责：

- 接收自然语言
- 维护 session / user / tenant
- 拆分领域任务
- 采集 `top-k candidates`

### 5.2 决策输入层

`velaris-agent` 首先把上游输入编译成稳定决策契约：

- `GoalContext`
- `TenantPolicyContext`
- `UserPreferenceContext`
- `CapabilityCandidateSet`
- `BundleConstraintSet`

这一层建议拆成：

- `GoalTenantCompiler`
  作用：把酒店租户策略、商旅组织策略、会员等级、预算、时间窗统一归档。
- `CandidateContractNormalizer`
  作用：把航班、酒店、咖啡、鲜花、接送等异构候选统一为可比较结构。
- `PolicyOverlay`
  作用：把组织硬约束、酒店权益、品牌策略覆盖到候选与权重上。

### 5.3 决策核心层

这是本次优化的重点，建议把现有 procurement graph 机制升级成共享 decision graph。

核心模块：

- `Feasibility / Bundle Planner`
  作用：先做硬约束过滤，例如 ETA、营业时间、机场出发时间、绕路上限、预算、租户禁配规则。
- `Decision Graph`
  作用：执行统一 operator 链，包括意图、归一化、可行性、Pareto frontier、operating point、bias audit、explanation。
- `Decision Basis Builder`
  作用：把排序结果整理成可解释的结构化依据，供平台直接渲染。

这里最关键的原则是：

- **硬约束先过滤**
- **软偏好后排序**
- **输出必须可解释**

### 5.4 治理与学习层

当前仓库已经有这部分基础能力，目标态是把它们从“附属能力”提升为“决策主链输入”：

- `PolicyRouter + AuthorityService`
  负责风险、写操作、副作用和审计门槛。
- `DecisionMemory + PreferenceLearner`
  负责用户历史选择、推荐接受率、偏好学习。
- `OrgPolicy / Tenant Policy`
  负责酒店品牌策略、企业商旅约束、会员权益。
- `OutcomeStore + TaskLedger`
  负责结果回写、执行追踪、KPI 归档、决策 trace。

## 6. 推荐输入输出契约

### 6.1 同类排序：`domain_rank`

适用场景：

- 多个酒店里选哪家
- 多个航班里选哪班
- 多个花店里选哪家

输入要点：

- `domain`
- `service_type`
- `request_context`
- `hard_constraints`
- `candidates[]`

输出要点：

- `selected_candidate_id`
- `ranked_candidates[]`
- `score_breakdown`
- `hard_constraint_report`
- `why_selected`
- `why_not_others`

### 6.2 跨类联合排序：`bundle_rank`

适用场景：

- 先去花店还是先取咖啡
- 航班 + 酒店 + 接送 + 增值服务如何组合
- 哪个 bundle 对酒店会员或商旅用户最优

输入要点：

- `bundle_candidates[]`
- `sequence_steps`
- `aggregates.total_price`
- `aggregates.total_eta_minutes`
- `aggregates.detour_minutes`
- `aggregates.time_slack_minutes`
- `hard_constraint_report`

输出要点：

- `selected_bundle_id`
- `ranked_bundles[]`
- `score_breakdown`
- `tradeoffs`
- `uncertainty_flags`
- `explanation_text`
- `decision_trace_id`

## 7. 对当前代码的增量改造建议

### 7.1 继续复用的模块

- [src/velaris_agent/velaris/orchestrator.py](/Users/apus/Documents/UGit/velaris-agent/src/velaris_agent/velaris/orchestrator.py)
- [src/velaris_agent/velaris/router.py](/Users/apus/Documents/UGit/velaris-agent/src/velaris_agent/velaris/router.py)
- [src/velaris_agent/memory/decision_memory.py](/Users/apus/Documents/UGit/velaris-agent/src/velaris_agent/memory/decision_memory.py)
- [src/velaris_agent/memory/preference_learner.py](/Users/apus/Documents/UGit/velaris-agent/src/velaris_agent/memory/preference_learner.py)
- [src/velaris_agent/decision/graph.py](/Users/apus/Documents/UGit/velaris-agent/src/velaris_agent/decision/graph.py)
- [src/velaris_agent/decision/operators/](/Users/apus/Documents/UGit/velaris-agent/src/velaris_agent/decision/operators)

### 7.2 需要收敛或升级的模块

1. [src/velaris_agent/biz/engine.py](/Users/apus/Documents/UGit/velaris-agent/src/velaris_agent/biz/engine.py)
   当前问题：场景分支太重，`travel` 仍是单场景直接评分。

   建议：

   - 保留 `build_capability_plan()` 做场景识别与治理规划。
   - 把 `travel` 的排序逻辑逐步迁移到 decision graph。
   - 新增 `hospitality_bundle` / `business_trip_bundle` 这类共享 graph 场景，而不是继续堆 if/else。

2. [src/velaris_agent/decision/operators/registry.py](/Users/apus/Documents/UGit/velaris-agent/src/velaris_agent/decision/operators/registry.py)
   当前问题：只注册了 `procurement`。

   建议：

   - 新增 `travel` 的 graph 注册。
   - 新增 `hospitality_bundle` 的 graph 注册。
   - 让 `option_discovery -> normalization -> feasibility -> operating_point_selector -> explanation` 成为统一主链。

3. `DecisionMemory` 相关模型
   当前问题：更像“用户偏好记忆”，还不是“用户 + 租户 + 组织”的三方决策上下文。

   建议：

   - 为 `DecisionRecord` 增补 `tenant_id`、`bundle_id`、`decision_basis`、`sequence_steps`、`rejected_bundle_ids`。
   - 为 `OrgPolicy` 增补酒店权益、企业差旅规则、供应商优先级。

### 7.3 建议新增的目录与模块

建议新增下面这些文件，把“输入标准化”“联合规划”“解释生成”从 `biz/engine.py` 里剥离出来：

- `src/velaris_agent/decision/contracts.py`
  作用：定义 `CapabilityCandidateSet`、`BundleDecisionRequest`、`BundleDecisionResponse`。
- `src/velaris_agent/decision/candidate_normalizer.py`
  作用：统一酒店、航司、本地服务候选结构。
- `src/velaris_agent/decision/bundle_planner.py`
  作用：组合候选、生成 `bundle_candidates[]`。
- `src/velaris_agent/decision/feasibility.py`
  作用：做 ETA、时间窗、绕路、预算、品牌策略等硬约束过滤。
- `src/velaris_agent/decision/policy_overlay.py`
  作用：把组织与租户策略应用到候选和权重。
- `src/velaris_agent/decision/explainer.py`
  作用：产出 `score_breakdown / why_selected / tradeoffs / uncertainty_flags`。

## 8. 时序主链

目标态时序分两段：

### 8.1 提案阶段

1. 用户在酒店或商旅 Chat 里提出复合需求。
2. `velaris-platform-agent` 读取用户画像、酒店策略、企业商旅规则。
3. 平台向领域 agent / supplier skills 拉取 `top-k candidates`。
4. 平台把标准化候选、约束、上下文提交给 `velaris-agent`。
5. `velaris-agent` 先做 `bundle planner + feasibility`，再做 `decision graph` 排序。
6. `velaris-agent` 输出“推荐 bundle + 结构化决策依据”。
7. 平台渲染 proposal。

### 8.2 确认与回写阶段

1. 用户确认 bundle。
2. 平台触发有序的 fulfillment saga。
3. 各领域 agent / supplier skills 完成预订或保留动作。
4. 结果回写 `OutcomeStore / TaskLedger / DecisionMemory`。
5. 后续反馈驱动 `PreferenceLearner` 继续学习。

## 9. 商业化建议

如果面向酒店用户和商旅用户，这个架构最合理的商业化方式是：

- 酒店侧：会员礼宾助手 / 酒店品牌白标能力
- 商旅侧：企业差旅助手 / 高频商务旅客订阅
- 供给侧：签约 supplier 的推荐分成或技术服务费

不建议把第一阶段目标写成“全量 OTA 替代品”，因为那会把组织复杂度提前拉爆。

## 10. 交付物

本次同步补了两张图：

- 优化后的架构图：
  [docs/diagrams/velaris-agent-hotel-biztravel-architecture.svg](/Users/apus/Documents/UGit/velaris-agent/docs/diagrams/velaris-agent-hotel-biztravel-architecture.svg)
- 酒店 / 商旅联合决策时序图：
  [docs/diagrams/velaris-agent-hotel-biztravel-sequence.svg](/Users/apus/Documents/UGit/velaris-agent/docs/diagrams/velaris-agent-hotel-biztravel-sequence.svg)

两张图的 PNG 版也已经导出，可直接用于方案讨论或对外沟通。
