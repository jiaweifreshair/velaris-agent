# Valeris Agent - 验证场景文档

> 两个验证 Case 的完整设计 | v0.1.0 | 2026-04-02

---

## Case 1: AI TokenCost - AI 使用成本优化

### 1.1 产品定位

Web 工具，面向 AI 开发者/团队，分析 API 用量 -> 输出降成本方案。

**目标用户**: 每月 AI API 花费 $500-$50,000 的开发团队
**核心价值**: "告诉我怎么花更少的钱，获得相同的效果"

### 1.2 Goal 示例

```typescript
{
  goalType: 'token_optimize',
  userId: 'dev_team_42',
  intent: '我每月 OpenAI 花费 $2000，想降到 $800 以内',
  constraints: {
    currentMonthlyCost: 2000,
    targetMonthlyCost: 800,
    maxQualityLoss: 0.1,      // 允许 10% 质量下降
    providers: ['openai', 'anthropic', 'google'],
  },
  sessionId: 'sess_abc123',
  budget: {
    maxTokens: 50000,
    maxCostUsd: 0.10,         // 分析本身花费不超过 $0.10
  },
}
```

### 1.3 Skill 清单

| Skill | 类型 | 输入 | 输出 | 预估成本 |
|-------|------|------|------|---------|
| `analyze-usage` | 原子 | API 用量 JSON | 成本结构分析 | 0 (纯计算) |
| `model-compare` | 原子 | 任务类型 + 候选模型 | 质量/成本/延迟对比 | ~2000 tokens |
| `optimize-suggest` | 原子 | 成本分析 + 质量约束 | 优化建议列表 | ~3000 tokens |

#### analyze-usage 详细设计

```
输入:
  - apiUsageData: OpenAI/Anthropic 的用量导出 JSON
  - period: 分析周期（7d/30d/90d）

输出:
  - totalCost: 总花费
  - costByModel: 按模型分组成本
  - costByTaskType: 按任务类型分组（分类/生成/嵌入/...）
  - topExpensiveCalls: 最贵的 Top 10 调用
  - avgTokensPerCall: 平均每次调用 token 数
  - wasteIndicators: 浪费指标（重复调用、过长 prompt、低利用率模型）
```

#### model-compare 详细设计

```
输入:
  - taskType: 'classification' | 'generation' | 'embedding' | 'reasoning' | 'coding'
  - currentModel: 当前使用的模型
  - candidateModels: 候选替代模型列表
  - qualityThreshold: 最低质量要求

输出:
  - comparisons: [{
      model: string,
      qualityScore: 0-1,        // 在该任务类型上的质量评分
      costPer1kTokens: number,  // 千 token 成本
      avgLatencyMs: number,     // 平均延迟
      recommendation: 'upgrade' | 'downgrade' | 'keep' | 'switch',
    }]
```

#### optimize-suggest 详细设计

```
输入:
  - usageAnalysis: analyze-usage 的输出
  - modelComparison: model-compare 的输出
  - constraints: 用户约束（目标成本、质量底线）

输出:
  - suggestions: [{
      type: 'model_switch' | 'prompt_compress' | 'cache_enable' | 'batch_merge' | 'tier_split',
      description: string,
      estimatedSaving: number,     // 预估月度节省 USD
      qualityImpact: number,       // 质量影响 -1 to 1
      effort: 'low' | 'medium' | 'high',
      priority: number,            // 1-10 优先级
    }]
  - totalEstimatedSaving: number
  - projectedMonthlyCost: number
```

### 1.4 Recipe: cost-audit

```
Step 1: analyze-usage
  输入: 用户上传的 API 用量 JSON
  输出: 成本结构分析

Step 2: model-compare
  输入: Step 1 识别的 topTaskTypes + 候选模型
  输出: 模型质量/成本对比矩阵

Step 3: score-options (内置 Skill)
  输入: Step 2 的 comparisons
  权重: { cost: 0.50, quality: 0.35, speed: 0.15 }
  输出: 排序后的模型替换方案

Step 4: optimize-suggest
  输入: Step 1 + Step 2 + Step 3 的综合分析
  输出: 最终优化建议列表 + 预估节省金额
```

