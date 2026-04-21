# Velaris-Agent 技术方案

> 版本: v0.3.0 - Decision Intelligence Agent
> 基线: OpenHarness (Python agent framework)

## 1. 核心定位

Velaris 不是一个评分函数, 是一个**会思考的决策 Agent**.

```
传统 agent: 用户提问 → 调 API → 返回结果
Velaris:    用户提问 → 理解意图 → 推理需要什么数据 → 智能获取 → 
            参考历史决策 → 个性化评分 → 推荐+解释 → 记录+学习
```

**竞争壁垒**: Context 深度. 同样的 LLM, 谁的上下文更全谁的决策更准.
- 短期: Tool 质量 (数据源多, 搜索准)
- 中期: Memory 深度 (决策记忆 + 偏好学习)
- 长期: 数据飞轮 (用户越多, 市场智能越强)

## 2. 三层架构

```
Layer 1: Agent Loop          — OpenHarness engine (已有, 不改)
Layer 2: Decision Tools      — 决策工具集 + 记忆系统 (本次建设重点)
Layer 3: Domain Plugins      — 场景数据源 (可插拔扩展)
```

```
┌──────────────────────────────────────────────────────────┐
│                   Velaris Decision Agent                  │
│                                                          │
│  Layer 1: Agent Loop (OpenHarness)                       │
│  ┌────────────────────────────────────────────┐          │
│  │  LLM 推理 → 调工具 → 拿结果 → 继续推理    │          │
│  │       ↑                          │         │          │
│  │       └──────────────────────────┘         │          │
│  └────────────────────────────────────────────┘          │
│                        │                                 │
│  Layer 2: Decision Tools                                 │
│  ┌──────────────────────────────────────────────┐        │
│  │  记忆类                                      │        │
│  │  ├── recall_preferences   用户偏好召回        │        │
│  │  ├── recall_decisions     相似决策检索         │        │
│  │  ├── recall_outcomes      历史结果查询         │        │
│  │  └── save_decision        记录本次决策         │        │
│  │                                              │        │
│  │  决策类                                      │        │
│  │  ├── score_options        多维评分 (个性化权重) │        │
│  │  ├── compare_options      选项对比分析         │        │
│  │  ├── price_trend          价格趋势判断         │        │
│  │  └── explain_decision     推荐理由生成         │        │
│  │                                              │        │
│  │  治理类                                      │        │
│  │  ├── check_policy         合规/预算检查        │        │
│  │  ├── check_authority      权限验证            │        │
│  │  └── request_approval     审批流程            │        │
│  └──────────────────────────────────────────────┘        │
│                        │                                 │
│  Layer 3: Domain Data Sources                            │
│  ┌──────────────────────────────────────────────┐        │
│  │  商旅: 携程/去哪儿/飞猪/12306/酒店直连        │        │
│  │  TokenCost: OpenAI/Anthropic/用量API          │        │
│  │  OpenClaw: 车辆注册表/位置服务/路线API         │        │
│  │  通用: web_search / web_fetch (兜底)          │        │
│  └──────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────┘
```

## 3. 与现有代码的关系

### 3.1 保留不变

| 模块 | 路径 | 说明 |
|------|------|------|
| Agent Loop | `src/openharness/engine/` | 核心循环, 流式工具调用 |
| Tool 基类 | `src/openharness/tools/base.py` | BaseTool + ToolRegistry |
| 权限系统 | `src/openharness/permissions/` | 工具级权限控制 |
| Hook 系统 | `src/openharness/hooks/` | 生命周期钩子 |
| 插件系统 | `src/openharness/plugins/` | 插件发现和加载 |
| Swarm | `src/openharness/swarm/` | 多 agent 协调 |
| CLI | `src/openharness/cli.py` | 命令行入口 |

### 3.2 重构

