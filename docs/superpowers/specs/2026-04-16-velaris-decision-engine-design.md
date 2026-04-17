# Velaris 决策内核生产化设计

> 目标：在不改变 `Velaris Agent` 品牌、不破坏 OpenHarness 兼容层的前提下，把当前仓库从“可运行的决策智能 demo / runtime 二开”演进为“可审计、可学习、可分布式扩展”的生产级决策平台。

## 1. 设计背景

Velaris-Agent 的核心差异化不是“又一个 Agent 框架”，而是三条决策能力主线：

1. 决策过程可审计
2. 多方利益冲突可量化协商
3. 偏好可学习并持续优化

这三条主线已经在当前仓库里有真实实现雏形：

- `src/velaris_agent/biz/engine.py`
  - 已具备场景识别、默认权重、基础评分、场景执行入口
- `src/velaris_agent/memory/preference_learner.py`
  - 已具备个性化权重学习、偏差检测、用户-组织对齐分析
- `src/velaris_agent/memory/conflict_engine.py`
  - 已具备利益冲突识别
- `src/velaris_agent/memory/negotiation.py`
  - 已具备协商提案生成
- `src/velaris_agent/memory/stakeholder.py`
  - 已具备利益相关方注册与决策曲线追踪雏形
- `src/velaris_agent/velaris/task_ledger.py`
  - 已具备任务账本雏形
- `src/velaris_agent/velaris/outcome_store.py`
  - 已具备 outcome 回写雏形

因此本轮设计的重点不是推翻重做，而是：

- 把现有“单文件/内存态/启发式”能力升级成“算子化/持久化/可聚合”的生产级内核
- 保留 `OpenHarness` 作为 L0 运行时底座
- 保留 `velaris_agent` 作为差异化业务内核与品牌承载层

## 2. 业务锚点与场景优先级

### 2.1 第一优先场景

首个主攻生产场景定义为：

- 企业采购决策
- 合规审计决策
- 多供应商 / 多 stakeholder / 多约束的推荐与协商

原因：

1. 与 Velaris 的三条能力主线直接同构
2. 国内外都存在明确付费意愿
3. 决策链路天然要求留痕、解释、回放、问责
4. 当前 `score_options + OrgPolicy + DecisionRecord + stakeholder/negotiation` 已具备最小可行基础

### 2.2 算法验证场景

以下场景继续保留为算法和产品化的验证跑道：

- `travel`
  - 用于验证预算/舒适度/时间/组织政策的多目标权衡
- `tokencost`
  - 用于验证成本/质量/速度的多目标优化与偏好学习
- `robotclaw`
  - 用于验证强治理、强约束、proposal/contract 型决策流
- `lifegoal`
  - 作为个人决策和偏好学习的展示型场景

这四类场景不应被废弃，而应作为统一决策内核的不同 domain profile。

## 3. 设计目标

### 3.1 目标

1. 支持生产级持久化、审计、回放和聚合分析
2. 支持多目标优化，不再仅依赖单一加权和
3. 支持多 stakeholder 冲突建模与协商提案
4. 支持用户偏好、组织策略、群体画像的分层融合
5. 支持偏差检测、纠偏和长期决策曲线追踪
6. 支持从单机仓库平滑升级到分布式事件架构

### 3.2 非目标

1. 不把 Velaris 重定位成通用 Agent 框架
2. 不移除 OpenHarness 兼容入口
3. 不在本阶段直接拆成多个独立仓库
4. 不在本阶段追求“所有场景一次性产品化”

## 4. 总体架构

### 4.1 分层结构

```text
L0 OpenHarness Runtime
  - 会话循环
  - 工具注册
  - MCP / UI / CLI / 权限 / 技能

L1 Velaris Decision Gateway
  - query -> objective/constraints/context
  - session 级治理与追踪

L2 Decision Graph Compiler
  - 目标建模
  - 候选项 schema 标准化
  - stakeholder graph 构建
  - operator graph 编排

L3 Decision Operators
  - 约束过滤
  - 多目标求解
  - 协商与让步
  - 偏差检测
  - 推荐解释

L4 Governance / Audit / Learning / Analytics
  - authority / policy / audit_event
  - feedback / preference update / bias review
  - decision curve / rollup / cohort analysis
```

