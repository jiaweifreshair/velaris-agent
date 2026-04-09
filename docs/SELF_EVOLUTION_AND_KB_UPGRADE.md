# Velaris 升级说明：自进化 + 个人知识库

更新时间：2026-04-09

## 背景输入

本次升级参考了 3 篇外部技术拆解（Hermes 自进化架构与 Karpathy LLM Wiki 工作流）：

1. https://mp.weixin.qq.com/s/9vfFwCgOF5zMBiCU4nS1Ag  
2. https://mp.weixin.qq.com/s/o1ZN0My8wCsGKSuYNwMAQw  
3. https://mp.weixin.qq.com/s/lTpEajixgv7zLN_ZQQCWLg  

## 设计提炼

### 1) 自进化能力（Hermes 思路）

- 前后台解耦：主链路不阻塞，复盘异步/周期触发。
- 复盘信号以真实结果为准：推荐采纳率、满意度、选择漂移。
- 复盘输出必须结构化：可执行动作 + 优先级 + 报告落盘路径。

### 2) 个人知识库能力（Karpathy 工作流）

- 三层结构：`raw` 原始层 + `wiki` 知识层 + `index` 配置/索引层。
- 三步闭环：`Ingest -> Query -> Lint`。
- 问答回写（file-back）：把高价值回答沉淀为新知识条目。

## 已实现能力

### 自进化

- 新增 `SelfEvolutionEngine`：
  - 基于历史决策计算采纳率、满意度、维度漂移；
  - 生成高/中/低优先级优化动作；
  - 支持报告 JSON 落盘。
- 新增工具 `self_evolution_review`：
  - 可按用户、场景、窗口手动触发复盘。
- 增强 `save_decision`：
  - 默认每 10 条记录触发一次自进化回顾；
  - 在工具返回中带出 `self_evolution` 结构化信息。

### 个人知识库

- 新增 `PersonalKnowledgeBase`：
  - 目录结构：`index.json + raw/*.md + wiki/*.md`；
  - 支持 namespace（按 user_id 隔离）。
- 新增工具：
  - `knowledge_ingest`：摄取资料并编译 wiki 页面；
  - `knowledge_query`：检索并可选问答回写；
  - `knowledge_lint`：断链/孤岛健康检查。

## 测试验证

- 新增测试覆盖：
  - `tests/test_knowledge/test_personal_knowledge_base.py`
  - `tests/test_evolution/test_self_evolution.py`
  - `tests/test_tools/test_knowledge_tools.py`
- 回归验证：
  - `tests/test_memory/test_decision_memory.py`
  - `tests/test_tools/test_core_tools.py`
  - `tests/test_tools/test_lifegoal_tool.py`
  - `tests/test_tools/test_decision_tools.py`
