# Velaris-Agent 技术方案（基于 OpenHarness 二开）

> 版本：v0.2.0（文档重写版）
> 基线仓库：`git@github.com:HKUDS/OpenHarness.git`

## 1. 方案概述

Velaris-Agent 的目标是把 OpenHarness 的通用 Agent 能力，落地为可交付的业务决策系统。

聚焦三条产品线：

1. 商旅 AI 助手：机酒比价 + 意图识别 + 组合推荐。
2. AI TokenCost：成本诊断 + 模型路由 + 降本建议。
3. OpenClaw 运行环境：意图单 -> 提案 -> 合约的三段式派单。

## 2. 设计原则

1. 路由先行：先决策再执行，避免“先干后解释”。
2. 权限外置：Capability Token 独立于 Prompt。
3. 任务可追踪：全链路任务账本（queued/running/completed/failed）。
4. 结果可回放：Outcome 结构化回写，支持策略迭代。
5. 契约驱动：输入/输出/停止条件统一 JSON Schema。

## 3. 技术架构

### 3.1 核心闭环

```text
Goal 输入
  -> PolicyRouter（路由）
  -> AuthorityService（签权）
  -> Planner + DecisionCore（规划与决策）
  -> Executor（执行）
  -> Evaluator（评估）
  -> OutcomeStore（回写）
  -> TaskLedger（审计轨迹）
```

### 3.2 策略与契约

- 策略文件：`config/routing-policy.yaml`
- 输入契约：`contracts/decision-contract/input.schema.json`
- 输出契约：`contracts/decision-contract/output.schema.json`
- 停止条件：`contracts/decision-contract/stop-conditions.schema.json`

## 4. 当前落地（已实现）

### 4.1 新增模块

- `packages/core/src/policy/router.ts`
- `packages/core/src/policy/default-routing-policy.ts`
- `packages/core/src/governance/authority.ts`
- `packages/core/src/control/task-ledger.ts`
- `packages/core/src/eval/outcome-store.ts`
- `velaris-agent-py/src/openharness/biz/engine.py`
- `velaris-agent-py/src/openharness/velaris/router.py`
- `velaris-agent-py/src/openharness/velaris/authority.py`
- `velaris-agent-py/src/openharness/velaris/task_ledger.py`
- `velaris-agent-py/src/openharness/velaris/outcome_store.py`
- `velaris-agent-py/src/openharness/velaris/orchestrator.py`
- `velaris-agent-py/src/openharness/tools/biz_execute_tool.py`
- `velaris-agent-py/src/velaris_agent/`

### 4.2 主流程接入

`packages/core/src/agent.ts` 已完成：

1. 路由上下文构建。
2. 规则命中与策略选择。
3. 能力签发与审批判定。
4. 任务账本根任务与步骤任务记录。
5. 评估后 Outcome 回写。

`velaris-agent-py/src/openharness/velaris/router.py` 已完成：

1. 读取 `config/routing-policy.yaml`。
2. 将业务计划映射为统一路由上下文。
3. 按规则优先级执行配置化匹配并输出 `trace` / `reason_codes`。

### 4.3 验证状态

- `pnpm typecheck`：通过。
- `pnpm test`：通过（新增路由治理测试）。
- Python `biz` 定向测试：通过（能力层、工具层、注册表集成、技能装载、运行时闭环）。
- Python `velaris_agent` 命名空间与领域数据源 adapter：通过。

## 5. 三大场景实施计划

### Phase A：商旅 AI 助手

1. 接入 `parse_intent/search_flights/search_hotels/recommend` 工具。
2. 接入 flight-compare 数据源。
3. 建立推荐质量与报价准确率指标。

### Phase B：AI TokenCost

1. 接入 `analyze_usage/model_compare/optimize_suggest` 工具。
2. 引入模型价格数据与版本管理。
3. 建立“建议采纳率/30天降本率”回流指标。

### Phase C：OpenClaw 运行环境

1. 定义 `IntentOrder/ServiceProposal/TransactionContract` 数据结构。
2. 接入 `match_vehicles/calculate_route/score_proposals/form_contract`。
3. 强化 strict_approval 审批链与越权阻断。

## 6. OpenHarness 二开路线

### 6.1 代码仓策略

1. Fork OpenHarness 到组织仓。
2. 已在当前仓库落地 `velaris-agent-py/`，承载第一轮 Python 运行时迁移。
3. 当前 TS 仓保留策略仿真、契约验证、测试基线能力。

### 6.2 迁移策略

1. 已迁治理骨架：路由、权限、任务账本、审计日志已在 TS 与 Python 两侧落地最小实现。
2. 正在迁场景：按 A/B/C 三场景逐个接入工具，并优先通过 `biz` 模块统一抽象能力。
3. 最后统一：汇总指标、可视化和发布管线。

## 7. 风险与控制

1. 风险：规则配置和代码实现漂移。
- 控制：策略文件 + 默认策略对象双向校验。

2. 风险：场景工具开发先于治理约束。
- 控制：新工具必须声明 capability demand。

3. 风险：多 runtime 切换复杂度高。
- 控制：先跑 local 与 openclaw 双路，再扩展 hybrid。

## 8. 交付标准

1. 所有新增模块必须有中文注释（是什么/做什么/为什么）。
2. `pnpm typecheck` 和 `pnpm test` 必须通过。
3. 路由输出必须包含 `trace` 与 `reasonCodes`。
4. 任务状态迁移必须可查询。
5. Outcome 记录可按 session 追溯。
