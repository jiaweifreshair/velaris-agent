# API 文档

## 工具 API（Agent 可调用的工具）

### 决策类工具

#### `lifegoal_decide`
人生目标决策，支持六大领域与个性化权重。
- **输入**: domain (career/finance/health/education/lifestyle/relationship), options (选项列表), user_id
- **输出**: 推荐选项 + 评分明细 + 推荐理由

#### `decision_score`
多维加权评分，支持个性化权重自动切换。
- **输入**: options, weights, user_id (可选)
- **输出**: 排序后的选项列表 + 评分明细

#### `score_options`
通用选项评分 (biz layer)。
- **输入**: options (list[dict]), weights (dict[str, float])
- **输出**: 排序后的选项列表，每项包含 total_score

#### `biz_execute`
业务闭环执行：路由 → 签权 → 执行 → 记录。
- **输入**: query, payload, constraints (可选), scenario (可选)
- **输出**: session_id, plan, routing, authority, task, outcome, result

#### `biz_plan`
能力规划：场景识别 + 约束推理。
- **输入**: query, constraints (可选), scenario (可选)
- **输出**: 结构化 plan (scenario, capabilities, weights, governance)

### 记忆类工具

#### `recall_preferences`
召回用户历史偏好。
- **输入**: user_id, scenario
- **输出**: 个性化权重 + 行为模式 + 满意度 + 已识别偏差

#### `recall_decisions`
检索相似历史决策。
- **输入**: user_id, scenario, query, limit (默认 5)
- **输出**: 相似决策记录列表

#### `save_decision`
保存完整决策快照。
- **输入**: DecisionRecord 完整字段
- **输出**: decision_id
- **副作用**: 每 10 条自动触发自进化复盘

### 知识库类工具

#### `knowledge_ingest`
摄取原始资料并编译为 Wiki 页面。
- **输入**: title, content, source (可选)
- **输出**: 文档 slug + 摘要

#### `knowledge_query`
检索个人知识库。
- **输入**: query, limit (默认 5)
- **输出**: 匹配文档列表

#### `knowledge_lint`
知识库健康检查。
- **输出**: 断链列表 + 孤岛文档列表

### 场景类工具

#### `travel_recommend`
商旅比价推荐。
- **输入**: query (自然语言), options (候选项)
- **输出**: 排序推荐 + 评分明细

#### `tokencost_analyze`
AI 成本分析与优化。
- **输入**: usage_data
- **输出**: 成本分析 + 降本建议

#### `robotclaw_dispatch`
RobotClaw 三段式调度。
- **输入**: dispatch_request
- **输出**: 调度提案 + 合约就绪判断

### 技能类工具

#### `skill`
按需读取技能全文或支持文件。
- **输入**: name
- **输出**: 技能内容

#### `skill_manage`
创建/patch/编辑/删除技能与支持文件。
- **输入**: action (create/patch/edit/delete), name, content

#### `skills_hub`
技能中心：搜索/安装/卸载/更新。
- **输入**: action, query/name

## 核心内部 API

### DecisionMemory
```python
class DecisionMemory:
    def save(record: DecisionRecord) -> str                    # 保存决策记录
    def get(decision_id: str) -> DecisionRecord | None         # 按 ID 获取
    def update_feedback(decision_id, user_choice, feedback)    # 回填反馈
    def list_by_user(user_id, scenario, limit) -> list         # 按用户检索
    def recall_similar(user_id, scenario, query, limit) -> list # 相似召回
    def aggregate_outcomes(scenario, option_field, value)       # 聚合满意度
```

### PreferenceLearner
```python
class PreferenceLearner:
    def compute_preferences(user_id, scenario) -> UserPreferences  # 计算偏好
    def get_personalized_weights(user_id, scenario) -> dict        # 获取个性化权重
    def detect_biases(user_id, scenario) -> list[BiasDetection]    # 偏差检测
    def compute_alignment(user_prefs, org_policy) -> AlignmentReport # 对齐分析
    def compute_merged_weights(user_prefs, org_policy) -> dict     # 融合权重
```

### PolicyRouter
```python
class PolicyRouter:
    def route(plan: dict, query: str) -> RoutingDecision  # 策略路由
```

### AuthorityService
```python
class AuthorityService:
    def issue_plan(required_capabilities, governance) -> AuthorityPlan  # 签发授权
```

### TaskLedger
```python
class TaskLedger:
    def create_task(session_id, runtime, role, objective) -> TaskLedgerRecord
    def update_status(task_id, status, error) -> TaskLedgerRecord | None
    def get_task(task_id) -> TaskLedgerRecord | None
    def list_by_session(session_id) -> list[TaskLedgerRecord]
```

### VelarisBizOrchestrator
```python
class VelarisBizOrchestrator:
    def execute(query, payload, constraints, scenario, session_id) -> dict
```

### SelfEvolutionEngine
```python
class SelfEvolutionEngine:
    def review(user_id, scenario, window, persist_report) -> SelfEvolutionReport
```

## CLI 入口

### Velaris CLI (`velaris` / `vl`)
```bash
velaris                          # 启动交互式 Agent
velaris -p "问题"                # 单次执行
velaris demo lifegoal            # 运行人生目标 Demo
velaris setup <provider>         # 配置 provider
velaris provider list/current/use
velaris auth login/logout/status/switch
velaris mcp add/list
```

### OpenHarness CLI (`oh` / `openharness`)
兼容入口，功能等同。