| 现有 | 改为 | 原因 |
|------|------|------|
| `biz/engine.py: _run_*_scenario()` | 拆成独立 Decision Tools | 让 LLM 自主编排, 不硬编码 pipeline |
| `biz/engine.py: score_options()` | `DecisionScoreTool` | 保留算法, 包装为 Tool |
| `biz/engine.py: infer_scenario()` | System Prompt 引导 | 场景识别由 LLM 推理, 不靠关键词匹配 |
| 三个空壳 adapter | Domain DataSource Tools | 真正的数据获取工具 |
| `velaris/router.py` | `CheckPolicyTool` | 治理检查变为可调用工具 |
| `velaris/orchestrator.py` | Agent Loop 原生能力 | 不需要额外编排层 |

### 3.3 新增

| 模块 | 说明 |
|------|------|
| Decision Memory | 决策记忆存储 + 检索 |
| Preference Learner | 从用户选择中学习权重 |
| Decision Tools (6个) | recall_preferences/decisions/outcomes, save_decision, score_options, explain_decision |
| Domain Tools | smart_search, price_trend |
| System Prompt | 引导 Agent 的决策行为 |

## 4. Decision Memory 设计

### 4.1 数据模型

```python
class DecisionRecord(BaseModel):
    """一次决策的完整快照"""
    decision_id: str
    user_id: str
    scenario: str                          # travel/tokencost/openclaw
    
    # 输入
    query: str                             # 原始意图
    intent: dict[str, Any]                 # 结构化意图
    
    # 过程
    options_discovered: list[dict]         # 发现了哪些选项
    options_filtered: list[dict]           # 过滤后剩余
    scores: list[dict]                     # 评分结果
    weights_used: dict[str, float]         # 使用的权重 (可能是个性化的)
    tools_called: list[str]               # 调了哪些工具
    
    # 输出
    recommended: dict                      # 系统推荐
    alternatives: list[dict]               # 备选方案
    explanation: str                       # 推荐理由
    
    # 反馈 (异步回填)
    user_choice: dict | None = None        # 用户最终选了什么
    user_feedback: float | None = None     # 满意度 0-5
    outcome_notes: str | None = None       # 结果备注
    
    # 元数据
    created_at: datetime
    context_tokens: int                    # 消耗的 context
    latency_ms: int                        # 决策耗时
```

### 4.2 存储

```
~/.velaris/decisions/
├── index.db                    # SQLite 索引 (快速查询)
├── records/                    # 完整决策记录 (JSON)
│   ├── 2026-04/
│   │   ├── dec-xxxx.json
│   │   └── dec-yyyy.json
│   └── 2026-05/
└── preferences/                # 用户偏好
    ├── user-001.json
    └── user-002.json
```

### 4.3 检索

```python
class DecisionMemory:
    def recall_similar(self, user_id: str, scenario: str, intent: dict,
                       limit: int = 5) -> list[DecisionRecord]:
        """找到相似的历史决策 - 基于场景+意图语义相似度"""
        ...
    
    def recall_preferences(self, user_id: str, scenario: str) -> UserPreferences:
        """计算用户在该场景下的偏好 (从历史选择中学习)"""
        ...
    
    def recall_outcomes(self, provider: str, option_type: str) -> AggregatedOutcome:
        """聚合某类选项的历史满意度"""
        ...
    
    def save(self, record: DecisionRecord) -> None:
        """保存决策记录"""
        ...
    
    def update_feedback(self, decision_id: str, choice: dict, 
                        feedback: float, notes: str) -> None:
        """回填用户选择和满意度"""
        ...
```

## 5. Preference Learning 设计

```python
class PreferenceLearner:
    """从用户的实际选择中学习真实偏好权重"""
    
    def compute_weights(self, user_id: str, scenario: str) -> dict[str, float]:
        """基于历史决策计算个性化权重
        
        算法:
        1. 取该用户在该场景下的所有决策记录
        2. 对于每条记录, 如果 user_choice != recommended:
           - chosen 在哪些维度更好 → 该维度权重 +
           - chosen 在哪些维度更差 → 该维度权重 -
        3. 用指数衰减加权 (近期决策权重更大)
        4. 与场景默认权重混合 (贝叶斯先验)
        """
        ...
    
    def _blend(self, prior: dict, learned: dict, 
               sample_size: int) -> dict[str, float]:
        """先验 + 学习的混合
        
        sample_size 小时, 偏向先验 (默认权重)
        sample_size 大时, 偏向学习 (用户实际偏好)
        """
        alpha = min(sample_size / 20, 0.8)  # 最多 80% 来自学习
        return {
            dim: prior[dim] * (1 - alpha) + learned.get(dim, prior[dim]) * alpha
            for dim in prior
        }
```

