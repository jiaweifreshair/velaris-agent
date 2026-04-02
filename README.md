# Valeris Agent

> 把每一次 AI 决策，沉淀成可复用、可审计、可持续优化的工程资产。

Valeris Agent 是一个 **AI 决策运行时框架（Decision Runtime Framework）**。它不是又一个聊天壳子，而是把“目标解析 → 规划 → 决策 → 执行 → 评估”变成可编排、可追踪、可控成本的标准流水线。

如果你正在做多 Agent 协作、企业级 AI 工作流、或需要“成本与质量同时可控”的 AI 产品，这个仓库就是你的底层引擎。

## 为什么是 Valeris

- 你不再手搓一次性 Agent 逻辑，而是复用一套分层决策内核。
- 你不再只能看“模型回复”，而是拿到完整决策路径与成本事件。
- 你不再在“效果、速度、成本”之间靠拍脑袋，而是用多维加权决策机制做可解释选择。
- 你可以把同一套引擎注入多个业务项目（如 `flight-compare`、`TokenScope`），快速形成产品矩阵。

## 核心能力

- 六层运行时架构（L0-L5）：事件总线、目标解析、规划编排、决策核心、执行引擎、评估反馈。
- Skill + Recipe 双抽象：可注册原子能力（Skill），再通过 Recipe 组合为可复用业务流程。
- 多维决策引擎：支持 `quality/cost/speed` 权重打分、过滤器、可扩展打分器。
- 预算与成本闭环：会话级 token / USD 实时追踪、80% 预算预警、超限策略（`compress/downgrade/stop`）。
- 子 Agent 网络：支持 `spawn + parallel` 并行任务协作。
- OpenAI-compatible 适配：可直连 OpenAI 及兼容接口服务。
- 全链路类型安全：TypeScript strict + Zod 输入输出校验。

## 六层架构一览

| 层级 | 模块 | 作用 |
|---|---|---|
| L0 | EventBus / AgentNetwork | 事件解耦、子 Agent 编排 |
| L1 | GoalParser | 自然语言 / 结构化 Goal 统一解析 |
| L2 | Planner | Recipe 匹配与执行计划生成 |
| L3 | DecisionCore | 约束过滤、多维打分、模型路由 |
| L4 | Executor | Skill/Recipe 执行、预算管控、异常处理 |
| L5 | Evaluator | 质量评分、成本分析、反馈沉淀 |

详细验证场景见：`docs/VALIDATION-CASES.md`

## 10 分钟上手

### 1) 环境要求

- Node.js >= 20
- pnpm >= 10

### 2) 安装依赖

```bash
pnpm install
```

### 3) 构建 + 测试

```bash
pnpm build
pnpm test
pnpm typecheck
```

### 4) 最小可运行示例

```ts
import { z } from 'zod';
import { createAgent, defineSkill, type RecipeDefinition } from '@valeris/core';
import { MemoryStorage, OpenAILLM } from '@valeris/core/adapters';

const analyzeUsageSkill = defineSkill({
  name: 'analyze-usage',
  description: '分析 API 用量与成本结构',
  inputSchema: z.object({ raw: z.record(z.unknown()) }),
  outputSchema: z.object({ totalCostUsd: z.number(), topModel: z.string() }),
  async execute(input) {
    return {
      totalCostUsd: Number(input.raw.totalCostUsd ?? 0),
      topModel: String(input.raw.topModel ?? 'gpt-4o-mini'),
    };
  },
});

const recipe: RecipeDefinition = {
  name: 'token_optimize',
  description: 'Token 成本优化流程',
  steps: [{ skill: 'analyze-usage' }, { skill: 'score-options' }],
};

const agent = createAgent({
  productId: 'tokencost',
  skills: [analyzeUsageSkill],
  recipes: [recipe],
  decisionWeights: { quality: 0.35, cost: 0.5, speed: 0.15 },
  storage: new MemoryStorage(),
  llm: new OpenAILLM({ apiKey: process.env.OPENAI_API_KEY ?? '' }),
  budget: {
    maxTokensPerSession: 50_000,
    maxCostPerSession: 0.1,
    onBudgetExceeded: 'compress',
  },
});

const session = agent.createSession('user_001');
const result = await session.run('我每月 AI 花费过高，帮我给出降本方案');
console.log(result.decision.reasoning);
console.log(result.evaluation.costAnalysis);
```

## 项目结构

```text
valeris-agent/
├── packages/
│   ├── core/      # 决策运行时核心
│   └── shared/    # 错误、日志、通用工具
├── cases/
│   ├── tokencost/     # Case 1: AI Token 成本优化
│   └── flightcompare/ # Case 2: 包机询价比价
├── docs/
│   ├── ARCHITECTURE.md
│   └── VALIDATION-CASES.md
└── examples/
```

