# Velaris 2.0 AIDLC/SuperPowers 开发计划

> 基于 `velaris-agent-optimization-2026-05-06.md` 优化方案和 `velaris-before-after-comparison-2026-05-06.md` 前后对比，结合 AIDLC 8步流水线 + gnhf 自动开发。

## 一、计划总览

### 改造目标映射

| # | 问题 | 优先级 | 改造目标 | AIDLC UOW |
|---|------|--------|----------|-----------|
| 1 | P0：快照不完整，治理变量未持久化 | P0 | OpenViking 持久化 + 三层加载 | UOW-4 |
| 2 | P0：Velaris/OpenHarness 定位模糊 | P0 | 物理分离 + 语义边界收束 | UOW-1 ✅ (已完成) |
| 3 | P1：场景硬编码 `_SCENARIO_KEYWORDS` | P1 | SKILL.md + ScenarioRegistry 插件化 | UOW-5 |
| 4 | P1：路由静态（YAML 无运行时感知） | P1 | DynamicRouter + token成本+SLA感知 | UOW-6 |
| 5 | P2：记忆召回弱（keyword-only 无语义） | P2 | VikingVectorDB (HNSW) + 目录递归检索 | UOW-7 |
| 6 | P2：无 Token Economics 感知 | P2 | DecisionCost ROI + 三层加载 + 工具精简 | UOW-8 |

### 总体架构变更

```
Before (Velaris 1.0):
┌─────────────────────────────────┐
│  engine.py (硬编码场景/权重/治理)  │
│  router.py (静态YAML路由)        │
│  preference_learner.py (keyword) │
│  persistence/ (SQLite only)      │
│  memory/ (DecisionMemory file)   │
└─────────────────────────────────┘

After (Velaris 2.0):
┌──────────────────────────────────────────────┐
│  ScenarioRegistry (SKILL.md 插件化发现)        │
│  DynamicRouter (token成本+SLA+合规感知)         │
│  PreferenceLearnerV2 (OpenViking语义召回)       │
│  OpenVikingContext (L0/L1/L2 三层加载)          │
│  DecisionCostTracker (ROI追踪)                  │
│  TimeMachine (任务树+文件快照)                   │
└──────────────────────────────────────────────┘
```

---

## 二、UOW 拆分与依赖

### UOW 依赖图

```
UOW-1 ✅ (已完成)
  ↓
UOW-4 (OpenViking 持久化层)
  ↓
UOW-5 (ScenarioRegistry 场景插件化) ──→ UOW-6 (DynamicRouter 动态路由)
  ↓                                       ↓
UOW-7 (语义召回增强)                  UOW-8 (Token Economics)
```

### UOW 详情

---

### UOW-4：OpenViking 上下文数据库集成

**目标**：用 OpenViking 替代 SQLite+文件存储+内存字典，实现持久化 + 三层加载 + viking:// URI 统一

**改造范围**：
- 新增 `src/velaris_agent/context/` 包
- 修改 `src/velaris_agent/persistence/factory.py`
- 修改 `src/velaris_agent/velaris/orchestrator.py`
- 修改 `src/velaris_agent/memory/decision_memory.py`
- 新增 `src/velaris_agent/context/openviking_context.py`
- 新增 `src/velaris_agent/context/uri_scheme.py`
- 新增 `src/velaris_agent/context/loading_strategy.py`

**关键设计**：

```python
# viking:// URI 映射到三维决策主体
# viking://user/{id}/preferences/     → 用户偏好
# viking://user/{id}/memories/        → 用户记忆
# viking://org/{id}/policies/         → 组织策略
# viking://org/{id}/compliance/       → 合规规则
# viking://agent/{id}/skills/         → Agent技能
# viking://agent/{id}/snapshots/      → 执行快照

# 三层加载策略
class LoadingStrategy:
    L0_SUMMARY = "100tok"    # 快速摘要，用于路由决策
    L1_CONTEXT = "2ktok"     # 上下文摘要，用于规划
    L2_FULL    = "full"      # 完整数据，用于执行
```

