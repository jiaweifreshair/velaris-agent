# Velaris Agent 验证场景（OpenHarness 二开）

> 目标：用可测量场景验证“路由治理 + 决策执行 + 结果回写”闭环。

## 1. Case A：人生目标决策智能

### 1.1 目标

输入自然语言人生选择，输出可解释的多维推荐，并把本次决策沉淀为后续学习样本。

### 1.2 核心链路

1. `biz_execute`：触发完整闭环，自动识别为 `lifegoal`。
2. `build_capability_plan`：生成场景能力规划、治理要求和推荐工具。
3. `PolicyRouter`：根据风险和复杂度选择 `local_closed_loop`。
4. `run_scenario(lifegoal)`：完成多维评分、排序和推荐解释。
5. `OutcomeStore`：回写 outcome，形成可回放记录。

### 1.3 路由策略建议

- 默认：`local_closed_loop`
- 需要外部副作用或审批：按治理约束升级

### 1.4 验证指标

- 推荐结论可解释，包含维度得分与排序结果
- 结果输出包含 `plan / routing / authority / task / outcome`
- 同类职业选择中，成长型选项可稳定胜出

### 1.5 自动化验证

```bash
uv run python -m pytest tests/test_tools/test_biz_execute_tool.py -q
```

对应断言：

- `query` 自动识别为 `lifegoal`
- 路由命中 `local_closed_loop`
- `recommended.id == "offer-b"`
- 任务账本与 outcome 回写成功

## 2. Case B：商旅 AI 助手

### 2.1 目标

输入自然语言出行需求，输出可解释的机酒组合推荐。

### 2.2 核心链路

1. `parse_intent`：意图解析。
2. `search_flights` + `search_hotels`：并行检索。
3. `recommend`：组合评分与三档推荐（最省/舒适/最优）。

### 2.3 路由策略建议

- 默认：`local_closed_loop`
- 需审计或外部副作用：`delegated_robotclaw`

### 2.4 验证指标

- 推荐可采纳率 >= 60%
- 查询耗时 P95 < 8s
- 组合总价误差 <= 5%

## 3. Case C：AI TokenCost

### 3.1 目标

分析 API 用量，输出可执行降本建议并估算节省空间。

### 3.2 核心链路

1. `analyze_usage`：成本结构识别。
2. `model_compare`：模型质量/成本/时延对比。
3. `optimize_suggest`：建议分级与优先级排序。

### 3.3 路由策略建议

- 默认：`local_closed_loop`
- 写配置/批量执行变更：`delegated_claude_code`

### 3.4 验证指标

- 建议采纳率 >= 60%
- 30 天成本下降 >= 30%
- 质量损失 <= 10%
- 单次分析成本 <= $0.10

## 4. Case D：RobotClaw 运行环境

### 4.1 目标

实现三段式派单协议：意图单 -> 服务提案 -> 交易合约。

### 4.2 核心链路

1. `match_vehicles`：候选运力匹配。
2. `calculate_route`：路径与时效评估。
3. `score_proposals`：多目标打分。
4. `form_contract`：合约生成与审计。

### 4.3 路由策略建议

- 默认：`delegated_robotclaw`
- 涉及代码联动改造：`hybrid_robotclaw_claudecode`

### 4.4 验证指标

- 调度成功率 >= 95%
- 审批命中率可解释（100% 可追踪）
- 越权执行率 = 0

## 5. 通用验收门槛

1. 编译错误 0。
2. Typecheck 0 error。
3. 核心单测通过。
4. 路由决策含 trace 字段。
5. 任务账本完整记录 queued/running/completed 或 failed。

## 6. 当前完成度

- 已完成：`lifegoal / travel / tokencost / robotclaw` 四类场景的能力规划、路由治理、任务账本与 outcome 回写。
- 已验证：`uv run python -m pytest tests/test_tools/test_biz_execute_tool.py -q` 可覆盖 `tokencost` 与 `lifegoal` 两条完整闭环。
- 待完成：更多真实外部 runtime 联调，以及持久化账本和更完整的 outcome 评估体系。
