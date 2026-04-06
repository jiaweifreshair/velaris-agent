---
name: decision
description: 引导 Agent 完成结构化决策流程, 包括偏好召回、数据收集、评分排序和记录保存。
---

# Decision - 结构化决策工作流

当用户需要从多个选项中做出选择时, 使用此工作流。
适用场景: 人生目标决策、商旅方案选择、Token 成本优化、RobotClaw 调度提案、以及任何需要多维权衡的决策。

## 何时使用

- 用户明确表达 "帮我选"、"哪个更好"、"推荐一个" 等决策意图
- 存在多个候选选项需要比较
- 需要在多个维度 (价格、时间、质量等) 之间权衡

## 决策工作流 (5 步)

### Step 1: 召回偏好

在做任何评分之前, 先了解用户的历史偏好。

```
recall_preferences(user_id, scenario)
```

- 获取个性化权重、行为模式、满意度历史
- 如果是新用户 (confidence=0), 使用场景默认权重
- 记下 common_patterns, 它揭示了用户的决策倾向

### Step 2: 召回历史决策

检查用户是否遇到过类似问题。

```
recall_decisions(user_id, scenario, query, limit=5)
```

- 找到相似的历史决策作为参考
- 注意: 用户上次选了什么? 满意度如何?
- 如果上次推荐被拒绝, 本次应调整策略

### Step 3: 收集候选项

使用领域工具获取候选选项:

- 商旅: `travel_recommend` 或 `biz_run_scenario`
- Token 成本: `tokencost_analyze` 或 `biz_run_scenario`
- 调度: `robotclaw_dispatch` 或 `biz_run_scenario`
- 通用: `biz_execute` 完整闭环

确保每个选项都有各维度的评分数据。

### Step 4: 评分排序

使用决策评分工具对候选项排序:

```
decision_score(options, weights, user_id, scenario)
```

- 传入 user_id 和 scenario 自动使用个性化权重
- 如果不传 user_id, 需要显式提供 weights
- 向用户展示排名结果和评分明细, 解释推荐理由

### Step 5: 保存决策

无论用户是否接受推荐, 都要保存决策记录:

```
save_decision(
    user_id, scenario, query,
    recommended, alternatives,
    weights_used, explanation,
    options_discovered, tools_called
)
```

- 记录完整上下文, 供偏好学习使用
- 用户选择了非推荐项时尤其重要 - 这是调整权重的关键信号

## 核心原则

1. **数据先行** - 先召回偏好和历史, 再做推荐。不要凭空猜测用户偏好。
2. **参考历史** - 相似决策的结果是最好的参考。上次被拒绝的推荐不要重复。
3. **解释推理** - 每次推荐都要说明理由: 哪些维度得分高, 为什么选它。
4. **记录一切** - 决策过程的完整记录是偏好学习的燃料。不记录 = 不学习。
5. **尊重选择** - 用户选了非推荐项时, 不要反复劝说。记录下来, 下次调整权重。

## 好的决策行为示例

**场景: 用户第三次选择商旅方案**

```
1. recall_preferences("user-001", "travel")
   -> weights: {price: 0.55, time: 0.30, comfort: 0.15}
   -> patterns: ["偏好price最优 (80%)"]
   -> confidence: 0.6

2. recall_decisions("user-001", "travel", "北京到上海出差")
   -> 上次选了最便宜的航班, 满意度 4.0
   -> 上上次也选了最便宜的, 满意度 3.5

3. [调用 travel_recommend 获取候选航班]

4. decision_score(options, user_id="user-001", scenario="travel")
   -> 个性化权重已自动偏向价格
   -> 推荐: 经济舱直飞 CA1234, 总分 0.87

5. save_decision(...)
   -> 记录完整决策上下文
```

Agent 向用户解释: "根据你过去的选择, 你更看重价格 (权重 55%)。
CA1234 是价格和时间综合最优的方案。如果你不赶时间,
MU5678 更便宜但多耗 1 小时。"