**最小交付物**：
- OpenVikingContext 类（支持 Local/HTTP 双模式）
- viking:// URI 解析与路由
- L0/L1/L2 三层加载实现
- persistence factory 切换点（SQLite → OpenViking）
- 集成测试：偏好/记忆/快照均可通过 viking:// 读写

**完成标准**：
- 能通过 viking://user/{id}/preferences/ 读写用户偏好
- 能通过 viking://agent/{id}/snapshots/ 保存执行快照
- 三层加载：L0 摘要 < 100tok，L1 上下文 < 2ktok
- 现有 SQLite 测试不回归

**gnhf 执行命令**：
```bash
cd /Users/apus/Documents/UGit/velaris-agent
gnhf "Implement UOW-4: OpenViking context database integration. \
1. Create src/velaris_agent/context/ package with openviking_context.py, uri_scheme.py, loading_strategy.py \
2. Implement viking:// URI parsing for user/org/agent three decision subjects \
3. Implement L0(100tok)/L1(2ktok)/L2(full) three-tier loading strategy \
4. Modify persistence/factory.py to support OpenViking backend alongside SQLite \
5. Integrate with orchestrator.py for snapshot persistence via viking:// \
6. Integrate with memory/decision_memory.py for preference/memory storage via viking:// \
7. Write tests for URI parsing, three-tier loading, and factory switching \
8. Ensure existing SQLite tests still pass" \
  --agent claude --max-iterations 15 --current-branch
```

---

### UOW-5：ScenarioRegistry 场景插件化

**目标**：用 SKILL.md + ScenarioRegistry 替代 `_SCENARIO_KEYWORDS` 硬编码

**改造范围**：
- 新增 `src/velaris_agent/scenarios/registry.py`
- 新增 `src/velaris_agent/scenarios/skill_loader.py`
- 修改 `src/velaris_agent/biz/engine.py`（消除 `_SCENARIO_KEYWORDS`）
- 为每个场景新增 `SKILL.md`
- 修改 `src/velaris_agent/velaris/router.py`

**关键设计**：

```yaml
# scenarios/travel/SKILL.md 示例
---
name: travel
version: "1.0"
keywords: [travel, flight, hotel, trip, 商旅, 出差, 机票, 酒店]
capabilities: [intent_parse, inventory_search, option_score, itinerary_recommend]
weights:
  price: 0.40
  time: 0.35
  comfort: 0.25
governance:
  requires_audit: false
  approval_mode: default
  stop_profile: balanced
risk_level: medium
tools: [biz_execute, travel_recommend, travel_compare, biz_plan, biz_score]
---

# Travel Scenario

商旅对比与推荐场景...
```

```python
# ScenarioRegistry 运行时发现
class ScenarioRegistry:
    """SKILL.md 驱动的场景注册表，替代硬编码 _SCENARIO_KEYWORDS。"""

    def discover(self, scenarios_dir: Path) -> list[ScenarioSpec]: ...
    def match(self, query: str) -> ScenarioSpec | None: ...
    def get(self, name: str) -> ScenarioSpec: ...
    def reload(self) -> None: ...  # 热加载新场景
```

**最小交付物**：
- ScenarioRegistry 类（发现/匹配/获取/热加载）
- SKILL.md 解析器（YAML frontmatter + markdown body）
- 6个场景的 SKILL.md（lifegoal, travel, hotel_biztravel, tokencost, robotclaw, procurement）
- engine.py 中 `_SCENARIO_KEYWORDS` 完全替换为 registry 调用
- router.py 中静态映射替换为 registry 查询

**完成标准**：
- `infer_scenario("帮我订机票")` 通过 registry 返回 "travel"
- 新增场景只需添加 SKILL.md 目录，零代码修改
- `registry.reload()` 后新场景可被发现
- 原有场景测试不回归

