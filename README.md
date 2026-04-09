<h1 align="center">Velaris Agent</h1>

<p align="center"><strong>Decision Intelligence Agent - 让每次决策都比上一次更好</strong></p>

<p align="center">
  <a href="#-quick-start"><img src="https://img.shields.io/badge/Quick_Start-5_min-blue?style=for-the-badge" alt="Quick Start"></a>
  <a href="#-architecture"><img src="https://img.shields.io/badge/Architecture-Runtime_%2B_Memory-ff69b4?style=for-the-badge" alt="Architecture"></a>
  <a href="#-life-goal-demo"><img src="https://img.shields.io/badge/Demo-LifeGoal_Ready-green?style=for-the-badge" alt="Demo"></a>
  <a href="#-tests"><img src="https://img.shields.io/badge/Tests-Pytest_Verified-brightgreen?style=for-the-badge" alt="Tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-yellow?style=for-the-badge" alt="License"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-%E2%89%A53.10-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Pydantic-v2-e92063?logo=pydantic&logoColor=white" alt="Pydantic">
  <img src="https://img.shields.io/badge/MCP-Protocol-blueviolet" alt="MCP">
  <img src="https://img.shields.io/badge/license-Apache_2.0-blue" alt="License">
  <img src="https://img.shields.io/badge/pytest-locally_verified-brightgreen" alt="Pytest">
  <img src="https://img.shields.io/badge/demo-local_script_ready-orange" alt="Demo">
</p>

---

## What is Velaris?

Velaris 不是一个评分函数, 是一个**会思考的决策 Agent**.

```
传统 agent: 用户提问 -> 调 API -> 返回结果 -> 忘掉一切
Velaris:    用户提问 -> 理解意图 -> 推理需要什么数据 -> 智能获取 ->
            参考历史决策 -> 个性化评分 -> 推荐+解释 -> 记录+学习
```

**核心理念**: Context 是护城河. 同样的 LLM, 谁的上下文更全谁的决策更准.

### 三个设计选择

| 载体 | 选择 | 理由 |
|------|------|------|
| **知识** | Markdown 文件 | 人和 AI 都能读写, 版本可控, 零依赖 |
| **工具集成** | MCP 协议 | 标准互操作, 不锁定供应商 |
| **运行时** | Python 3.10+ | AI/ML 生态最成熟, 类型安全 (Pydantic v2) |

### 开源场景: 人生目标决策智能体 Demo

帮助用户在人生重大决策中做出更好的选择, 覆盖六大领域:

| 领域 | 典型决策 |
|------|----------|
| **Career** 职业 | 该不该跳槽? Offer A 还是 B? 要不要创业? |
| **Finance** 财务 | 该不该买房? 怎么配置资产? 这个投资值不值? |
| **Health** 健康 | 选什么运动? 该不该做这个手术? |
| **Education** 教育 | 该不该读研? 学什么技能最有用? |
| **Lifestyle** 生活 | 要不要搬到另一个城市? 怎么分配时间? |
| **Relationship** 关系 | 该不该合伙? 怎么处理这段关系? |

> Velaris 的决策框架是**通用的** - 人生目标是开源 demo, 同样的引擎可以扩展到任何决策场景.

### 当前开箱可体验的场景

| 场景 | 说明 | 入口 |
|------|------|------|
| **Life Goal** 人生目标 | 职业/财务/健康/教育/生活/关系等重大选择 | `lifegoal_decide` / `scripts/run_lifegoal_demo.py` |
| **Travel** 商旅推荐 | 预算、时效、舒适度权衡 | `travel_recommend` / `biz_execute` |
| **TokenCost** 成本优化 | 模型成本分析与降本建议 | `tokencost_analyze` / `biz_execute` |
| **RobotClaw** 调度治理 | 调度提案评分、合约就绪判断 | `robotclaw_dispatch` / `biz_execute` |
| **Personal KB** 个人知识库 | Ingest / Query / Lint / 问答回写 | `knowledge_ingest` / `knowledge_query` / `knowledge_lint` |

---

## Architecture