## 6. Decision Tools 详细设计

### 6.1 记忆类 Tools

#### recall_preferences

```python
class RecallPreferencesTool(BaseTool):
    """查询用户历史偏好和决策模式"""
    name = "recall_preferences"
    description = """查询用户的历史决策偏好. 返回:
    - 个性化评分权重 (从历史选择中学习)
    - 常见选择模式 (总选最便宜/总选舒适/看情况)
    - 历史满意度模式 (哪类选项评价高/低)
    在做推荐前调用此工具, 可以让推荐更贴合用户."""
    
    # Input: user_id, scenario
    # Output: weights, patterns, satisfaction_history
```

#### recall_decisions

```python
class RecallDecisionsTool(BaseTool):
    """检索相似的历史决策"""
    name = "recall_decisions"
    description = """查找与当前意图相似的历史决策. 返回:
    - 相似决策的推荐和用户最终选择
    - 决策结果和满意度
    用于参考 '上次类似情况怎么选的, 结果如何'."""
    
    # Input: user_id, scenario, intent_summary, limit
    # Output: list of {decision_summary, recommended, chosen, outcome, feedback}
```

#### save_decision

```python
class SaveDecisionTool(BaseTool):
    """保存本次决策的完整上下文"""
    name = "save_decision"
    description = """在完成推荐后调用, 记录完整的决策过程.
    包括: 意图、发现的选项、使用的权重、推荐结果.
    这些记录用于未来的偏好学习和决策优化."""
    
    # Input: decision_record (完整快照)
    # Output: decision_id
```

### 6.2 决策类 Tools

#### score_options

```python
class DecisionScoreTool(BaseTool):
    """多维加权评分 (支持个性化权重)"""
    name = "score_options"
    description = """对候选选项进行多维评分和排序.
    权重可以来自 recall_preferences 的个性化结果,
    也可以手动指定. 返回排序后的选项和得分明细."""
    
    # Input: options, weights (个性化或默认), constraints
    # Output: ranked options with score breakdown
```

#### smart_search

```python
class SmartSearchTool(BaseTool):
    """智能数据搜索 - 自动选择最佳数据源"""
    name = "smart_search"
    description = """搜索商品/服务选项. 特点:
    - 自动选择最佳数据源 (机票/酒店/高铁/模型价格等)
    - 支持灵活参数 (日期范围/价格区间/多城市)
    - 并发查询多个数据源
    - 返回标准化的选项列表
    可以多次调用, 用不同参数扩展搜索范围."""
    
    # Input: query, source_hint, params
    # Output: list of standardized options
```

#### price_trend

```python
class PriceTrendTool(BaseTool):
    """价格趋势分析"""
    name = "price_trend"
    description = """查询历史价格趋势, 判断当前价格是否合理.
    返回: 当前价格在历史中的百分位, 建议买入/等待."""
    
    # Input: item_type, route/model/provider, date_range
    # Output: current_percentile, trend, recommendation
```

### 6.3 治理类 Tools

#### check_policy

```python
class CheckPolicyTool(BaseTool):
    """合规和预算检查"""
    name = "check_policy"
    description = """检查推荐方案是否符合用户的政策约束.
    如: 企业差旅标准、预算限制、安全合规要求.
    在最终推荐前调用."""
    
    # Input: recommendation, policy_context
    # Output: compliant (bool), violations, suggestions
```

## 7. System Prompt 设计