### 1.5 Decision 权重

```typescript
{ cost: 0.50, quality: 0.35, speed: 0.15 }
```

**理由**: 用户的核心诉求是降成本，质量不能太差，速度是次要因素。

### 1.6 评估指标

| 指标 | 目标 | 测量方式 |
|-----|------|---------|
| 建议采纳率 | > 60% | 用户标记"已采纳"的建议比例 |
| 实际成本下降 | > 30% | 30天后对比实际 API 账单 |
| 质量损失 | < 10% | 用户主观反馈（1-5分） |
| 分析耗时 | < 30s | 从提交到出结果的时间 |
| 分析自身成本 | < $0.10 | 单次分析的 LLM 调用成本 |

### 1.7 API 端点设计

```
POST /api/analyze
  请求: { apiUsageJson: string, period: string, constraints: object }
  响应: { suggestions: Suggestion[], costReport: CostReport, reasoning: string }

GET /api/model-prices
  响应: { models: ModelPrice[] }
  用途: 返回最新模型价格数据

POST /api/feedback
  请求: { decisionId: string, accepted: boolean, feedback: string }
  用途: 用户反馈，用于 L5 评估优化
```

### 1.8 模型价格数据库

```typescript
// 维护主流 AI 模型的价格数据（每月更新）
const MODEL_PRICES = {
  'gpt-4o':           { input: 2.50, output: 10.00 },  // per 1M tokens
  'gpt-4o-mini':      { input: 0.15, output: 0.60 },
  'gpt-4.1':          { input: 2.00, output: 8.00 },
  'gpt-4.1-mini':     { input: 0.40, output: 1.60 },
  'gpt-4.1-nano':     { input: 0.10, output: 0.40 },
  'claude-sonnet-4':  { input: 3.00, output: 15.00 },
  'claude-haiku-3.5': { input: 0.80, output: 4.00 },
  'gemini-2.0-flash': { input: 0.10, output: 0.40 },
  'gemini-2.5-pro':   { input: 1.25, output: 10.00 },
  'deepseek-v3':      { input: 0.27, output: 1.10 },
  // ...
};
```

---

## Case 2: FlightCompare - 包机询价比价

### 2.1 产品定位

B2B 工具，面向包机经纪人/运营方，替代手动询价流程。

**目标用户**: 公务机经纪公司、企业差旅管理部门
**核心价值**: "2分钟出报价，替代 2小时人工询价"

### 2.2 Goal 示例

```typescript
{
  goalType: 'charter_quote',
  userId: 'broker_007',
  intent: '下周三 5人从上海飞三亚，带高尔夫球具，预算20万以内',
  constraints: {
    departure: 'SHA',
    arrival: 'SYX',
    date: '2026-04-09',
    passengers: 5,
    specialCargo: ['golf_equipment'],
    maxBudgetCny: 200000,
    preferences: {
      directFlight: true,
      aircraftClass: 'midsize',
    },
  },
  sessionId: 'sess_flight_001',
  budget: {
    maxTokens: 30000,
    maxCostUsd: 0.05,
  },
}
```

### 2.3 Skill 清单

| Skill | 类型 | 输入 | 输出 | 预估成本 |
|-------|------|------|------|---------|
| `search-aircraft` | 原子 | 日期+航线+机型 | 可用飞机列表 | 0 (API调用) |
| `calc-reposition` | 原子 | 飞机位置+出发机场 | 调机费用 | 0 (纯计算) |
| `check-empty-legs` | 原子 | 航线+日期 | 匹配的空腿航班 | 0 (API调用) |
| `price-quote` | 原子 | 飞机+航线+服务 | 完整报价单 | ~1000 tokens |
| `check-compliance` | 原子 | 航线+机型+旅客 | 合规检查结果 | 0 (规则匹配) |

#### search-aircraft 详细设计