## 与验证项目结合方案

下面是你提到的两个验证项目，与 Valeris 底层引擎的推荐接入方式。

### A. 结合 `flight-compare`（`@flight-compare`）

`flight-compare` 当前是 `FastAPI + agent-browser` 的旅行比价服务，Valeris 可以承担“判断层与编排层”：

- 把用户查询（如“下周三上海飞三亚，预算 20 万”）转换为 `goalType=charter_quote`。
- 用 Recipe 串联：`search-aircraft -> calc-reposition -> check-empty-legs -> score-options -> price-quote`。
- 用 L3 决策核心统一处理 `价格/时效/合规` 权重评分。
- 用 L4/L5 输出可解释推荐与成本归因，支持复盘。

建议接口边界：

- `flight-compare` 负责数据抓取、供应商接口和前端交互。
- `valeris-agent` 负责决策编排、策略选择、预算控制与评估沉淀。

### B. 结合 `TokenScope`（路径按你提供：`@Documents/UGit/tokenscope`）

TokenScope 可直接复用 `tokencost` 场景定义，形成“成本治理中枢”：

- 目标统一为 `goalType=token_optimize`。
- 关键 Skill：`analyze-usage`、`model-compare`、`optimize-suggest`。
- 决策权重建议：`{ cost: 0.50, quality: 0.35, speed: 0.15 }`。
- 预算建议：单次分析成本限制在 `< $0.10`，并默认开启超限压缩策略。

这样可以把 TokenScope 从“账单展示”升级为“可执行降本系统”。

## 与 OpenClaw / Claude Code 的联动亮点（对外话术）

- 决策脑 + 双执行臂：Valeris 负责决策，OpenClaw 负责治理，Claude Code 负责代码落地。
- 从目标到交付：一句目标可串联为任务计划、执行链路与可验证结果。
- 对话外自治任务：支持后台持续运行、暂停、重试、取消与恢复。
- 可审计 AI：每次策略命中、审批动作、执行结果都有追踪记录。
- 自治等级可控：可在 `supervised/plan/auto` 间按风险动态切换。
- 质量-成本-时延三目标平衡：不靠拍脑袋，靠策略规则和预算约束驱动。
- 双模切换：低风险任务本地闭环，高风险任务委派 OpenClaw/Claude Code 分工处理。
- 最小权限执行：能力按任务发放，超范围立即阻断并记录审计事件。
- 失败可回放：支持用同一输入回放路由和停止条件，定位问题更快。
- 不只是多 Agent：核心是“多策略决策引擎”，多 Agent 只是执行形态之一。

## 典型应用场景

1. 需求到代码交付：把需求拆解为任务后交给 Claude Code 执行改造、测试与提交建议。
2. 高风险发布治理：通过 OpenClaw 管理审批、审计与回滚检查点，降低发布风险。
3. 生产故障处置：自动判断“先止血还是先定位根因”，并行拉起排障子任务。
4. 成本治理与模型路由：在 TokenScope 场景中持续做降本建议与预算控制。
5. 复杂比价与推荐：在 flight-compare 场景中做多源检索、冲突裁决与可解释推荐。
6. 合规敏感任务执行：涉及外部写入或通知时，强制走权限令牌与审批链。
7. 长任务后台编排：任务可脱离会话持续运行，支持状态追踪与人工接管。
8. 多团队协同：策略层统一，执行层按研发/运营/风控职责分工。
9. 策略 A/B 实验：同一目标跑不同策略，比较质量/成本/时延后迭代规则。
10. 人机协同决策：证据冲突、预算耗尽或越权风险时自动升级人工检查点。

## 推荐落地顺序（两周）

1. 第 1-2 天：沉淀两个项目的统一 Goal 协议与 Recipe 协议。
2. 第 3-5 天：先接 `flight-compare` 判断层，打通端到端推荐链路。
3. 第 6-8 天：接入 TokenScope 成本分析链路，落地优化建议闭环。
4. 第 9-10 天：打通评估数据回流，形成可量化仪表盘。
5. 第 11-14 天：灰度上线 + 指标复盘（采纳率、成本下降、延迟、预算命中率）。

## 开发命令

```bash
pnpm build
pnpm test
pnpm typecheck
pnpm clean
```

## 里程碑方向

- 多模型路由策略增强（按任务类型与 SLA 动态路由）
- 更细粒度预算治理（层级配额 / 任务配额）
- 生产级存储适配器（PostgreSQL / Redis）
- 决策可视化控制台（决策树 + 成本时间线 + 反馈回放）

## 结语

当你把 Agent 从“会说话”升级到“会做可审计决策”，产品的护城河才真正开始出现。

Valeris 的目标很明确：
**让 AI 系统从 Demo 体质，进化为可规模化交付的工程系统。**