<p align="center">
  <img src="assets/architecture-velaris.png" alt="Velaris Decision Intelligence Architecture" width="900">
</p>

### 三层设计

**Layer 1: Agent Loop** - 基于 OpenHarness engine, 流式 LLM 推理 + 多轮工具调用编排. 不写死 pipeline, 让 LLM 自主决定调什么工具、调几次.

**Layer 2: Decision Tools** - 决策、治理和领域工具:
- **记忆类**: 召回用户偏好、检索相似历史决策、保存决策全量记录
- **决策类**: 多维评分 (支持个性化权重)、人生目标决策、业务闭环执行
- **治理类**: 路由策略、能力签发、任务账本、Outcome 回写

**Layer 3: Domain Data Sources** - 可插拔的场景数据源, Agent 自主决定查询哪些源、用什么参数.

### 安全架构（参考 Hermes-Agent 纵深防御）

Velaris 现在把一部分关键安全能力下沉到 `src/openharness/security/`，不再只依赖模型“自觉”：

- **危险命令审批**：`bash` 工具会在真正执行前做危险命令识别，支持 `manual / smart / off` 三档模式
- **会话级审批状态**：危险命令的已审批规则只在当前会话复用，不会跨会话串联放大风险
- **上下文注入扫描**：`AGENTS.md`、`CLAUDE.md`、`.cursorrules`、`.cursor/rules/*` 以及 Issue / PR 上下文在注入系统提示前先做威胁扫描
- **MCP 凭据过滤**：stdio MCP 子进程默认只继承安全环境变量，显式配置的认证变量才会透传
- **敏感输出脱敏**：Shell 输出与 MCP 错误文本在回到模型前统一做密钥/令牌脱敏
- **文件系统边界**：`write_file / edit_file` 会拒绝写入 `.ssh`、`~/.velaris-agent`、`/etc` 等敏感位置；读取敏感配置文件时默认先脱敏
- **输入清洗**：`bash.cwd` / MCP `cwd` 会先经过字符白名单校验，阻断把 shell 元字符塞进工作目录参数的攻击
- **剩余执行链补齐**：`bridge spawn`、后台 `task`、`remote_trigger` 与 command hook 现在也复用同一套命令审批、工作目录校验与输出脱敏逻辑
- **子进程密钥降暴露**：React 前端拉起 backend、以及本地 agent 背景任务，不再把 API Key 放进子进程 argv，改为通过环境变量传递

### 当前代码结构的真实落点

- `src/openharness/`：Agent Loop、工具协议、技能、权限、CLI 等通用运行时
- `src/velaris_agent/biz/engine.py`：场景识别、能力规划、评分与场景执行
- `src/velaris_agent/velaris/`：路由、授权、账本、Outcome 等治理闭环
- `src/velaris_agent/memory/`：决策记忆、偏好学习、个性化权重
- `src/openharness/tools/`：把 lifegoal / travel / tokencost / robotclaw 等能力暴露给 Agent

### 数据飞轮

```
用户使用 -> 决策记录 -> 偏好学习 -> 权重更新 -> 推荐更准 -> 用户更愿意用
```

每次决策都被完整记录 (意图 + 选项 + 推荐 + 用户选择 + 满意度), PreferenceLearner 从实际选择中学习个性化权重. 用的人越多, 推荐越准.

---

## Quick Start

### 环境要求

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (推荐) 或 pip

### 安装

```bash
git clone https://github.com/jiaweifreshair/velaris-agent.git
cd velaris-agent
uv sync --extra dev
```

### 如何运行项目

#### 1. 运行本地人生目标 Demo

这个 Demo 不依赖外部模型，也不需要 API Key。它会自动：

- 预写入 career 历史决策
- 召回用户偏好和相似历史
- 执行一次新的 `lifegoal_decide`
- 保存本次决策结果

```bash
uv run velaris demo lifegoal
uv run velaris demo lifegoal --json
uv run velaris demo lifegoal --save-to out/lifegoal-demo.json
uv run python scripts/run_lifegoal_demo.py
```