```
输入:
  - route: { departure: string, arrival: string }
  - date: string (ISO 8601)
  - aircraftClass: 'light' | 'midsize' | 'heavy' | 'ultra-long'
  - minSeats: number
  - suppliers: string[]     // 查询哪些供应商

输出:
  - aircraft: [{
      id: string,
      supplier: string,
      model: string,           // e.g. 'Citation XLS+'
      class: string,
      seats: number,
      currentLocation: string, // 飞机当前位置
      availableDate: string,
      basePrice: number,       // 基础价格 CNY
      features: string[],      // 特殊设备
    }]
```

#### calc-reposition 详细设计

```
输入:
  - aircraft: { currentLocation: string, model: string }
  - departureAirport: string
  - fuelPricePerKg: number

输出:
  - distance: number,          // 调机距离 km
  - flightTime: number,        // 飞行时间 min
  - fuelCost: number,          // 燃油费 CNY
  - repositionFee: number,     // 调机总费 CNY
  - isLocal: boolean,          // 是否本场飞机（无需调机）
```

#### check-empty-legs 详细设计

```
输入:
  - route: { departure: string, arrival: string }
  - date: string
  - flexDays: number          // 允许前后浮动天数

输出:
  - emptyLegs: [{
      id: string,
      aircraft: string,
      originalRoute: string,
      availableDate: string,
      discountPercent: number, // 折扣比例
      price: number,          // 空腿价格 CNY
    }]
```

#### price-quote 详细设计

```
输入:
  - aircraft: object          // search-aircraft 结果
  - repositionCost: number    // calc-reposition 结果
  - route: object
  - passengers: number
  - specialServices: string[] // 餐饮、地面交通等

输出:
  - quote: {
      baseFlight: number,     // 基础飞行费
      repositionFee: number,  // 调机费
      fuelSurcharge: number,  // 燃油附加
      landingFees: number,    // 起降费
      crewCost: number,       // 机组费
      cateringCost: number,   // 餐饮费
      groundTransport: number,// 地面交通
      taxes: number,          // 税费
      totalPrice: number,     // 总价 CNY
      pricePerPerson: number, // 人均价
      validUntil: string,     // 报价有效期
    }
```

### 2.4 Recipe: charter-quote

```
Step 1: [并行] 三路搜索
  |-- search-aircraft (supplier-a)  -> 查供应商A可用飞机
  |-- search-aircraft (supplier-b)  -> 查供应商B可用飞机
  +-- check-empty-legs              -> 查空腿航班匹配

Step 2: calc-reposition
  输入: Step 1 汇总的可用飞机列表
  输出: 每架飞机的调机费用

Step 3: check-compliance
  条件: 跨境航线才执行
  输入: 航线 + 机型 + 旅客信息
  输出: 合规检查结果（不合规的飞机被过滤）

Step 4: price-quote
  输入: 合规飞机 + 调机费 + 服务需求
  输出: 每个方案的完整报价单

Step 5: score-options (内置 Decision Core 打分)
  权重: { price: 0.40, timeMatch: 0.25, aircraftFit: 0.20, reliability: 0.15 }
  输出: Top 3 方案排序
```

### 2.5 多 Agent 编排示意

```
主Agent (charter-coordinator)
|
|-- [并行 spawn]
|   |-- supplier-a-agent
|   |   +-- search-aircraft -> calc-reposition -> price-quote
|   |
|   |-- supplier-b-agent
|   |   +-- search-aircraft -> calc-reposition -> price-quote
|   |
|   +-- empty-leg-agent
|       +-- check-empty-legs -> price-quote (如果有匹配)
|
|-- [汇总]
|   +-- check-compliance (过滤不合规方案)
|
+-- [决策]
    +-- Decision Core 多维打分 -> Top 3 方案 + 推荐理由
```

### 2.6 Decision 权重

```typescript
{ price: 0.40, timeMatch: 0.25, aircraftFit: 0.20, reliability: 0.15 }
```

**维度说明**:
- **price (0.40)**: 总价是否在预算内，越低越好
- **timeMatch (0.25)**: 出发时间是否匹配需求，调机时间是否合理
- **aircraftFit (0.20)**: 机型是否匹配（座位数、货舱、航程）
- **reliability (0.15)**: 供应商可靠性评分、历史准点率