### 4.2 边界约束

#### OpenHarness 继续负责

- Agent runtime
- Tool 协议
- UI、CLI、MCP、技能管理
- 通用工具发现与执行

#### Velaris 继续负责

- 决策图编译
- 多目标求解与协商
- 审计账本
- 偏好学习与偏差检测
- 领域场景 profile

### 4.3 当前推荐部署形态：单体生产架构

基于“尽可能少中间件、暂不考虑分布式”的约束，当前推荐架构不是多服务拆分，而是：

- 一个 `Velaris Core` 应用进程
- 一个 PostgreSQL 实例
- 一个本地文件证据目录（或后续平滑切到对象存储）

```text
OpenHarness Runtime / CLI / API
  -> Velaris Core
     -> Decision Compiler
     -> Operator Pipeline
     -> Governance + Audit
     -> Preference + Bias
     -> Curve Rollup Jobs
  -> PostgreSQL
  -> local evidence store
```

当前阶段明确不引入：

- Redis
- Kafka / Redpanda
- ClickHouse
- Celery / 独立任务队列
- 多副本分布式协调

理由：

1. 当前主要瓶颈不在吞吐，而在模型、数据结构和算子边界
2. 过早引入中间件会放大维护成本和故障面
3. 单体 + PostgreSQL 仍足以支撑早期生产环境中的审计、学习和曲线聚合

## 4.4 单体架构下的模块边界

为了避免“虽然是单体，但内部还是一团糟”，单体内部也必须强分层：

- `api / cli`
  - 只负责请求接入和返回
- `decision`
  - 负责 objective、constraint、operator graph、solver
- `governance`
  - 负责 authority、policy、audit_event
- `memory`
  - 负责决策记录、偏好画像、偏差记录、召回
- `analytics`
  - 负责 rollup、决策曲线、健康指标
- `scenarios`
  - 负责 travel / tokencost / robotclaw / procurement 等领域适配

这样做的目的，是在不加中间件的情况下，仍然保证边界清楚、后续好拆。

## 5. 决策内核：从函数编排升级为算子图

当前 `src/velaris_agent/biz/engine.py` 已经承担了过多责任：

- 场景识别
- 权重生成
- 评分
- 场景执行
- stakeholder 合并

生产化后应升级为“决策图 + 可替换算子”架构。

### 5.1 核心算子类型

1. `IntentOp`
   - 输入：自然语言 query + payload
   - 输出：结构化 objective / constraints / assumptions

2. `OptionDiscoveryOp`
   - 输入：场景、查询条件、数据源上下文
   - 输出：统一 schema 的候选项集合

3. `NormalizationOp`
   - 输入：候选项原始字段
   - 输出：标准维度分值、证据引用、缺失值说明

4. `StakeholderOp`
   - 输入：用户、组织、关系型 stakeholder 信息
   - 输出：`StakeholderMapModel`、alignment、conflicts

5. `FeasibilityOp`
   - 输入：硬约束、合规约束、预算约束
   - 输出：可行域（feasible set）

6. `OptimizationOp`
   - 输入：feasible set、权重、效用模型
   - 输出：Pareto frontier、排序候选、置信度

7. `NegotiationOp`
   - 输入：冲突、影响力、组织硬约束
   - 输出：协商提案、让步代价、可行性评分

8. `BiasAuditOp`
   - 输入：历史记录、当前推荐、当前选择、群体参考
   - 输出：偏差信号、纠偏建议、风险提示

9. `ExplanationOp`
   - 输入：候选集、frontier、协商结果、审计证据
   - 输出：结构化 explanation + 审计摘要

### 5.2 算子统一契约

每个算子统一输出以下元信息：