其中 `--json` 用于输出结构化 JSON，`--save-to` 会把同一份结果落盘到指定路径，便于做验证留档或二次处理。

#### 2. 运行交互式 Agent

如果你要体验完整的 Agent Loop，需要先配置模型 API Key：

```bash
export ANTHROPIC_API_KEY=your-key-here
uv run velaris
```

#### 3. 单次执行一个问题

适合快速体验人生目标决策或其他场景：

```bash
uv run velaris -p "我收到了两个 offer, A 薪资更高, B 成长性更强, 怎么选?"
uv run velaris -p "帮我查下周三北京到上海的机票"
uv run velaris --model claude-sonnet-4 -p "分析我的 API 成本"
```

### 配置

```bash
# API Key (必需)
export ANTHROPIC_API_KEY=your-key-here

# 可选: 自定义模型
export ANTHROPIC_MODEL=claude-sonnet-4

# 可选: 兼容其他提供商
export ANTHROPIC_BASE_URL=https://your-proxy/v1
```

### 如何运行测试

```bash
# 运行全部测试
uv run python -m pytest tests/ -q

# 只验证人生目标 demo 相关主链
uv run python -m pytest \
  tests/test_memory/test_preference_learner.py \
  tests/test_tools/test_decision_tools.py \
  tests/test_tools/test_lifegoal_tool.py -q
```

---

## Life Goal Demo

### Demo 覆盖了什么

人生目标 demo 当前已经打通了这条主链：

1. `recall_preferences` 读取用户在 `career / finance / health / education / lifestyle / relationship` 领域的历史偏好
2. `recall_decisions` 召回类似人生决策
3. `lifegoal_decide` 基于领域默认权重或个性化权重做多维评分
4. `save_decision` 保存本次推荐，形成后续学习样本

### Demo 命令

```bash
uv run velaris demo lifegoal
uv run velaris demo lifegoal --json
uv run velaris demo lifegoal --save-to out/lifegoal-demo.json
uv run python scripts/run_lifegoal_demo.py
```

### Demo 输出内容

运行后你会看到 4 段结构化输出：

- 偏好召回结果
- 历史决策召回结果
- 本次人生目标决策结果
- 保存结果

### 再次体验时的数据位置

真正的 CLI 决策记录默认保存在：

```bash
~/.velaris/decisions
```

本地 Demo 脚本使用的是临时目录，不会污染你的真实数据。

---

## Decision Tools

### 记忆类

| 工具 | 说明 |
|------|------|
| `recall_preferences` | 召回用户历史偏好 - 个性化权重 + 行为模式 + 满意度 |
| `recall_decisions` | 检索相似历史决策 - "上次类似情况怎么选的, 结果如何" |
| `save_decision` | 保存完整决策快照 - 意图/选项/推荐/权重/工具调用 |

### 决策类

| 工具 | 说明 |
|------|------|
| `lifegoal_decide` | 人生目标决策 - 支持六大领域与个性化权重 |
| `decision_score` | 多维加权评分 - 支持个性化权重自动切换 |
| `score_options` | 通用选项评分 (biz layer) |
| `biz_execute` | 业务闭环执行 (路由 -> 签权 -> 执行 -> 记录) |
| `biz_plan` | 能力规划 (场景识别 + 约束推理) |
| `self_evolution_review` | 自进化复盘 - 基于历史结果给出优化动作 |

### 知识库类

| 工具 | 说明 |
|------|------|
| `knowledge_ingest` | 摄取原始资料并编译为 Wiki 页面 |
| `knowledge_query` | 检索个人知识库并支持问答回写 |
| `knowledge_lint` | 断链/孤岛文档健康检查 |

### 治理类

| 工具 | 说明 |
|------|------|
| `travel_recommend` | 商旅比价推荐 |
| `tokencost_analyze` | AI 成本分析与优化 |
| `robotclaw_dispatch` | RobotClaw 三段式调度 |

### Skill 类

| 工具 | 说明 |
|------|------|
| `skill` | 按需读取技能全文或支持文件 |
| `skill_manage` | 创建 / patch / 编辑 / 删除技能与支持文件 |

---