**gnhf 执行命令**：
```bash
gnhf "Implement UOW-5: ScenarioRegistry with SKILL.md plugin system. \
1. Create src/velaris_agent/scenarios/registry.py with discover/match/get/reload methods \
2. Create src/velaris_agent/scenarios/skill_loader.py for SKILL.md YAML frontmatter parsing \
3. Create SKILL.md for all 6 scenarios (lifegoal, travel, hotel_biztravel, tokencost, robotclaw, procurement) \
4. Refactor engine.py to use ScenarioRegistry instead of _SCENARIO_KEYWORDS/_SCENARIO_CAPABILITIES/_SCENARIO_WEIGHTS/_SCENARIO_GOVERNANCE/_SCENARIO_RECOMMENDED_TOOLS \
5. Update router.py to use registry for scenario metadata \
6. Write tests for SKILL.md parsing, scenario matching, and hot-reload \
7. Ensure all existing scenario tests pass without regression" \
  --agent claude --max-iterations 15 --current-branch
```

---

### UOW-6：DynamicRouter 动态路由

**目标**：在 PolicyRouter 基础上增加 token 成本、SLA、本地合规感知的动态路由

**改造范围**：
- 新增 `src/velaris_agent/velaris/dynamic_router.py`
- 修改 `src/velaris_agent/velaris/router.py`（保持向后兼容）
- 新增 `src/velaris_agent/velaris/cost_tracker.py`
- 修改 `src/velaris_agent/velaris/orchestrator.py`

**关键设计**：

```python
class DynamicRouter:
    """token成本+SLA+合规感知的动态路由器。"""

    def route(self, plan, query, context: RoutingContext) -> RoutingDecision:
        # 1. PolicyRouter 基础规则匹配（保留向后兼容）
        base = self._base_route(plan, query)
        # 2. Token 成本优化（L0/L1 级别路由到低成本模型）
        cost_adjusted = self._adjust_for_cost(base, context)
        # 3. SLA 感知（高延迟场景路由到快速模型）
        sla_adjusted = self._adjust_for_sla(cost_adjusted, context)
        # 4. 本地合规感知（AI Localism：数据不出境）
        final = self._adjust_for_compliance(sla_adjusted, context)
        return final

class DecisionCostTracker:
    """决策成本追踪，计算每次决策的 ROI。"""

    def track(self, execution_id, token_in, token_out, model, latency_ms) -> CostRecord: ...
    def roi(self, scenario, period_days=30) -> ROIReport: ...
```

**最小交付物**：
- DynamicRouter 类（4层路由调整）
- DecisionCostTracker 类（token 追踪 + ROI 计算）
- RoutingContext 数据类（成本/SLA/合规上下文）
- orchestrator 集成点
- 成本报告工具

**完成标准**：
- DynamicRouter 在低预算时自动降级到 L0/L1 模型
- 每次执行有 token 成本记录
- ROI 报告可按场景/时间段生成
- 原 PolicyRouter 行为完全保持

**gnhf 执行命令**：
```bash
gnhf "Implement UOW-6: DynamicRouter with token cost, SLA, and compliance awareness. \
1. Create src/velaris_agent/velaris/dynamic_router.py with 4-layer routing (base→cost→SLA→compliance) \
2. Create src/velaris_agent/velaris/cost_tracker.py for decision cost tracking and ROI reporting \
3. Create RoutingContext dataclass for cost/SLA/compliance context \
4. Integrate DynamicRouter into orchestrator.py alongside existing PolicyRouter (backward compatible) \
5. Write tests for each routing adjustment layer and ROI calculation \
6. Ensure PolicyRouter existing tests pass without regression" \
  --agent claude --max-iterations 12 --current-branch
```

---

### UOW-7：语义召回增强

**目标**：用 VikingVectorDB (HNSW) + 目录递归检索替代 keyword-only 召回

**改造范围**：
- 新增 `src/velaris_agent/memory/semantic_recall.py`
- 修改 `src/velaris_agent/memory/decision_memory.py`
- 修改 `src/velaris_agent/memory/preference_learner.py`
- 集成 OpenViking 的 VikingVectorDB

**关键设计**：

```python
class SemanticRecallEngine:
    """基于 VikingVectorDB 的语义召回引擎。"""

    def index(self, record: DecisionRecord) -> None:
        """索引决策记录到向量数据库。"""

    def recall(self, query: str, scenario: str, top_k: int = 5) -> list[DecisionRecord]:
        """语义召回：支持 HNSW 近似最近邻 + 目录递归。"""

    def recall_by_embedding(self, embedding: list[float], top_k: int = 5) -> list[DecisionRecord]:
        """直接用 embedding 召回。"""
```

