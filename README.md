<h1 align="center">Velaris Agent</h1>

<p align="center"><strong>Decision Intelligence Runtime — AI 智能运营商的基座引擎</strong></p>

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

Velaris 不是一个评分函数，也不是又一个 Agent 框架。它是一个**目标驱动的决策智能运行时**，为 AI 智能运营商提供基座引擎。

```
通用 Agent 框架:  用户提问 -> 调 API -> 返回结果 -> 忘掉一切
自改进 Agent:     用户提问 -> 执行任务 -> 沉淀技能 -> 下次执行更快
Velaris:          用户目标 -> 理解意图 -> 自主抓取数据 -> 参考历史决策 ->
                  个性化评分 -> 推荐+解释 -> 快照决策环境 -> 学习偏好
```

**核心理念**: 决策过程本身是资产。同样的 LLM，谁的决策上下文更完整、治理更显式、学习闭环更紧，谁的决策就更准。

### 基座引擎定位

Velaris 解决的不是"让 Agent 能干活"或"让 Agent 越干越好"，而是**让 Agent 的决策过程可控、可审计、可回放、可学习**。

决策引擎覆盖三类决策主体及其关系：

| 主体 | 说明 | 引擎能力 |
|------|------|----------|
| **用户决策** | 个人在具体场景中的选择和偏好 | 偏好学习 + 偏差检测 + 个性化权重 |
| **组织决策** | 公司/平台层面的策略、约束、合规要求 | OrgPolicy + 组织权重 + 硬约束 |
| **用户-组织关系** | 两者之间的匹配度、冲突点、协商空间 | AlignmentReport + 融合权重 + 协商建议 |

目标是：
- **更了解自己的决策** — 通过决策环境快照和偏好画像，量化"我在什么情况下倾向于怎么选"
- **纠正不合理的偏差** — AI 检测近因偏差、锚定效应、损失厌恶等认知偏差，给出纠正建议
- **持续改进决策能力** — 追踪决策曲线（接受率、满意度、偏差次数、权重稳定性），量化进步
- **优化决策曲线** — 每次决策都让下一次更好，直到权重趋于稳定、偏差趋于零

决策目标是确定的，但可以重新设定。外部变量（市场、价格、政策等）是动态变化的，Agent 每次决策时自主抓取最新数据。

### 与 Hermes、OpenClaw 的区别

| 维度 | OpenClaw | Hermes | Velaris |
|------|----------|--------|---------|
| **定位** | 通用自主 Agent 框架 | 自我改进的 AI 队友 | 决策智能运行时 / 基座引擎 |
| **核心创新** | Gateway + ReAct 循环 + 社区技能生态 | 闭环学习（技能自创建 + 自改进） | 治理闭环（路由 + 授权 + 账本 + Outcome + 决策快照） |
| **学习对象** | 无（技能是静态的） | 技能级（完成任务后自动写技能） | 决策级（用户偏好 + 组织策略 + 偏差纠正） |
| **治理模型** | 基本无（prompt 级约束） | 轻量（权限 + 审批） | 显式策略路由 + 能力令牌 + 任务账本 + 停止条件 |
| **决策主体** | 单一（用户） | 单一（用户） | 三方（用户 + 组织 + 关系对齐） |
| **偏差纠正** | 无 | 无 | 自动检测认知偏差 + 纠正建议 |
| **数据获取** | Agent 自主调用工具 | Agent 自主调用工具 | Agent 自主调用工具 + 决策环境快照 |
| **决策可回放** | 否 | 否 | 是（完整环境快照 + 路由 trace + outcome） |
| **适用场景** | 个人助手、内容自动化 | 长期 AI 助手、需要持续改进 | 需要决策审计、治理合规、多场景路由的业务系统 |

