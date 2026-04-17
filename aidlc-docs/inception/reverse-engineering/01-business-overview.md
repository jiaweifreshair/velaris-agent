# 业务概览

## 项目名称
Velaris Agent — Decision Intelligence Runtime（决策智能运行时）

## 项目定位
Velaris 是一个**目标驱动的决策智能运行时**，为 AI 智能运营商提供基座引擎。它不是通用 Agent 框架，也不是自改进 Agent，而是让 Agent 的决策过程**可控、可审计、可回放、可学习**的基座引擎。

## 核心价值主张
- **决策过程即资产**：同样的 LLM，谁的决策上下文更完整、治理更显式、学习闭环更紧，谁的决策就更准
- **三方决策主体**：用户决策 + 组织决策 + 用户-组织关系对齐
- **偏差纠正**：自动检测近因偏差、锚定效应、损失厌恶等认知偏差
- **决策环境快照**：不只记录"推荐了什么"，而是记录"在什么环境下、基于什么变量、做出了什么决策"

## 业务场景

### 已实现场景
| 场景　　　　　　　　　　　| 说明　　　　　　　　　　　　　　　　　　| 入口工具　　　　　　　　　　　　　　　　　　　　　　　　　|
| ---------------------------| -----------------------------------------| -----------------------------------------------------------|
| Life Goal（人生目标）　　 | 职业/财务/健康/教育/生活/关系等重大选择 | `lifegoal_decide`　　　　　　　　　　　　　　　　　　　　 |
| Travel（商旅推荐）　　　　| 预算、时效、舒适度权衡，支持提案确认流　| `travel_recommend` / `travel_compare`　　　　　　　　　　 |
| TokenCost（成本优化）　　 | 模型成本分析与降本建议　　　　　　　　　| `tokencost_analyze`　　　　　　　　　　　　　　　　　　　 |
| RobotClaw（调度治理）　　 | 调度提案评分、合约就绪判断　　　　　　　| `robotclaw_dispatch`　　　　　　　　　　　　　　　　　　　|
| Procurement（采购决策）　 | 供应商评估、多维评分　　　　　　　　　　| `biz_execute`　　　　　　　　　　　　　　　　　　　　　　 |
| Personal KB（个人知识库） | 资料摄取 / 检索 / 健康检查　　　　　　　| `knowledge_ingest` / `knowledge_query` / `knowledge_lint` |

### 业务事务流程
```
用户目标 → 意图识别(infer_scenario)
         → 能力规划(build_capability_plan)
         → 策略路由(PolicyRouter.route)
         → 能力签发(AuthorityService.issue_plan)
         → 任务创建(TaskLedger.create_task)
         → 场景执行(run_scenario)
         → 结果记录(OutcomeStore.record)
         → 决策保存(DecisionMemory.save)
         → 偏好学习(PreferenceLearner.compute_preferences)
         → 自进化复盘(SelfEvolutionEngine.review)
```

## 决策主体模型

### 用户决策 (UserPreferences)
- 个性化权重（从历史选择中学习）
- 行为模式（"偏好最低价"、"预算敏感"）
- 已识别的偏差倾向（recency_bias、loss_aversion 等）

### 组织决策 (OrgPolicy)
- 组织层面的评分权重
- 硬约束（预算上限、合规要求）
- 偏差纠正方向

### 用户-组织关系 (AlignmentReport)
- 总体对齐度 0-1
- 冲突点（哪些维度分歧大）
- 协同点（哪些维度一致）
- 协商空间（双方各让多少）

## 开源 Demo
人生目标决策智能体，覆盖六大领域：Career、Finance、Health、Education、Lifestyle、Relationship。
