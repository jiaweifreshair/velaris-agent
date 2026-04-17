# 核心数据模型

## 决策领域模型 (src/velaris_agent/memory/types.py)

### DecisionRecord — 决策记录（核心）
```python
class DecisionRecord(BaseModel):
    decision_id: str                          # 决策 ID
    user_id: str                              # 用户 ID
    org_id: str | None                        # 组织 ID
    scenario: str                             # 场景 (career/travel/...)
    query: str                                # 原始查询
    intent: dict[str, Any]                    # 结构化意图
    active_goals: list[str]                   # 关联目标 ID
    env_snapshot: dict[str, Any]              # 环境变量快照
    options_discovered: list[dict]            # Agent 抓取的候选项
    options_filtered: list[dict]              # 过滤后候选项
    weights_used: dict[str, float]            # 使用的权重
    org_weights_applied: dict[str, float]     # 组织权重
    scores: list[dict]                        # 评分明细
    recommended: dict[str, Any]               # 系统推荐
    alternatives: list[dict]                  # 备选方案
    explanation: str                          # 推荐理由
    user_choice: dict | None                  # 用户最终选择
    user_feedback: float | None               # 满意度 0-5
    outcome_notes: str | None                 # 结果备注
    detected_biases: list[dict]               # 检测到的偏差
    bias_correction_applied: bool             # 是否应用纠正
    tools_called: list[str]                   # 调用的工具
    created_at: datetime                      # 创建时间
```

### UserPreferences — 用户偏好
```python
class UserPreferences(BaseModel):
    user_id: str
    scenario: str
    weights: dict[str, float]                 # 个性化权重
    common_patterns: list[str]                # 行为模式
    known_biases: list[str]                   # 已识别偏差
    satisfaction_avg: float | None            # 平均满意度
    decision_count: int                       # 决策数量
    last_updated: datetime | None
```

### OrgPolicy — 组织策略
```python
class OrgPolicy(BaseModel):
    org_id: str
    scenario: str
    weights: dict[str, float]                 # 组织权重
    constraints: dict[str, Any]               # 硬约束
    bias_corrections: dict[str, str]          # 偏差纠正方向
```

### BiasDetection — 偏差检测
```python
class BiasDetection(BaseModel):
    bias_type: str                            # recency/anchoring/loss_aversion/sunk_cost
    confidence: float                         # 置信度 0-1
    evidence: str                             # 证据描述
    correction_suggestion: str                # 纠正建议
```

### AlignmentReport — 对齐报告
```python
class AlignmentReport(BaseModel):
    alignment_score: float                    # 总体对齐度 0-1
    conflicts: list[dict]                     # 冲突点
    synergies: list[dict]                     # 协同点
    negotiation_space: dict[str, Any]         # 协商空间
    merged_weights: dict[str, float]          # 融合权重
```

### DecisionCurvePoint — 决策曲线
```python
class DecisionCurvePoint(BaseModel):
    period: str                               # 时间段
    decision_count: int
    acceptance_rate: float | None
    avg_satisfaction: float | None
    bias_count: int
    alignment_score: float | None
    weight_stability: float | None
```

## 利益相关者模型

### Stakeholder — 利益相关者
```python
class Stakeholder(BaseModel):
    stakeholder_id: str
    name: str
    role: StakeholderRole                     # user/organization/regulator/advisor/...
    scenario: str
    interests: list[InterestDimension]        # 关注维度 + 权重
    influence_weights: dict[str, float]       # 影响力权重
    relationships: list[str]                  # 关联的其他利益相关者
```

### StakeholderMapModel — 利益相关者地图
```python
class StakeholderMapModel(BaseModel):
    stakeholders: list[Stakeholder]
    pairwise_alignments: list[PairwiseAlignment]
    conflicts: list[Conflict]
    proposals: list[NegotiationProposal]
```

## 治理模型

### RoutingDecision — 路由决策
```python
@dataclass
class RoutingDecision:
    selected_route: SelectedRoute             # 选中的路由
    selected_strategy: str                    # 策略名
    required_capabilities: list[str]          # 所需能力
    reason_codes: list[str]                   # 原因码
    confidence: float                         # 置信度
```

### AuthorityPlan — 授权计划
```python
@dataclass
class AuthorityPlan:
    approvals_required: bool                  # 是否需要审批
    required_capabilities: list[str]
    capability_tokens: list[CapabilityToken]
```

### TaskLedgerRecord — 任务记录
```python
@dataclass
class TaskLedgerRecord:
    task_id: str
    session_id: str
    runtime: str                              # self/robotclaw/claude_code/mixed
    role: str
    objective: str
    status: str                               # queued/running/completed/failed
    depends_on: list[str]
    error: str | None
```

### OutcomeRecord — 结果记录
```python
@dataclass
class OutcomeRecord:
    session_id: str
    scenario: str
    selected_strategy: str
    success: bool
    reason_codes: list[str]
    summary: str
    metrics: dict[str, Any]
```

## 进化模型

### SelfEvolutionReport — 自进化报告
```python
class SelfEvolutionReport(BaseModel):
    user_id: str
    scenario: str
    generated_at: datetime
    sample_size: int
    accepted_recommendation_rate: float | None
    average_feedback: float | None
    top_preference_drift: dict[str, float]
    actions: list[EvolutionAction]
    report_path: str | None
```

### EvolutionAction — 优化动作
```python
class EvolutionAction(BaseModel):
    action_id: str                            # collect_more_samples/tighten_recall/...
    priority: str                             # low/medium/high
    title: str
    reason: str
    details: dict[str, Any]
```

## 审计模型

### DecisionAuditSchema — 决策审计
```python
class DecisionAuditSchema(BaseModel):
    audit_id: str
    decision_id: str
    scenario: str
    metrics: list[DecisionOptionMetric]
    options: list[DecisionOptionSchema]
    primary_evidence: list[str]
```