一句话总结：OpenClaw 让 Agent 能干活，Hermes 让 Agent 越干越好，Velaris 让 Agent 的决策过程可控可审计可学习。

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
| **Travel** 商旅推荐 | 预算、时效、舒适度权衡，支持提案确认流 | `travel_recommend` / `travel_compare` / `biz_execute` |
| **TokenCost** 成本优化 | 模型成本分析与降本建议 | `tokencost_analyze` / `biz_execute` |
| **RobotClaw** 调度治理 | 调度提案评分、合约就绪判断 | `robotclaw_dispatch` / `biz_execute` |
| **Personal KB** 个人知识库 | Ingest / Query / Lint / 问答回写 | `knowledge_ingest` / `knowledge_query` / `knowledge_lint` |

---

## Architecture

<p align="center">
  <img src="assets/architecture-velaris.png" alt="Velaris Decision Intelligence Architecture" width="900">
</p>

### 五层 + 学习闭环设计

```
L0  Agent Runtime        OpenHarness engine — LLM 推理 + 工具调用编排
L1  Goal-to-Plan         场景识别（ScenarioRegistry 插件化）→ 能力规划 → 治理约束生成
L2  Routing & Governance  DynamicRouter 四层路由 → 能力签发 → 停止条件
L3  Decision Execution    多维评分 + 场景执行 + 数据自主抓取
L4  Runtime Control       OpenViking 上下文数据库 + 任务账本 + Outcome 回写 + 决策环境快照
──  Learning Loop         决策记忆 + 偏好学习 + 语义召回 + 自进化 + Token Economics (贯穿全层)
```

**Layer 0: Agent Loop** — 基于 OpenHarness engine，流式 LLM 推理 + 多轮工具调用编排。不写死 pipeline，让 LLM 自主决定调什么工具、调几次。

**Layer 1: Goal-to-Plan Compiler** — `build_capability_plan()` 把自然语言目标编译为结构化 plan（场景、能力集、权重、治理约束、推荐工具链）。`ScenarioRegistry` 插件化管理场景，新场景通过 SKILL.md 声明即可注册，无需改 engine.py。

**Layer 2: Routing & Governance** — `DynamicRouter` 四层路由引擎（规则匹配 → 场景语义 → 成本约束 → 降级兜底），替代静态 YAML 规则，运行时感知成本、负载、SLA 等指标动态调整路由权重。`AuthorityService` 签发短时能力令牌。

**Layer 3: Decision Execution** — Agent 通过工具自主抓取决策所需数据（机票价格、模型成本、车辆状态等），然后执行多维评分和场景逻辑。数据不需要预置，Agent 自己获取。

**Layer 4: Runtime Control** — `OpenViking` 上下文数据库提供统一的上下文存储与检索（`viking://` URI scheme + L0/L1/L2 三层渐进加载），`TaskLedger` 跟踪执行状态，`OutcomeStore` 回写结果，决策环境快照记录完整决策上下文。

**Learning Loop** — 贯穿全层：`DecisionMemory` 存储完整决策记录，`PreferenceLearner` 从用户实际选择中学习个性化权重（贝叶斯先验 + 指数衰减），`SemanticRecallEngine` 语义召回相似历史决策，`SkillEvolutionLoop` 技能自进化（collect_feedback → learn → validate → deploy 四步闭环），`CostOptimizer` Token 经济学优化（加载分级 + 模型推荐 + 预算门控），`SelfEvolutionEngine` 定期复盘并联动成本追踪。

### 决策环境快照（Decision Context Snapshot）

Velaris 的核心差异化之一：不只记录"推荐了什么"，而是记录"在什么环境下、基于什么变量、做出了什么决策"。

每次决策完成后，系统自动快照以下信息：

| 快照类别 | 包含内容 | 用途 |
|----------|----------|------|
| **环境变量** | 原始意图、结构化 intent、Agent 抓取到的所有候选项、过滤后候选项 | 回放决策当时的信息环境 |
| **决策变量** | 使用的权重（可能是个性化的）、每个选项每个维度的评分明细、调用了哪些工具 | 解释为什么推荐这个 |
| **治理变量** | 路由 trace（评估了哪些规则、命中了哪条）、能力令牌、任务状态变迁、outcome 指标 | 审计合规 |
| **输出快照** | 系统推荐、备选方案、推荐理由 | 对比分析 |
| **反馈数据** | 用户最终选择、满意度 0-5、结果备注 | 偏好学习输入 |

