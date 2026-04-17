# 架构文档

## 五层架构设计

```
L0  Agent Runtime        OpenHarness engine — LLM 推理 + 工具调用编排
L1  Goal-to-Plan         场景识别 → 能力规划 → 治理约束生成
L2  Routing & Governance  策略路由 → 能力签发 → 停止条件
L3  Decision Execution    多维评分 + 场景执行 + 数据自主抓取
L4  Runtime Control       任务账本 + Outcome 回写 + 决策环境快照
──  Learning Loop         决策记忆 + 偏好学习 + 自进化复盘 (贯穿全层)
```

## 层级详解

### Layer 0: Agent Runtime (OpenHarness Engine)
- **核心文件**: `src/openharness/engine/query_engine.py`, `query.py`
- **职责**: 流式 LLM 推理 + 多轮工具调用编排
- **关键类**: `QueryEngine` — 管理会话历史、工具注册、权限检查、成本追踪
- **特性**:
  - 不写死 pipeline，让 LLM 自主决定调什么工具、调几次
  - 后台技能复盘：工具调用达到阈值后自动 fork 静默 review 回合
  - 支持 auto-compact（上下文窗口自动压缩）

### Layer 1: Goal-to-Plan Compiler
- **核心文件**: `src/velaris_agent/biz/engine.py`
- **关键函数**: `build_capability_plan(query, constraints, scenario)`
- **职责**: 把自然语言目标编译为结构化 plan
- **输出结构**:
  ```python
  {
      "scenario": str,           # 识别的场景
      "capabilities": list,      # 所需能力集
      "weights": dict,           # 评分权重
      "governance": dict,        # 治理约束
      "recommended_tools": list  # 推荐工具链
  }
  ```

### Layer 2: Routing & Governance
- **策略路由**: `src/velaris_agent/velaris/router.py` — `PolicyRouter`
  - 基于 YAML 规则引擎 (`config/routing-policy.yaml`)
  - 支持操作符: eq/ne/gt/gte/lt/lte/in/not_in
  - 路由策略: local_closed_loop / delegated_robotclaw / delegated_claude_code / hybrid
  - 停止策略画像: strict_approval / balanced / fast_fail
- **能力签发**: `src/velaris_agent/velaris/authority.py` — `AuthorityService`
  - 签发短时能力令牌 (CapabilityToken)
  - 敏感能力需审批: write, exec, audit, contract_form

### Layer 3: Decision Execution
- **核心文件**: `src/velaris_agent/biz/engine.py`
- **关键函数**:
  - `infer_scenario(query)` — 场景识别
  - `score_options(options, weights)` — 多维加权评分
  - `run_scenario(scenario, payload)` — 场景执行分发
- **场景实现**:
  - `_run_travel_scenario` — 商旅比价
  - `_run_tokencost_scenario` — 成本分析
  - `_run_robotclaw_scenario` — 调度治理
  - `_run_procurement_scenario` — 采购决策
  - `_run_lifegoal_scenario` — 人生目标决策

### Layer 4: Runtime Control
- **任务账本**: `src/velaris_agent/velaris/task_ledger.py` — `TaskLedger`
  - 状态机: queued → running → completed/failed
  - 当前为内存 dict 实现
- **Outcome 存储**: `src/velaris_agent/velaris/outcome_store.py` — `OutcomeStore`
  - 记录业务执行结果
  - 当前为内存 list 实现

### Learning Loop (贯穿全层)
- **决策记忆**: `src/velaris_agent/memory/decision_memory.py` — `DecisionMemory`
  - JSONL 索引 + JSON 记录文件
  - 支持按用户/场景检索、相似度召回、反馈回填
- **偏好学习**: `src/velaris_agent/memory/preference_learner.py` — `PreferenceLearner`
  - 贝叶斯先验 + 指数衰减
  - 从用户实际选择中学习个性化权重
  - 偏差检测 + 对齐分析
- **自进化**: `src/velaris_agent/evolution/self_evolution.py` — `SelfEvolutionEngine`
  - 计算推荐接受率、平均满意度、维度漂移
  - 生成可执行优化动作

## 编排器 (Orchestrator)
- **核心文件**: `src/velaris_agent/velaris/orchestrator.py` — `VelarisBizOrchestrator`
- **职责**: 串联完整业务闭环
- **流程**: plan → route → authorize → create_task → execute → record_outcome
- **支持审计仓储协议** (AuditStore Protocol)

## 决策环境快照
每次决策完成后自动快照：
| 快照类别 | 包含内容 |
|----------|----------|
| 环境变量 | 原始意图、结构化 intent、候选项、过滤后候选项 |
| 决策变量 | 使用的权重、每个选项每个维度的评分明细、调用的工具 |
| 治理变量 | 路由 trace、能力令牌、任务状态变迁、outcome 指标 |
| 输出快照 | 系统推荐、备选方案、推荐理由 |
| 反馈数据 | 用户最终选择、满意度 0-5、结果备注 |