**最小交付物**：
- SemanticRecallEngine 类（索引/召回/embedding 召回）
- DecisionMemory 集成点（keyword 降级为 fallback）
- PreferenceLearnerV2 使用语义召回增强权重学习
- 召回质量对比测试

**完成标准**：
- 语义召回归类率 > keyword-only 基线
- "帮我选机票" 召回商旅相关决策，而非仅靠关键词匹配
- keyword-only 降级路径完整
- 原有记忆系统测试不回归

**gnhf 执行命令**：
```bash
gnhf "Implement UOW-7: Semantic recall enhancement with VikingVectorDB HNSW. \
1. Create src/velaris_agent/memory/semantic_recall.py with SemanticRecallEngine \
2. Implement index/recall/recall_by_embedding methods using OpenViking VikingVectorDB \
3. Modify decision_memory.py to use semantic recall with keyword fallback \
4. Modify preference_learner.py to use semantic recall for weight learning \
5. Write tests comparing semantic vs keyword recall quality \
6. Ensure existing memory system tests pass without regression" \
  --agent claude --max-iterations 12 --current-branch
```

---

### UOW-8：Token Economics & Skill 自进化

**目标**：实现 DecisionCost ROI 追踪 + Skill 自进化循环

**改造范围**：
- 新增 `src/velaris_agent/evolution/skill_evolution.py`
- 新增 `src/velaris_agent/evolution/cost_optimizer.py`
- 修改 `src/velaris_agent/evolution/self_evolution.py`
- 集成 DecisionCostTracker

**关键设计**：

```python
class SkillEvolutionLoop:
    """Skill 自进化循环：使用反馈→学习→验证→部署。"""

    def collect_feedback(self, execution_id: str) -> SkillFeedback: ...
    def learn(self, feedback: SkillFeedback) -> SkillMutation: ...
    def validate(self, mutation: SkillMutation) -> bool: ...
    def deploy(self, mutation: SkillMutation) -> None: ...

class CostOptimizer:
    """Token 成本优化器。"""

    def optimize_loading_tier(self, scenario: str, budget: float) -> str:
        """根据预算决定加载层级：L0/L1/L2。"""

    def recommend_model(self, scenario: str, complexity: str) -> str:
        """根据场景复杂度推荐模型。"""

    def token_budget_gate(self, remaining_budget: float, estimated_cost: float) -> bool:
        """Token 预算门控：类似 Codex /goal 的 Ralph Loop。"""
```

**最小交付物**：
- SkillEvolutionLoop 4步循环
- CostOptimizer 加载层级/模型推荐/预算门控
- 与 OpenViking 集成的反馈存储
- Token Economics 报告

**完成标准**：
- Skill 反馈收集→学习→验证→部署闭环可运行
- 预算不足时自动降级到 L0/L1
- Token Economics 报告可生成
- 与 gnhf 类似的 continuation.md 目标持久化机制

**gnhf 执行命令**：
```bash
gnhf "Implement UOW-8: Token Economics and Skill self-evolution loop. \
1. Create src/velaris_agent/evolution/skill_evolution.py with SkillEvolutionLoop (feedback→learn→validate→deploy) \
2. Create src/velaris_agent/evolution/cost_optimizer.py with loading tier/model recommendation/budget gating \
3. Integrate with DecisionCostTracker for ROI tracking \
4. Implement continuation.md-style goal persistence across sessions \
5. Integrate with OpenViking for feedback storage via viking:// \
6. Write tests for evolution loop, cost optimization, and budget gating \
7. Ensure existing evolution tests pass without regression" \
  --agent claude --max-iterations 12 --current-branch
```

---

## 三、执行策略

### gnhf 使用规范