这套快照机制使得：
- **回放**：任何历史决策都可以还原当时的完整上下文
- **审计**：治理链路（路由 → 授权 → 执行 → 结果）全程可追溯
- **学习**：`PreferenceLearner` 从 `user_choice` vs `recommended` 的差异中学习权重调整
- **对比**：同一用户在不同时间点对同类问题的决策环境变化可量化

### 数据获取策略

决策过程中需要的各种数据由 Agent 自主获取，不需要预置：

```
Agent 收到目标
  → build_capability_plan 识别需要什么数据
  → Agent 自主选择工具（web_search / 领域 API / MCP server）
  → 抓取候选项数据
  → 数据进入 DecisionRecord.options_discovered
  → 评分、路由、执行
  → 完整环境快照落盘
```

Velaris 不关心数据从哪来，关心的是：拿到数据之后，怎么评分、怎么路由、怎么治理、怎么记住这次决策环境。

### 安全架构

Velaris 把关键安全能力下沉到 `src/openharness/security/`，不依赖模型"自觉"：

- **危险命令审批**：`bash` 工具执行前做危险命令识别，支持 `manual / smart / off` 三档
- **会话级审批状态**：已审批规则只在当前会话复用，不跨会话串联
- **上下文注入扫描**：`AGENTS.md`、`.cursorrules` 等在注入系统提示前先做威胁扫描
- **MCP 凭据过滤**：stdio MCP 子进程默认只继承安全环境变量
- **敏感输出脱敏**：Shell 输出与 MCP 错误文本统一做密钥/令牌脱敏
- **文件系统边界**：拒绝写入 `.ssh`、`~/.velaris-agent`、`/etc` 等敏感位置
- **输入清洗**：`bash.cwd` / MCP `cwd` 经过字符白名单校验

详细设计见 `docs/SECURITY-EXECUTION-HARDENING.md`。

### 当前代码结构

- `src/openharness/`：Agent Loop、工具协议、技能、权限、CLI 等通用运行时
- `src/velaris_agent/biz/engine.py`：场景识别、能力规划、评分与场景执行
- `src/velaris_agent/velaris/`：路由（DynamicRouter 四层路由）、授权、账本、Outcome 等治理闭环
- `src/velaris_agent/memory/`：决策记忆、偏好学习、语义召回（SemanticRecallEngine）
- `src/velaris_agent/evolution/`：技能自进化（SkillEvolutionLoop）、Token 经济学（CostOptimizer）、自进化引擎
- `src/velaris_agent/context/`：OpenViking 上下文数据库（viking:// URI + L0/L1/L2 渐进加载）
- `src/velaris_agent/scenarios/`：ScenarioRegistry 插件化场景（SKILL.md 声明式注册）
- `src/openharness/tools/`：把 lifegoal / travel / tokencost / robotclaw 等能力暴露给 Agent

### 数据飞轮

```
用户目标 → Agent 自主抓取数据 → 决策环境快照 → 偏好学习 + 语义召回 → 权重更新 → 推荐更准
                                              ↓
                                    SkillEvolutionLoop → 技能自进化
                                    CostOptimizer → Token 经济学优化
```

每次决策的完整环境（意图 + 抓取到的数据 + 评分 + 路由 trace + 用户选择 + 满意度）都被快照记录。PreferenceLearner 从实际选择中学习个性化权重，SemanticRecallEngine 语义召回相似历史，SkillEvolutionLoop 闭环进化技能，CostOptimizer 优化 Token 开销。用的人越多，推荐越准、成本越低。

### Velaris 2.0 开发进度（UOW 全完成 ✅）