### 2.7 评估指标

| 指标 | 目标 | 测量方式 |
|-----|------|---------|
| 报价采纳率 | > 30% | 客户下单/总报价 |
| 报价响应时间 | < 60s | 从询价到出 Top 3 方案 |
| 价格竞争力 | 偏差 < 5% | vs 人工报价的价格差 |
| 空腿匹配率 | > 10% | 成功匹配空腿的询价比例 |
| 合规准确率 | 100% | 不得遗漏合规问题 |

### 2.8 API 端点设计

```
POST /api/quote
  请求: { departure, arrival, date, passengers, specialCargo, budget, preferences }
  响应: { topOptions: QuoteOption[], reasoning: string, costReport: CostReport }

GET /api/aircraft/:id
  响应: 飞机详细信息

POST /api/quote/:id/accept
  请求: { selectedOptionIndex: number }
  用途: 用户选择方案，触发后续流程

POST /api/feedback
  请求: { quoteId: string, outcome: 'accepted' | 'rejected' | 'modified', feedback: string }
  用途: 反馈到 L5 评估层
```

---

## Case 对比总结

| 维度 | TokenCost | FlightCompare |
|-----|----------|---------------|
| 用户 | AI 开发者 | 包机经纪人 |
| 决策类型 | 分析优化型 | 多方比价型 |
| 核心挑战 | 模型质量/成本 tradeoff | 多供应商并行 + 约束过滤 |
| 数据来源 | 用户上传 API 用量 | 多供应商 API 实时查询 |
| 多Agent需求 | 低（单 pipeline） | 高（多 SubAgent 并行） |
| 实时性要求 | 中（30s） | 高（60s） |
| 框架覆盖层 | L1-L5 全覆盖 | L0-L5 全覆盖（含 Agent Network） |

两个 Case 互补验证框架能力：
- **TokenCost** 验证核心决策链路（L1->L5 单 pipeline）
- **FlightCompare** 验证多 Agent 编排能力（L0 Agent Network + 并行 spawn）

---

## 验证方案

### 单元测试

| 测试文件 | 覆盖模块 | 关键测试点 |
|---------|---------|----------|
| `decision-core.test.ts` | L3 Decision | 给定 goal + candidates -> 验证排序正确性 |
| `goal-parser.test.ts` | L1 Parser | NL -> GoalSchema 解析准确率 |
| `cost-tracker.test.ts` | Cost | token 计数 + budget 阈值触发 |
| `recipe.test.ts` | Skill | pipeline 步骤串联 + 并行执行 |
| `event-bus.test.ts` | L0 Network | 事件发布/订阅 + 类型安全 |

### 集成测试

| 测试场景 | 输入 | 预期输出 | 验证点 |
|---------|------|---------|-------|
| TokenCost 全链路 | API 用量 JSON | 优化建议列表 | 6层串联、成本追踪 |
| FlightCompare 全链路 | 询价请求 | Top 3 报价方案 | 多Agent并行、决策排序 |
| Budget 超限 | 低 budget 设置 | 自动压缩/降级 | 成本管控触发 |
| 空输入处理 | 空/非法输入 | Zod 校验错误 | 错误处理 |

### E2E 测试（Phase 1 后期）

| 测试流程 | 步骤 |
|---------|------|
| TokenCost 基本流程 | 上传用量 -> 等待分析 -> 查看建议 -> 标记采纳 |
| FlightCompare 基本流程 | 输入航线 -> 等待报价 -> 查看 Top 3 -> 选择方案 |

### 框架可用性验证

**目标**: 新开发者 5 分钟内完成 hello-decision 示例运行

**验证步骤**:
1. `git clone` + `pnpm install` (< 60s)
2. 阅读 README 快速上手部分 (< 120s)
3. 运行 `examples/hello-decision` (< 60s)
4. 看到决策结果输出 (< 30s)
5. 理解如何自定义 Skill (< 60s)