- `operator_id`
- `operator_version`
- `input_schema_version`
- `output_schema_version`
- `latency_ms`
- `confidence`
- `evidence_refs`
- `policy_impact`
- `warnings`

这样能保证：

- 可审计：知道每一步用了什么版本和证据
- 可回放：同样输入能重跑同样逻辑
- 可演进：不同算法版本可并行 A/B

## 6. 多目标优化策略

### 6.1 设计原则

Velaris 不应把“单一加权总分最高”视为唯一最优解。
在生产场景里，更合理的定义是：

- 先满足硬约束
- 再识别 Pareto 最优边界
- 再考虑 stakeholder 冲突、协商代价、风险与不确定性
- 最后选出当前 operating point

### 6.2 求解四层

#### 第一层：约束可行域

先处理硬约束：

- 预算上限
- 合规禁入项
- 审批要求
- 供应商资格
- 不可突破的组织策略

输出：

- `feasible_options`
- `rejected_options`
- `rejection_reasons`

这一步是布尔裁剪，不是打分。

#### 第二层：Pareto 前沿

在可行域内，对以下维度做非支配筛选：

- cost / quality / speed / compliance / risk / comfort / growth 等

输出：

- `pareto_frontier`
- `dominated_options`
- `frontier_metrics`

这样可以避免单一加权和导致的前沿误杀。

#### 第三层：多方效用与协商代价

对 Pareto 前沿上的选项计算：

- 用户效用
- 组织效用
- 关系型 stakeholder 效用
- 冲突代价
- 让步代价
- 风险代价
- 不确定性惩罚

统一 operating point 目标函数可表达为：

```text
U(x)
  = Σ actor_weight(a) * utility_a(x)
  - λ1 * conflict_cost(x)
  - λ2 * policy_risk(x)
  - λ3 * uncertainty(x)
  - λ4 * regret_estimate(x)
```

这里的 `U(x)` 不是用来替代 Pareto，而是用于在 Pareto 前沿中选择“当前最适合落地”的推荐点。

#### 第四层：长期学习最优

单次推荐是局部最优。
平台最终追求的是动态长期最优：

- 更高接受率
- 更高满意度
- 更低 regret
- 更低偏差率
- 更高用户-组织对齐度

因此系统必须区分：

- `Online Solver`
  - 低延迟，面向即时推荐
- `Offline Solver`
  - 周期优化策略参数，面向长期最优

### 6.3 局部与全局的关系

#### 局部优化

面向单次采购、单次差旅、单次 vendor choice。

#### 组合优化

面向同一个 session 内多个子决策联动，例如：

- 采购价格低但合同风险高
- 航班便宜但酒店总成本更高

#### 全局优化

面向季度、年度、组织层 portfolio 决策：

- SaaS 成本结构优化
- 供应商集中度控制
- 审计通过率与效率平衡

结论：

- 局部求解负责“这次怎么选”
- 全局求解负责“长期参数怎么调”

## 7. 偏好学习与偏差检测

### 7.1 分层偏好模型

当前 `PreferenceLearner` 已有“默认权重 + 历史学习 + 组织融合”的基础，生产化后升级为：

```text
effective_weights
  = global_prior
  + scenario_prior
  + org_policy_delta
  + cohort_delta
  + user_delta
  + session_delta
```

说明：

- `global_prior`
  - 全平台通用先验
- `scenario_prior`
  - 场景默认权重
- `org_policy_delta`
  - 组织策略偏移
- `cohort_delta`
  - 部门/岗位/国家/行业等群体偏移
- `user_delta`
  - 个人长期偏好
- `session_delta`
  - 当前会话中的临时意图偏移

### 7.2 偏差检测分层

#### 用户行为偏差

- recency
- anchoring
- loss_aversion
- sunk_cost
- overconfidence

#### 组织策略偏差

- 成本过度优先
- 合规过度保守
- 供应商路径依赖
- 部门利益偏置

#### 系统/模型偏差