| UOW | 名称 | 状态 | 核心交付 |
|-----|------|------|----------|
| UOW-1 | Architecture Boundary | ✅ | ExecutionContract + PersistenceBarrier + Envelope-first 输出 |
| UOW-4 | OpenViking Context DB | ✅ | viking:// URI + L0/L1/L2 渐进加载 + Local/HTTP 双模式 |
| UOW-5 | ScenarioRegistry | ✅ | SKILL.md 插件化 + discover/match/reload + 消除 5 个硬编码字典 |
| UOW-6 | DynamicRouter | ✅ | 四层路由（规则/语义/成本/降级）+ DecisionCostTracker |
| UOW-7 | Semantic Recall | ✅ | SemanticRecallEngine + HybridRecall + 相似决策召回 |
| UOW-8 | Token Economics | ✅ | SkillEvolutionLoop + CostOptimizer + LoadingTier 分级优化 |

### 基座引擎能力全景

| 能力 | 状态 | 实现 |
|------|------|------|
| Goal → Plan 编译 | ✅ | `build_capability_plan()` + ScenarioRegistry 插件化场景识别 |
| OpenViking 上下文 | ✅ | `viking://` URI scheme + L0_SUMMARY/L1_CONTEXT/L2_FULL 渐进加载 |
| 四层动态路由 | ✅ | DynamicRouter：规则匹配 → 场景语义 → 成本约束 → 降级兜底 |
| 能力签发 | ✅ | `AuthorityService` 短时令牌 |
| 任务跟踪 | ✅ | `TaskLedger` 状态机 |
| Outcome 回写 | ✅ | `OutcomeStore` 结果记录 |
| 决策记忆 | ✅ | SQLite（`SqliteDecisionMemory`）+ OpenViking 上下文数据库双存储 |
| 语义召回 | ✅ | `SemanticRecallEngine` 向量 + 关键词混合召回 |
| 偏好学习 | ✅ | `PreferenceLearner` 贝叶斯先验 + 指数衰减 |
| 技能自进化 | ✅ | `SkillEvolutionLoop` collect→learn→validate→deploy 四步闭环 |
| Token 经济学 | ✅ | `CostOptimizer` 加载分级 + 模型推荐 + 预算门控 |
| 安全纵深防御 | ✅ | 命令审批 + 凭据过滤 + 输出脱敏 + 文件边界 |
| Skills Hub | ✅ | 多源发现 + 安全扫描 + 锁文件 + CLI |

### 作为基座引擎的下一步方向

| 方向 | 当前状态 | 目标状态 | 优先级 |
|------|----------|----------|--------|
| **多租户隔离** | 单用户 session 级 | tenant 级隔离（决策记忆、偏好、路由策略独立） | P0 |
| **Outcome 聚合分析** | 单条记录查询 | 跨场景、跨时间段的 outcome 聚合统计和趋势分析 | P1 |
| **快照对比与回放 API** | 快照数据已落盘，但缺少结构化查询和对比接口 | 提供 diff API：同用户不同时间点的决策环境变化可量化 | P1 |
| **运行时指标驱动路由** | DynamicRouter 已支持四层路由，成本维度已接入 | 接入负载/SLA/可用性等更多运行时指标 | P2 |

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

安装后可用入口如下：

- `velaris` / `vl`：Velaris Agent 官方入口，品牌保持不变
- `oh` / `openharness`：OpenHarness 兼容入口，便于迁移已有脚本与习惯

- 默认交互入口是 React 终端 UI；`velaris` 首次启动时如果 `frontend/terminal` 下还没有前端依赖，会自动执行 `npm install`。
- 如果你只想单独开发前端，进入 `frontend/terminal` 后运行 `npm start` 即可。

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

如果你要体验完整的 Agent Loop，推荐先用统一的 provider / auth 流程完成初始化：

```bash
uv run velaris setup anthropic --model claude-sonnet-4 --use-env
uv run velaris
```

如果你已经设置好环境变量，也可以直接启动：

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

#### 4. Provider / 鉴权快速配置

Velaris 在运行时能力上持续向 OpenHarness 对齐，但品牌入口保持为 `Velaris Agent`。当前支持 Anthropic 与多种 OpenAI-compatible provider（如 OpenAI、Moonshot、DashScope、Gemini、DeepSeek、OpenRouter、Groq 等）。

