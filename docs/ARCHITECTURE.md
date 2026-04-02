# Valeris-Agent 决策引擎架构（双模）

## 1. 架构定位

Valeris-Agent 的本体不是“多 Agent 平台”，而是“目标导向、多策略、带治理与评估闭环的决策引擎”。

它支持两种运行模式并可在一次任务内切换：

- 自闭环模式（Local Closed-Loop）：由 Valeris-Agent 独立完成目标编译、策略选择、执行编排与评估。
- 分工模式（Delegated）：由 Valeris-Agent 保持决策主权，将执行分工给 OpenClaw 与 Claude Code。

分层职责固定如下：

- Valeris-Agent：Policy Brain（决策脑）
- OpenClaw：Control + Governance Runtime（任务控制与治理底座）
- Claude Code：Code Expert Runtime（代码域专家执行器）

## 2. 七层架构（从上到下）

### 2.1 Goal Plane（目标编译层）

职责：把自然语言需求编译为可计算目标对象。

产物：`GoalSpec`

核心字段：

- `goalType`：任务类型
- `constraints`：硬约束
- `successMetrics`：成功判定指标
- `riskBudget/costBudget/latencyBudget`：风险与资源预算

### 2.2 Policy Plane（策略选择层）

职责：根据当前状态与预算，在策略族中选择最优路线。

策略族建议：

- `single_agent`
- `planner_worker`
- `proposal_verify`
- `debate_red_team`
- `ask_human`
- `no_op`

### 2.3 Team Plane（队形编排层）

职责：仅在必要时组队，定义角色与通信拓扑。

核心决策：

- 角色：`planner/researcher/verifier/critic/actuator`
- 运行时：`self/openclaw/claude_code`
- 通信拓扑：主脑汇聚、点对点协作、分层汇报

### 2.4 Control Plane（任务控制层）

职责：任务生命周期管理与可恢复执行。

生命周期建议：

- `queued`
- `running`
- `blocked`
- `retrying`
- `completed`
- `canceled`
- `failed`

### 2.5 Authority Plane（权限治理层）

职责：把“是否允许执行”从提示词中剥离，做成独立能力边界。

核心机制：

- Capability Token（最小权限、短时效、可追踪）
- 审批链（人审/系统审）
- 越权阻断与审计记录

### 2.6 Runtime Plane（执行层）

职责：承接具体执行动作。

- `self`：Valeris 本地执行能力
- `openclaw`：任务控制面、审批、通知、跨会话追踪
- `claude_code`：代码实现、重构、测试、仓库级操作

### 2.7 Evaluation Plane（评估学习层）

职责：形成决策闭环，驱动策略更新。

评估维度：

- 完成度（目标达成）
- 一致性（证据冲突率）
- 代价（token/cost/latency）
- 风险（越权率、审批命中率）

## 3. 双模路由原则

### 3.1 进入自闭环模式的条件

- 任务低风险
- 单步或短链路任务
- 不依赖跨系统审批
- 无高敏感权限需求

### 3.2 进入分工模式的条件

- 高风险或强审计任务
- 需要后台生命周期管理、暂停/重试/取消
- 代码改动密集且需仓库上下文深度执行

### 3.3 分工模式下的细分路由

- 治理优先：路由到 OpenClaw
- 代码优先：路由到 Claude Code
- 混合任务：先 OpenClaw 管控，再 Claude Code 执行代码子任务

## 4. 决策闭环（固定 7 步）

1. 目标编译：输入请求 -> `GoalSpec`
2. 状态采样：预算、风险、证据一致性、工具健康度
3. 策略选择：生成并打分候选策略
4. 权限签发：按策略签发 Capability Token
5. 执行编排：创建任务并分配 runtime
6. 结果评估：计算质量/成本/风险与是否达标
7. 经验回写：沉淀 `OutcomeRecord` 供后续策略更新

## 5. 与当前代码的映射关系

已存在模块可直接承接：

- L1：`packages/core/src/layers/goal-parser.ts`
- L2：`packages/core/src/layers/planner.ts`
- L3：`packages/core/src/layers/decision-core.ts`
- L4：`packages/core/src/layers/executor.ts`
- L5：`packages/core/src/layers/evaluator.ts`

建议新增模块：

- `packages/core/src/policy/router.ts`：策略路由器
- `packages/core/src/governance/authority.ts`：能力令牌与审批
- `packages/core/src/control/task-ledger.ts`：持久化任务账本
- `packages/core/src/eval/outcome-store.ts`：决策评估回放存储

## 6. 交付工件（本次）

- `config/routing-policy.yaml`：可执行路由规则
- `contracts/decision-contract/input.schema.json`：决策输入契约
- `contracts/decision-contract/output.schema.json`：决策输出契约
- `contracts/decision-contract/stop-conditions.schema.json`：停止条件契约