- 召回源偏差
- 解释偏差
- 排序校准失真
- 训练样本覆盖偏差

### 7.3 偏差检测机制

1. 规则检测
   - 保留当前启发式逻辑
2. 反事实检测
   - 去掉某个因素后推荐是否变化
3. 群体对照检测
   - 与 cohort 基线对比，判断是否系统性偏移

### 7.4 新增关键指标

- `regret_score`
  - 事后看，是否存在明显更优替代
- `calibration_score`
  - 高置信推荐是否真的更常被接受或带来更高满意度

## 8. 精简中间件的数据架构

### 8.1 当前阶段的最小生产存储方案

当前推荐只保留两类基础设施：

- PostgreSQL
  - 唯一事务真相源
- 本地文件证据目录
  - 保存大体积 explanation 附件、外部抓取快照、原始输入归档

#### PostgreSQL 负责

- decision session / option / score / recommendation
- stakeholder snapshot / policy snapshot
- feedback / outcome / bias signal
- audit_event
- preference profile
- decision curve rollup
- 任务账本与后台 job 状态

#### 本地文件证据目录负责

- 原始 payload 归档
- 大体积 explanation 材料
- 外部证据抓取快照
- 可回放的环境附件

文件目录可以先约定为：

```text
.velaris/
  evidence/
  snapshots/
  reports/
```

部署到服务器时，可挂载持久卷；后续若需要切对象存储，再保持引用接口不变平滑迁移。

### 8.2 当前阶段明确不引入的组件

- 不引入 Redis
  - 缓存先交给进程内 TTL cache + PostgreSQL 索引优化
- 不引入消息队列
  - 后台任务先采用数据库任务表 + 单进程 worker
- 不引入 ClickHouse
  - 聚合分析先使用 PostgreSQL rollup 表和物化视图
- 不引入向量数据库
  - 相似召回先用 PostgreSQL 全文检索 / trigram，相似度不够时再升级

### 8.3 轻量召回与聚合策略

#### 相似决策召回

- 第一阶段：
  - PostgreSQL 全文检索
  - trigram similarity
  - 结构化过滤（scenario / org / time window / option type）

#### 决策曲线与聚合

- 第一阶段：
  - PostgreSQL 汇总表
  - PostgreSQL 物化视图
  - 定时命令或应用内调度器执行 rollup

这样可以在零额外中间件的前提下，仍保持指标可查、曲线可算、结果可追。

### 8.2 核心实体

建议逐步引入以下持久化实体：

- `decision_session`
- `decision_objective`
- `decision_option`
- `decision_option_metric`
- `decision_frontier`
- `decision_recommendation`
- `stakeholder_snapshot`
- `policy_snapshot`
- `negotiation_round`
- `feedback_event`
- `outcome_fact`
- `bias_signal`
- `preference_profile`
- `audit_event`
- `decision_curve_rollup`

### 8.3 审计事件模型

`audit_event` 采用 append-only 设计，至少包含：

- `event_id`
- `session_id`
- `decision_id`
- `step_name`
- `operator_id`
- `operator_version`
- `input_ref`
- `output_ref`
- `evidence_ref`
- `confidence`
- `trace_id`
- `created_at`

重要约束：

- 不直接把大模型私有 chain-of-thought 当审计材料
- 只保存结构化理由图与证据链

### 8.4 后台任务模型：不用消息队列的健康做法

为了避免引入 Celery / Kafka / Redis，本阶段后台任务统一采用“数据库任务表 + 应用内 worker”模型：

- `job_queue`
  - 记录待执行任务
- `job_run`
  - 记录执行状态、重试次数、错误摘要

任务类型包括：

- feedback 回填
- preference profile 重算
- bias review
- decision curve rollup
- 审计完整性检查

保障策略：

1. 每个 job 必须具备幂等键
2. 每个 job 必须有最大重试次数
3. 失败任务必须落库并可人工重放
4. 后台任务与在线决策解耦，失败不能阻塞核心推荐链路

## 9. 决策曲线与聚合计算