```bash
# 查看内置 provider 预设
uv run velaris provider list

# 查看当前生效 provider / model / base_url / 鉴权来源
uv run velaris provider current
uv run velaris auth status

# 切换 provider 预设
uv run velaris provider use moonshot
uv run velaris auth switch anthropic

# 配置鉴权：写入 settings.json
uv run velaris auth login moonshot --api-key sk-your-key

# 配置鉴权：仅使用环境变量，不落盘
uv run velaris auth login moonshot --use-env

# OpenAI 授权模式：可以直接写入 settings.json，或只依赖环境变量
uv run velaris setup openai --model gpt-5.4 --use-env
uv run velaris auth login openai --api-key sk-your-key
uv run velaris auth login openai --use-env

# 如果你已经执行过 `codex login`，OpenAI provider 也可以直接复用
# `~/.codex/auth.json` 中的 OPENAI_API_KEY（只读回退，不写入 Velaris 配置）
uv run velaris auth switch openai
uv run velaris auth status

# 一次性完成 provider + model + 鉴权方式初始化
uv run velaris setup moonshot --model kimi-k2 --use-env

# 清除本地持久化 API Key
uv run velaris auth logout
```

在 REPL / TUI 中也有对应 slash command：

```text
/provider current
/provider use moonshot
/auth status
/auth switch anthropic
/auth switch openai
/login moonshot sk-your-key
/login openai sk-your-key
/logout
```

### 配置

```bash
# Anthropic provider
export ANTHROPIC_API_KEY=your-key-here
export ANTHROPIC_MODEL=claude-sonnet-4
export ANTHROPIC_BASE_URL=https://your-proxy/v1

# OpenAI-compatible provider（示例：Moonshot / OpenAI）
export MOONSHOT_API_KEY=your-key-here
export OPENAI_API_KEY=your-key-here

# 也可以显式指定运行时 provider / API 形态
export VELARIS_PROVIDER=moonshot
export VELARIS_API_FORMAT=openai_compat
export VELARIS_BASE_URL=https://api.moonshot.ai/v1
```

> 说明：`VELARIS_*` 与 `OPENHARNESS_*` 环境变量前缀都可用，用于兼容 OpenHarness 组件迁移；对外品牌与默认入口仍然是 Velaris。
>
> 补充：当当前 provider 为 `openai` 且没有显式 `api_key`、没有命中环境变量时，
> Velaris 会只读回退到 `~/.codex/auth.json` 中的 `OPENAI_API_KEY`。
> 可以先执行 `codex login`，再通过 `uv run velaris auth status` 确认来源是否显示为
> `codex:~/.codex/auth.json#OPENAI_API_KEY`。
> 这条回退目前只对 `openai` provider 生效，不会自动把 Codex 的 OpenAI key 复用到
> `moonshot`、`dashscope`、`gemini` 等 vendor-specific OpenAI-compatible provider。

### 如何运行测试

```bash
# 运行全部测试
./scripts/run_pytest.sh tests/ -q

# 只验证人生目标 demo 相关主链
./scripts/run_pytest.sh \
  tests/test_memory/test_preference_learner.py \
  tests/test_tools/test_decision_tools.py \
  tests/test_tools/test_lifegoal_tool.py \
  tests/test_biz/test_engine_hotel_biztravel.py \
  tests/test_biz/test_hotel_biztravel_inference.py -q
```

> Apple Silicon 说明：仓库内 `.venv/bin/python` 可能默认以 `x86_64` 启动，`./scripts/run_pytest.sh` 会优先强制使用 arm64 解释器，避免 `pydantic_core` 一类二进制依赖出现架构不兼容。

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

## Hotel / Biztravel Shared Decision Demo

### Demo 覆盖了什么

酒店 / 商旅共享决策 demo 当前已经打通这条主链：