## Decision Memory

Velaris 的竞争壁垒: 每次决策都被完整记录, 用于未来学习.

```python
# 决策记录结构
DecisionRecord:
  decision_id     # 唯一 ID
  user_id         # 用户
  scenario        # 场景 (travel/tokencost/robotclaw)
  query           # 原始意图
  options_discovered  # 发现的所有选项
  scores          # 评分结果
  weights_used    # 使用的权重 (可能是个性化的)
  recommended     # 系统推荐
  user_choice     # 用户最终选了什么 (反馈回填)
  user_feedback   # 满意度 0-5 (反馈回填)
```

### 偏好学习

```python
# PreferenceLearner 从用户实际选择中学习
# 用户连续5次选了最贵的舒适方案:
#   price 权重: 0.40 -> 0.22
#   comfort 权重: 0.25 -> 0.43
# 第6次直接推荐舒适方案
```

算法: 贝叶斯先验 + 指数衰减 (近期决策权重更大) + 归一化

### 自进化复盘

`save_decision` 会在固定间隔（默认每 10 条）触发一次后台自进化回顾：

- 统计推荐接受率与满意度
- 识别“用户选择 vs 系统推荐”的维度漂移
- 生成可执行动作（例如提升某维度权重、补强解释质量）
- 可通过 `self_evolution_review` 主动触发并落盘报告

---

## Life Goal Example

一个完整的人生决策过程:

```
用户: "我收到了两个 offer, A 公司薪资高但加班多, B 公司薪资一般但发展好, 怎么选?"

Velaris Agent 的决策过程:

1. recall_preferences("user-123", "career")
   -> "这个用户过去偏重成长性(0.35), 不太看重短期收入(0.18)"

2. recall_decisions("user-123", "career", "offer 选择")
   -> "去年选了成长性更好的 offer, 满意度 4.5/5"

3. lifegoal_decide(domain="career", options=[
     {id: "A", dimensions: {income: 0.9, growth: 0.5, balance: 0.3}},
     {id: "B", dimensions: {income: 0.6, growth: 0.9, balance: 0.7}}
   ], user_id="user-123")
   -> 使用个性化权重: growth=0.35 > income=0.18
   -> 推荐 B (总分 0.72 vs A 的 0.58)

4. save_decision(推荐B, 用户最终选了B, 3个月后满意度4.8)
   -> 下次类似决策, 权重更精准

输出:
  "推荐选择 B 公司. 基于你的历史偏好, 你更看重长期成长而非短期薪资.
   去年类似选择的结果也印证了这一点 (满意度 4.5).
   B 公司在成长性(0.9)和工作生活平衡(0.7)上明显优于 A.
   建议 3 个月后回顾这个决策."
```

---

## Harness Infrastructure

继承自 OpenHarness 的 10 子系统基础设施:

| 子系统 | 说明 |
|--------|------|
| **Engine** | 核心 agent 循环 - 流式 LLM + 工具调用编排 |
| **Tools** | OpenHarness 内置工具 + Velaris 决策/治理/领域工具, BaseTool 抽象 |
| **Skills** | Markdown 知识注入, 引导 Agent 行为 |
| **Plugins** | 插件发现/加载/生命周期, plugin.json manifest |
| **Permissions** | 多级权限 (tool/file/command), 3 种模式 |
| **Hooks** | 生命周期事件 (session/tool use), 支持 command/http/prompt |
| **Memory** | 持久化跨会话记忆 + 决策记忆 |
| **Swarm** | 多 agent 协调, subprocess/in-process 后端 |
| **Tasks** | 后台任务管理, shell/agent 任务 |
| **MCP** | Model Context Protocol 工具集成 |

---

## Skill System

Velaris 现在采用 Hermes 风格的技能沉淀架构，而不是“做完立刻硬编码保存”：