当前 `DecisionCurveTracker` 已经在 `src/velaris_agent/memory/stakeholder.py` 中存在，但仍偏单点统计。
生产化后要升级为“在线事件 + 离线 rollup”的双层曲线体系。

### 9.1 六条核心曲线

1. `Acceptance Curve`
   - 推荐接受率
2. `Satisfaction Curve`
   - 满意度 / 结果达成率
3. `Alignment Curve`
   - 用户-组织对齐度
4. `Bias Curve`
   - 偏差率 / 偏差严重度
5. `Stability Curve`
   - 权重稳定性 / 推荐稳定性
6. `Efficiency Curve`
   - 决策耗时 / 协商轮次 / 审计通过率

### 9.2 聚合维度

聚合至少按以下切片输出：

- user
- org
- scenario
- department
- vendor / provider
- region
- policy_version
- operator_version

### 9.3 聚合粒度

- 日
- 周
- 月
- 季

### 9.4 建议输出的 rollup 指标

- `sample_size`
- `accept_rate`
- `avg_satisfaction`
- `avg_regret`
- `bias_rate`
- `bias_severity_mean`
- `alignment_mean`
- `alignment_p90_gap`
- `negotiation_cost_mean`
- `policy_violation_rate`
- `weight_stability`
- `confidence_calibration`
- `outcome_roi`

### 9.5 单体模式下的计算方式

在当前阶段，决策曲线计算采用“两段式”：

1. 在线写入
   - 每次决策完成时写入原子事件和最小统计字段
2. 离线汇总
   - 通过定时命令把原子事件汇总到 rollup 表

不做流式计算，不做实时大屏。
这样可以显著降低复杂度，同时保证统计口径稳定。

## 10. 仓库内目标模块划分

### 10.1 现状问题

当前问题不在“能力不存在”，而在“边界还不够干净”：

- `biz/engine.py` 责任过重
- `DecisionMemory` 还是本地文件级存储
- `TaskLedger` / `OutcomeStore` 还是内存态
- 偏差检测、偏好学习、协商逻辑尚未沉淀为统一 operator

### 10.2 目标目录

```text
src/velaris_agent/
  decision/
    compiler/
    operators/
    solver/
    explanation/
  governance/
    policy/
    authority/
    audit/
  memory/
    repositories/
    learners/
    bias/
    retrieval/
  analytics/
    curves/
    rollups/
    metrics/
  scenarios/
    procurement/
    travel/
    tokencost/
    robotclaw/
    lifegoal/
```

### 10.3 渐进迁移映射

- `src/velaris_agent/biz/engine.py`
  - 拆向 `decision/compiler`、`decision/solver`、`scenarios/*`
- `src/velaris_agent/memory/decision_memory.py`
  - 拆向 `memory/repositories`、`memory/retrieval`
- `src/velaris_agent/memory/preference_learner.py`
  - 拆向 `memory/learners`、`memory/bias`
- `src/velaris_agent/velaris/task_ledger.py`
  - 迁入 `governance/audit`
- `src/velaris_agent/velaris/outcome_store.py`
  - 迁入 `analytics` 或 `governance/audit`

兼容原则：

- 现有 public import 路径先保留导出层
- `velaris` / `vl` 品牌与命令入口不变
- `openharness` 入口保留兼容壳层

## 11. 分阶段实施方案

### Phase 0：场景锚定与指标定义

目标：

- 把企业采购 + 合规审计设为主线场景
- 把 `travel / tokencost / robotclaw` 作为统一内核验证场景
- 固化 metrics registry 与审计字段

产出：

- 决策指标字典
- 统一 option schema
- 统一 audit schema

### Phase 1：持久化基座

目标：

- 把 `DecisionMemory / TaskLedger / OutcomeStore` 从本地/内存态迁到 PostgreSQL
- 增加 `audit_event`
- 增加本地证据目录引用
- 增加 `job_queue / job_run`

产出：

- repository 层
- schema migration
- append-only 审计表
- job 表与后台 worker