1. `hotel_biztravel` 场景识别后进入共享决策内核，而不是继续走普通 travel 平面排序
2. `domain_rank` 输出同类候选店铺摘要、低置信度需求推断和写回提示
3. `bundle_rank` 输出跨类 bundle 摘要、联合排序结果和结构化决策依据
4. 用户确认后把真实选择回写到 `DecisionMemory`，供后续 `recall_preferences` 和 `PreferenceLearner` 继续学习

### 设计原则

- 同类问题只给候选集，不把 supplier 私有协议暴露给决策层
- 跨类问题先由确定性的 bundle planner 做硬约束过滤，再交给共享决策内核排序
- `save_decision` 只记录真实选择和可解释上下文，不把隐式推断写进知识库

### 对应测试

- `tests/test_biz/test_engine_hotel_biztravel.py`
- `tests/test_biz/test_hotel_biztravel_inference.py`
- `tests/test_memory/test_preference_learner.py`

---

## Decision Tools

### 记忆与召回类

| 工具 | 说明 |
|------|------|
| `recall_preferences` | 召回用户历史偏好 - 个性化权重 + 行为模式 + 满意度 |
| `recall_decisions` | 检索相似历史决策 - "上次类似情况怎么选的, 结果如何" |
| `semantic_recall` | 语义召回相似决策 — 向量 + 关键词混合检索（UOW-7） |
| `save_decision` | 保存完整决策快照 - 意图/候选摘要/推荐/权重/工具调用/写回提示 |

### 决策类

| 工具 | 说明 |
|------|------|
| `lifegoal_decide` | 人生目标决策 - 支持六大领域与个性化权重 |
| `decision_score` | 多维加权评分 - 支持个性化权重自动切换 |
| `score_options` | 通用选项评分 (biz layer) |
| `biz_execute` | 业务闭环执行 (路由 -> 签权 -> 执行 -> 记录) |
| `biz_plan` | 能力规划 (场景识别 + 约束推理) |
| `self_evolution_review` | 自进化复盘 - 基于历史结果给出优化动作 |

### Token Economics 类（UOW-8）

| 工具 | 说明 |
|------|------|
| `cost_optimize` | Token 成本优化建议 - 加载分级 + 模型推荐 + 预算门控 |
| `evolution_feedback` | Skill 进化反馈收集 - 质量评分 + 用户满意度 → 驱动 SkillEvolutionLoop |

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

## Decision Memory & Context Snapshot

Velaris 的竞争壁垒: 每次决策的完整环境都被快照记录, 用于回放、审计和学习.

### 三类决策主体

```python
# 用户决策: 个人偏好和选择
UserPreferences:
  weights           # 个性化权重 (从历史选择中学习)
  common_patterns   # 行为模式 ("偏好最低价", "预算敏感")
  known_biases      # 已识别的偏差倾向 ("recency_bias", "loss_aversion")

# 组织决策: 公司/平台策略
OrgPolicy:
  weights           # 组织层面的评分权重
  constraints       # 硬约束 (预算上限、合规要求)
  bias_corrections  # 组织希望纠正的偏差方向

# 用户-组织关系: 对齐分析
AlignmentReport:
  alignment_score   # 总体对齐度 0-1
  conflicts         # 冲突点 (哪些维度分歧大)
  synergies         # 协同点 (哪些维度一致)
  negotiation_space # 协商空间 (双方各让多少)
```

### 决策环境快照

```python
DecisionRecord:
  # 主体与目标
  user_id / org_id      # 谁在决策
  active_goals          # 关联的目标 ID

  # 环境变量快照 — 动态变化的外部条件
  env_snapshot          # {'market_trend': 'up', 'season': 'peak'}
  options_discovered    # Agent 自主抓取到的所有候选项
  tools_called          # 调用了哪些工具获取数据

  # 决策变量快照
  weights_used          # 用户个性化权重
  org_weights_applied   # 组织策略权重
  scores                # 评分明细

  # 偏差检测
  detected_biases       # AI 检测到的认知偏差
  bias_correction_applied  # 是否应用了纠正

  # 输出 + 反馈
  recommended / user_choice / user_feedback
```

### 偏差检测与纠正

AI 通过分析历史决策模式，自动识别不合理的决策偏差：