```markdown
你是 Velaris, 一个智能决策助手. 你通过深度理解用户意图、
广泛获取数据、参考历史决策来做出最优推荐.

## 决策流程

1. **理解意图**: 分析用户的真实需求, 不只是字面意思
2. **召回偏好**: 用 recall_preferences 了解这个用户的历史模式
3. **召回历史**: 用 recall_decisions 看类似场景怎么决策的
4. **智能搜索**: 用 smart_search 获取候选选项
   - 不要只查用户明确说的, 思考可能的替代方案
   - 可以多次调用, 扩展搜索范围 (不同日期/不同方式/不同平台)
5. **趋势判断**: 必要时用 price_trend 判断时机
6. **评分排序**: 用 score_options 评分, 优先使用个性化权重
7. **合规检查**: 用 check_policy 确认合规
8. **推荐输出**: 给出推荐 + 备选 + 理由
9. **记录决策**: 用 save_decision 保存完整决策过程

## 关键原则

- 数据越多决策越准, 宁可多查不要少查
- 参考历史但不盲从, 环境变了要调整
- 解释清楚为什么推荐这个, 不要只给结果
- 如果信息不够, 主动追问用户
- 推荐不满意时, 记录反馈用于改进
```

## 8. 实施计划

### Phase 1: Decision Memory + Core Tools (本次)

| 步骤 | 内容 | 产出 |
|------|------|------|
| 1.1 | DecisionRecord Pydantic 模型 | `src/velaris_agent/memory/types.py` |
| 1.2 | DecisionMemory 存储+检索 | `src/velaris_agent/memory/decision_memory.py` |
| 1.3 | PreferenceLearner | `src/velaris_agent/memory/preference_learner.py` |
| 1.4 | recall_preferences Tool | `src/openharness/tools/recall_preferences_tool.py` |
| 1.5 | recall_decisions Tool | `src/openharness/tools/recall_decisions_tool.py` |
| 1.6 | save_decision Tool | `src/openharness/tools/save_decision_tool.py` |
| 1.7 | score_options Tool (重构) | `src/openharness/tools/decision_score_tool.py` |
| 1.8 | Decision System Prompt | `src/openharness/skills/bundled/content/decision.md` |
| 1.9 | 修复 CRITICAL 问题 | API key 清理, 路径修复, __init__.py |
| 1.10 | 测试 | 全部新模块的单元测试 |

### Phase 2: Smart Search + Domain Sources (后续)

| 步骤 | 内容 |
|------|------|
| 2.1 | SmartSearchTool (统一搜索接口) |
| 2.2 | 商旅数据源（SkillHub 真实 skills：`meituan` / `meituan-hot-trend` / `meituan-coupon-auto`、`coupon` / `coupons` / `obtain-coupons-all-in-one` / `obtain-takeout-coupon`、`tripgenie` / `stayforge-api` / `tuniu-hotel`、`cabin` / `flight-search-fast` 与后续 provider adapters 集成） |
| 2.3 | TokenCost 数据源 (模型定价库 + 用量 API) |
| 2.4 | OpenClaw 数据源 (车辆注册 + DispatchEngine 集成) |
| 2.5 | PriceTrendTool |

### Phase 3: Governance + Evolution (后续)

| 步骤 | 内容 |
|------|------|
| 3.1 | CheckPolicyTool (从 router.py 重构) |
| 3.2 | Feedback Loop (用户选择回填) |
| 3.3 | MarketIntelligence (聚合分析) |
| 3.4 | 自进化: 权重自动调整验证 |

## 9. 清理现有问题

| 问题 | 处理 |
|------|------|
| API key 泄露 | 改为纯环境变量, 清除硬编码 |
| 路由策略路径脆弱 | 用 importlib.resources 或显式配置 |
| 缺 __init__.py | 补全所有包 |
| 硬编码 WORKSPACE | 改为 tmpdir |
| biz/engine 场景函数 | Phase 1 保留, Phase 2 逐步拆为 Tools |
| 空壳 adapter | Phase 2 替换为 Domain Source Tools |
| DispatchEngine 孤岛 | Phase 2 集成为 OpenClaw Domain Source |

## 10. 验证标准

| 检查项 | 命令 | 标准 |
|--------|------|------|
| 编译 | `python -m compileall src/` | 0 errors |
| Lint | `ruff check src tests` | 0 errors |
| 类型 | `mypy src/velaris_agent` | 0 errors |
| 测试 | `pytest tests/ -q` | 全部通过 |
| 决策记忆 | 手动验证 | save → recall 闭环 |
| 偏好学习 | 单元测试 | 5次选择后权重变化 |