1. **每个 UOW 独立分支**：`gnhf/` 前缀自动创建，用 `--current-branch` 合并到主线
2. **迭代限制**：每个 UOW 设 12-15 次迭代上限，避免无限循环
3. **Agent 选择**：默认 `--agent claude`，如需 Codex 可切换
4. **并发**：独立 UOW 可用 `--worktree` 并行跑（UOW-5 和 UOW-7 无依赖）
5. **质量检查**：每次 gnhf 完成后手动跑 `pytest` 验证

### AIDLC 流水线映射

| AIDLC 步骤 | 对应活动 | 产出 |
|------------|---------|------|
| 1. Workspace Detection | ✅ 已完成 | 项目根目录确认 |
| 2. Reverse Engineering | ✅ 已完成 | 架构/组件/接口文档 |
| 3. Requirements Analysis | ✅ 已完成 | 6大问题→6大目标 |
| 4. Workflow Planning | 本文档 | UOW-4~8 拆分 |
| 5. Application Design | 本文档 | 关键设计代码示例 |
| 6. Units Generation | gnhf 执行 | 代码+测试 |
| 7. Build & Test | pytest 验证 | 测试报告 |
| 8. Operations | 持续集成 | 监控+反馈 |

### 执行顺序与时间线

| 阶段 | UOW | 预计迭代 | 依赖 | 可并行 |
|------|-----|---------|------|--------|
| Phase 2a | UOW-4 (OpenViking) | 15 | UOW-1 ✅ | 否 |
| Phase 2b | UOW-5 (ScenarioRegistry) | 15 | UOW-4 | 否 |
| Phase 2c | UOW-6 (DynamicRouter) | 12 | UOW-5 | 否 |
| Phase 2d | UOW-7 (语义召回) | 12 | UOW-4 | ✅ 与UOW-6并行 |
| Phase 2e | UOW-8 (Token Economics) | 12 | UOW-6 + UOW-7 | 否 |

### 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| OpenViking API 不稳定 | 中 | 高 | SQLite fallback 路径保留 |
| gnhf 迭代跑偏 | 中 | 中 | 限制迭代次数 + 人工 review |
| 场景插件化破坏现有行为 | 低 | 高 | 完整回归测试 + 渐进替换 |
| 语义召回质量不达预期 | 中 | 中 | keyword fallback 保证底线 |
| HNSW 索引构建性能 | 低 | 低 | 异步构建 + 增量更新 |

---

## 四、核心算法保留清单

以下算法/机制在改造中**零改动**：

1. ✅ 贝叶斯先验混合：`blended = prior×(1-α) + learned×α`
2. ✅ 指数衰减加权：`decay = e^(-0.693×days/30)`
3. ✅ 五层决策架构（L0-L4）
4. ✅ 三维决策主体（user/org/agent）
5. ✅ 治理门（high→denied, medium→degraded, low→allowed）
6. ✅ 偏差检测（近因偏差/锚定效应/损失厌恶/沉没成本）
7. ✅ 用户-组织对齐分析
8. ✅ envelope-first 输出协议
9. ✅ fail-closed 屏障

---

## 五、量化目标

| 指标 | Before (1.0) | After (2.0) | 改善 |
|------|-------------|------------|------|
| Token 消耗 | 基线 | -83% | OpenViking 三层加载 |
| 任务完成率 | 基线 | +44% | 语义召回+动态路由 |
| 场景扩展时间 | ~2天/场景 | <2小时 | SKILL.md 插件化 |
| 成本效率 | 基线 | -80% | Token Economics 门控 |
| 记忆召回准确率 | keyword-only | +语义匹配 | HNSW 向量检索 |
| 决策 ROI 可追踪 | 无 | 完整 | DecisionCostTracker |

---

## 六、开发环境准备

```bash
# 1. 确认 gnhf 已安装
which gnhf  # → /Users/apus/.covs/node/.../gnhf

# 2. 确认项目可运行
cd /Users/apus/Documents/UGit/velaris-agent
python -m pytest tests/ -x -q  # 验证基线

# 3. 创建 Velaris 2.0 开发分支
git checkout -b velaris-2.0

# 4. 安装 OpenViking（待确认安装方式）
# pip install openviking  或  从源码安装
```