| 偏差类型 | 检测方式 | 纠正建议 |
|----------|----------|----------|
| **近因偏差** (recency) | 最近 N 次选择高度相似 | 重新评估其他候选项 |
| **锚定效应** (anchoring) | 总是选第一个出现的选项 | 评分后再选，不受展示顺序影响 |
| **损失厌恶** (loss_aversion) | 过度选择最保守选项 | 适当平衡风险和收益 |
| **沉没成本** (sunk_cost) | 因历史投入继续选同类 | 基于当前价值重新评估 |

### 决策曲线

追踪决策能力随时间的变化，量化"越来越好"：

```python
DecisionCurvePoint:
  period              # 时间段 ("2026-Q1")
  decision_count      # 决策数量
  acceptance_rate     # 推荐接受率 (越高说明推荐越准)
  avg_satisfaction    # 平均满意度
  bias_count          # 偏差次数 (越少越好)
  alignment_score     # 与组织对齐度
  weight_stability    # 权重稳定性 (趋于 1 说明决策成熟)
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

### 技能自进化（UOW-8 SkillEvolutionLoop）

`SkillEvolutionLoop` 实现四步闭环，让技能在每次使用后自动进化：

```
collect_feedback → learn → validate → deploy
       ↓                                   
  SkillFeedback                              
  (质量评分+用户满意度)                      
       ↓                                   
  SkillMutation                            
  (经验→规则补强/边界案例/解释质量)         
       ↓                                   
  EvolutionGate                           
  (test_pass + quality_improve + no_regression)
       ↓                                   
  deploy (idempotent: 未变化则跳过)
```

Safety 机制：
- 每次 deploy 前跑完整测试套件，失败则自动回滚
- `EvolutionGate` 三重门控：test_pass + quality_improve + no_regression
- `max_evolution_per_day=3` 防止抖动
- 未变化不重复 deploy（幂等性）

### 成本优化（UOW-8 CostOptimizer）

`CostOptimizer` 从三个维度优化 Token 开销：

| 维度 | 策略 |
|------|------|
| **LoadingTier 分级** | L0_SUMMARY(100tok) / L1_CONTEXT(2ktok) / L2_FULL(8ktok) — 按场景 + 预算动态选择 |
| **模型推荐** | premium（claude-gpt5）/ standard（gpt-4o） / economy（gpt-4o-mini）—— 按复杂度自适应 |
| **Budget Gate** | 预算充足→全量加载；预算紧张→降级 L0/L1；critical 场景保 L1 |

`DecisionCostTracker` 记录每次决策的 Token 消耗，`SelfEvolutionEngine` 联动成本数据给出降本建议。

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
./scripts/run_pytest.sh tests/ -q

# Demo 主链测试
./scripts/run_pytest.sh \
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
│   │   ├── security/             # 安全架构（危险命令审批/凭据过滤/输出脱敏）
│   │   ├── swarm/                # 多 agent 协调
│   │   ├── mcp/                  # MCP 协议集成
│   │   └── ...
│   └── velaris_agent/            # 业务层 (Velaris 2.0)
│       ├── context/               # OpenViking 上下文数据库 (UOW-4)
│       │   ├── openviking_context.py  # viking:// URI + L0/L1/L2 加载
│       │   ├── loading_strategy.py    # LoadingTier 分级策略
│       │   └── uri_scheme.py         # viking:// URI parser
│       ├── scenarios/             # ScenarioRegistry 插件化 (UOW-5)
│       │   ├── registry.py        # 场景注册表 + SKILL.md 发现
│       │   ├── skill_loader.py    # SKILL.md YAML frontmatter 解析
│       │   └── lifegoal/         # 人生目标决策 demo
│       ├── velaris/               # 治理运行时 (UOW-1/6)
│       │   ├── dynamic_router.py  # 四层路由引擎
│       │   ├── cost_tracker.py    # DecisionCostTracker
│       │   ├── authority.py       # 能力令牌签发
│       │   ├── task_ledger.py     # 任务账本
│       │   └── outcome_store.py   # Outcome 回写
│       ├── memory/                # 决策记忆 + 语义召回 (UOW-7)
│       │   ├── semantic_recall.py # SemanticRecallEngine 向量+关键词混合召回
│       │   ├── decision_memory.py # DecisionMemory 接口
│       │   └── preference_learner.py # 偏好学习 贝叶斯+指数衰减
│       ├── evolution/             # 技能自进化 + Token Economics (UOW-8)
│       │   ├── skill_evolution.py # SkillEvolutionLoop 四步闭环
│       │   ├── cost_optimizer.py  # CostOptimizer 加载分级+模型推荐+预算门控
│       │   └── self_evolution.py  # SelfEvolutionEngine 定期复盘
│       ├── biz/                  # 场景引擎 (L1 Goal-to-Plan)
│       ├── persistence/           # 持久化层 (SQLite + OpenViking)
│       └── decision/              # 决策算子 (intent_op, bias_audit_op, ...)
├── tests/                        # pytest 测试集 (~1200 用例)
│   ├── test_evolution/           # UOW-8 测试 (skill_evolution, cost_optimizer)
│   ├── test_dynamic_router/      # UOW-6 测试 (四层路由)
│   ├── test_semantic_recall/     # UOW-7 测试 (语义召回)
│   ├── test_scenario_registry/    # UOW-5 测试 (ScenarioRegistry)
│   ├── test_context/             # UOW-4 测试 (OpenViking)
│   └── ...
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

Velaris Agent 继续沿用 `Velaris` 品牌入口，但 MCP 配置格式已经兼容 OpenHarness 当前的 `stdio / http / ws` 三种 transport。

你既可以直接编辑 `~/.velaris/settings.json`，也可以用 CLI 管理：

```bash
# 本地 stdio MCP
uv run velaris mcp add local-files '{"command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","."]}'