### Phase 2：算子化

目标：

- 从 `biz/engine.py` 提取 operator graph
- 把 `score / conflict / negotiation / bias` 算子化
- 算子全量补版本和 evidence

产出：

- operator contract
- operator registry
- operator execution trace

### Phase 3：多目标求解升级

目标：

- 引入 `FeasibilityOp`
- 引入 `ParetoFrontierOp`
- 引入 `OperatingPointSelector`
- 让 weighted-sum 退居 operating point 选择阶段

产出：

- 在线求解器 v2
- 前沿解释能力

### Phase 4：学习与纠偏升级

目标：

- 分层偏好模型
- regret / calibration
- 反事实偏差检测

产出：

- preference profile v2
- bias audit v2
- 策略调优信号

### Phase 5：决策曲线与分析平台

目标：

- 把曲线从单点计算升级为 rollup 平台
- 输出 user/org/scenario/operator 维度分析

产出：

- analytics rollup
- dashboard-ready dataset

### Phase 6：分布式事件化

目标：

- 当写入量和分析需求明显上升时，引入事件总线和分析存储

建议：

- Kafka / Redpanda
- ClickHouse

注意：

- 本阶段不是当前第一优先
- 当前版本明确不做
- 只有在 PostgreSQL rollup 和单体 worker 明显成为瓶颈时才考虑

## 12. 风险与设计约束

### 12.1 主要风险

1. 过早拆微服务，导致复杂度先于价值增长
2. 仍把 weighted-sum 当唯一求解器，导致多目标失真
3. 把大模型自由推理文本当审计主材料，导致审计不可控
4. 先做 dashboard 再做事件和口径统一，导致数据不可信
5. 场景过多同时推进，导致统一内核迟迟不稳定

### 12.2 设计约束

1. 品牌不变：继续使用 `Velaris Agent`
2. 兼容不破：保留 OpenHarness 兼容入口
3. 演进优先：增量迁移，不大爆炸重构
4. 审计优先：所有关键决策节点必须可回放
5. 算法优先：先沉淀 operator 和求解器，再做 UI 包装
6. 中间件克制：除 PostgreSQL 外，不默认新增独立中间件

## 12.3 系统健康保障

即使采用精简中间件架构，也必须保证系统健康。当前建议至少落实以下健康机制：

1. 数据健康
   - 所有核心实体有外键、唯一键、审计时间戳
   - `audit_event` append-only，不允许 update 覆盖历史
   - 核心写链路必须事务化

2. 任务健康
   - `job_queue` / `job_run` 可观测
   - 失败任务可重试、可重放、可人工接管
   - 后台任务失败不拖垮在线请求

3. 性能健康
   - 单次推荐链路设置 P95 预算
   - 慢查询必须可定位
   - rollup 任务限制窗口和批量大小

4. 审计健康
   - 每个推荐 session 必须能关联到完整 `audit_event`
   - 定时执行审计完整性巡检
   - 缺失证据引用的记录要能报警

5. 学习健康
   - 新偏好权重变更要有限幅
   - 偏差纠正策略要可关闭、可回滚
   - operator / policy 版本升级要可 pin

6. 运维健康
   - 提供 `/health`、`/ready`、`/metrics`
   - 提供每日数据一致性检查命令
   - 提供 rollup lag / failed jobs / audit completeness 三类核心告警

## 13. 结论

Velaris 的目标架构不应是“更花哨的 agent runtime”，而应是：

- 一个以多目标优化为核心的决策引擎
- 一个以审计留痕为核心的治理系统
- 一个以偏好学习和偏差纠偏为核心的长期优化系统

更准确地说，Velaris 的“全局最优”不是某次排序里一个固定的最高分，而是：

> 在硬约束可行域内，兼顾多方利益、政策风险、偏差纠正和长期学习收益的动态 Pareto 最优 operating point。

这一定义既能解释当前仓库为什么已经有差异化，也能指导后续如何把差异化真正产品化。