1. 前台引导：系统提示会注入 `SKILLS_GUIDANCE`，提醒模型在复杂任务（如 5+ 次工具调用、棘手错误修复、非平凡工作流）后考虑沉淀技能。
2. 索引层加载：系统提示只注入技能索引（名称 + 描述），避免把完整技能内容塞进前缀。
3. 按需层加载：当用户输入 `/skill-name`，或模型显式调用 `skill(name="...")` 时，完整技能内容才会作为用户消息注入。
4. 后台 Review：主任务完成后，如果工具调用次数达到阈值，Engine 会 fork 一个静默 review 回合，只暴露 `skill` + `skill_manage`，best-effort 地创建或修补技能。

### 用户技能目录

```bash
~/.velaris-agent/skills/
```

支持两种格式：

- 旧格式：`~/.velaris-agent/skills/my-skill.md`
- 新格式：`~/.velaris-agent/skills/my-skill/SKILL.md`

新格式还支持：

- `references/`
- `templates/`
- `scripts/`
- `assets/`

---

## Tests

```bash
# 全量测试
uv run python -m pytest tests/ -q

# Demo 主链测试
uv run python -m pytest \
  tests/test_memory/test_preference_learner.py \
  tests/test_tools/test_decision_tools.py \
  tests/test_tools/test_lifegoal_tool.py \
  tests/test_biz/test_router_config.py \
  tests/test_biz/test_orchestrator.py -q
```

---

## Project Structure

```
velaris-agent/
├── src/
│   ├── openharness/              # 基础设施 (OpenHarness engine)
│   │   ├── engine/               # Agent 循环
│   │   ├── tools/                # 内置工具 + 决策工具 + demo 工具注册
│   │   ├── skills/bundled/       # Markdown 知识文件
│   │   ├── plugins/              # 插件系统
│   │   ├── permissions/          # 权限管理
│   │   ├── hooks/                # 生命周期钩子
│   │   ├── memory/               # 基础记忆系统
│   │   ├── swarm/                # 多 agent 协调
│   │   ├── mcp/                  # MCP 协议集成
│   │   └── ...
│   └── velaris_agent/            # 业务层
│       ├── memory/               # 决策记忆 + 偏好学习
│       ├── velaris/              # 治理运行时 (router, authority, ...)
│       ├── biz/                  # 场景引擎
│       ├── adapters/             # 数据源适配
│       └── scenarios/
│           ├── lifegoal/         # 人生目标决策 demo
│           └── robotclaw/        # RobotClaw 场景协议与治理
├── tests/                        # pytest 测试集
├── config/                       # 路由策略 YAML
├── docs/                         # 技术方案 + 架构文档
├── frontend/                     # 终端与前端实验
├── scripts/                      # 本地 demo / 开发脚本
└── pyproject.toml
```

---

## Extending Velaris

### 添加新的 Decision Tool

```python
from openharness.tools.base import BaseTool, ToolResult, ToolExecutionContext
from pydantic import BaseModel, Field

class MyToolInput(BaseModel):
    query: str = Field(description="搜索查询")

class MyTool(BaseTool):
    name = "my_tool"
    description = "我的自定义决策工具"
    input_model = MyToolInput

    async def execute(self, args: MyToolInput, context: ToolExecutionContext) -> ToolResult:
        result = await do_something(args.query)
        return ToolResult(output=json.dumps(result))

    def is_read_only(self, args: MyToolInput) -> bool:
        return True
```

### 添加新的 Skill (Markdown 知识)

创建 `~/.velaris/skills/my-skill.md`:

```markdown
---
name: my-skill
description: 我的自定义决策流程
---

# My Skill

## When to use
当用户需要...

## Workflow
1. 先做...
2. 然后...
3. 最后...
```

### 添加 MCP Server

在 `~/.velaris/settings.json`:

```json
{
  "mcp_servers": {
    "my-server": {
      "command": "npx",
      "args": ["-y", "my-mcp-server"]
    }
  }
}
```

---

## Contributing

参见 [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
# 开发环境
uv sync --extra dev

# 测试
uv run pytest tests/ -v

# Lint
uv run ruff check src tests

# 类型检查
uv run mypy src/velaris_agent
```

---

## License

[Apache-2.0](LICENSE)

---

<p align="center">
  <strong>Context is the moat. Every decision makes the next one better.</strong>
</p>