# 远端 HTTP MCP
uv run velaris mcp add remote-http '{"type":"http","url":"https://example.com/mcp","headers":{"Authorization":"Bearer <token>"}}'

# 远端 WebSocket MCP
uv run velaris mcp add remote-ws '{"type":"ws","url":"wss://example.com/mcp","headers":{"Authorization":"Bearer <token>"}}'

# 查看当前已配置服务器（会显示 transport 与目标地址）
uv run velaris mcp list
```

如果你更习惯手工维护配置文件，可以写成下面这样：

```json
{
  "mcp_servers": {
    "local-files": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
    },
    "remote-http": {
      "type": "http",
      "url": "https://example.com/mcp",
      "headers": {
        "Authorization": "Bearer <token>"
      }
    },
    "remote-ws": {
      "type": "ws",
      "url": "wss://example.com/mcp",
      "headers": {
        "Authorization": "Bearer <token>"
      }
    }
  }
}
```

如果需要在会话内补充鉴权，也可以继续使用现有命令：

```text
/mcp
/mcp auth remote-http bearer <token>
/mcp auth remote-ws bearer <token>
/mcp auth remote-ws header X-API-Key <token>
```

当前 `/mcp` 的纯文本摘要也已经和最新 OpenHarness 风格保持一致，会直接标出每个 server 的连接状态、鉴权/工具/资源计数，以及恢复/失败语义：

```text
MCP servers:
- remote-http [connected] http
  auth=True tools=2 resources=1
  tool_names: search_docs, read_page
  resource_uris: docs://index
- remote-ws [connected] ws
  auth=True tools=3 resources=1
  mcp recovered: Auto-reconnect recovered after transport closed
  tool_names: search_flights, search_hotels, get_weather
  resource_uris: travel://guide
- local-files [failed] stdio
  auth=False tools=0 resources=0
  mcp error: broken pipe
```

在交互会话里执行 `/mcp auth ...` 时，如果当前运行时持有活跃的 MCP manager，Velaris 会优先热更新该 server 配置并尝试自动重连；如果是在离线修改配置或当前上下文没有活跃 manager，则会在下次进入会话时生效。

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
