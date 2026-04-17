"""决策记忆数据模型。

三类决策主体:
- 用户 (user): 个人在具体场景中的选择
- 组织 (org): 公司/平台层面的策略、约束、偏好
- 关系 (alignment): 用户和组织之间的匹配度、冲突点、协商空间

目标:
- 更了解自己的决策模式
- 通过 AI 纠正不合理的决策偏差
- 持续改进决策能力, 优化决策曲线
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class DecisionActor(str, Enum):
    """决策主体类型。"""

    USER = "user"
    ORG = "org"


class DecisionGoal(BaseModel):
    """决策目标。

    目标是确定的, 但可以重新设定。
    外部变量是动态变化的, 目标本身保持稳定直到主动修改。
    """

    goal_id: str = Field(description="目标唯一 ID")
    actor: DecisionActor = Field(description="目标所属主体: user 或 org")
    actor_id: str = Field(description="主体 ID (user_id 或 org_id)")
    scenario: str = Field(description="目标所属场景")
    description: str = Field(description="目标描述, 如 '3年内晋升到 P7'")
    target_metrics: dict[str, float] = Field(
        default_factory=dict,
        description="目标量化指标, 如 {'growth': 0.8, 'income_increase': 0.3}",
    )
    priority: float = Field(
        default=1.0, ge=0, le=10,
        description="目标优先级, 用于多目标冲突时排序",
    )
    status: str = Field(
        default="active",
        description="目标状态: active / paused / achieved / abandoned",
    )
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="最后修改时间")


class OrgPolicy(BaseModel):
    """组织决策策略。

    代表公司/平台层面的约束和偏好, 与用户偏好独立存在。
    """

    org_id: str = Field(description="组织 ID")
    scenario: str = Field(description="策略适用场景")
    weights: dict[str, float] = Field(
        default_factory=dict,
        description="组织层面的评分权重, 如 {'compliance': 0.5, 'cost': 0.3}",
    )
    constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="硬约束, 如 {'max_budget': 5000, 'require_direct_flight': True}",
    )
    bias_corrections: dict[str, float] = Field(
        default_factory=dict,
        description="组织希望纠正的决策偏差, 如 {'cost_over_quality': -0.15}",
    )
    updated_at: datetime | None = Field(default=None, description="最后修改时间")


class BiasDetection(BaseModel):
    """决策偏差检测结果。

    AI 通过分析历史决策模式, 识别不合理的决策偏差。
    """

    bias_type: str = Field(
        description="偏差类型: recency (近因偏差) / anchoring (锚定) / "
        "loss_aversion (损失厌恶) / confirmation (确认偏差) / "
        "sunk_cost (沉没成本) / overconfidence (过度自信)",
    )
    severity: float = Field(
        ge=0, le=1,
        description="偏差严重程度 0-1",
    )
    evidence: str = Field(description="偏差证据描述")
    correction_suggestion: str = Field(description="纠正建议")
    affected_dimension: str = Field(
        default="",
        description="受影响的决策维度, 如 'cost' / 'growth'",
    )


class AlignmentReport(BaseModel):
    """用户-组织决策对齐报告。

    分析用户偏好和组织策略之间的匹配度、冲突点和协商空间。
    """

    user_id: str = Field(description="用户 ID")
    org_id: str = Field(description="组织 ID")
    scenario: str = Field(description="场景")
    alignment_score: float = Field(
        ge=0, le=1,
        description="总体对齐度 0-1, 1 表示完全一致",
    )
    conflicts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="冲突点列表, 每项包含 dimension / user_weight / org_weight / gap",
    )
    synergies: list[str] = Field(
        default_factory=list,
        description="协同点: 用户和组织偏好一致的维度",
    )
    negotiation_space: dict[str, Any] = Field(
        default_factory=dict,
        description="协商空间: 双方可以妥协的维度和幅度",
    )
    created_at: datetime | None = Field(default=None, description="生成时间")


class DecisionCurvePoint(BaseModel):
    """决策曲线上的一个数据点。

    用于追踪决策能力随时间的变化。
    """

    period: str = Field(description="时间段标识, 如 '2026-Q1'")
    actor: DecisionActor = Field(description="决策主体")
    actor_id: str = Field(description="主体 ID")
    scenario: str = Field(description="场景")
    decision_count: int = Field(default=0, description="该时段决策数量")
    acceptance_rate: float = Field(
        default=0.0, description="推荐接受率",
    )
    avg_satisfaction: float | None = Field(
        default=None, description="平均满意度",
    )
    bias_count: int = Field(default=0, description="检测到的偏差次数")
    alignment_score: float | None = Field(
        default=None, description="与组织的对齐度 (仅 user 主体)",
    )
    weight_stability: float = Field(
        default=0.0, ge=0, le=1,
        description="权重稳定性: 1 表示权重不再大幅波动, 决策趋于成熟",
    )


class DecisionRecord(BaseModel):
    """一次决策的完整快照。

    不只记录结果, 而是记录完整上下文:
    谁在决策 + 基于什么目标 + 有哪些选项 + 系统推荐了什么 +
    用户选了什么 + 组织约束是什么 + 有没有偏差 + 结果如何。
    """

    decision_id: str = Field(description="决策唯一 ID")
    user_id: str = Field(description="用户 ID")
    org_id: str = Field(default="", description="组织 ID (空表示纯个人决策)")
    scenario: str = Field(
        description="决策场景或领域, 如 travel / tokencost / robotclaw / career",
    )

    # 目标上下文
    active_goals: list[str] = Field(
        default_factory=list,
        description="本次决策关联的目标 ID 列表",
    )

    # 输入
    query: str = Field(description="原始意图文本")
    intent: dict[str, Any] = Field(default_factory=dict, description="结构化意图")

    # 环境变量快照 (动态变化的外部条件)
    env_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        description="决策时的外部环境变量快照, 如 {'market_trend': 'up', 'season': 'peak'}",
    )

    # 过程
    options_discovered: list[dict[str, Any]] = Field(
        default_factory=list, description="发现的所有候选项",
    )
    options_after_filter: list[dict[str, Any]] = Field(
        default_factory=list, description="过滤后的候选项",
    )
    scores: list[dict[str, Any]] = Field(
        default_factory=list, description="评分结果",
    )
    weights_used: dict[str, float] = Field(
        default_factory=dict, description="本次使用的权重 (可能是个性化的)",
    )
    org_weights_applied: dict[str, float] = Field(
        default_factory=dict, description="组织策略权重 (如果有)",
    )
    tools_called: list[str] = Field(
        default_factory=list, description="调用的工具列表",
    )

    # 偏差检测
    detected_biases: list[BiasDetection] = Field(
        default_factory=list, description="AI 检测到的决策偏差",
    )
    bias_correction_applied: bool = Field(
        default=False, description="是否应用了偏差纠正",
    )

    # 输出
    recommended: dict[str, Any] = Field(
        default_factory=dict, description="系统推荐的选项",
    )
    alternatives: list[dict[str, Any]] = Field(
        default_factory=list, description="备选方案",
    )
    explanation: str = Field(default="", description="推荐理由")

    # 反馈 (异步回填)
    user_choice: dict[str, Any] | None = Field(
        default=None, description="用户最终选了什么 (可能不是推荐的)",
    )
    user_feedback: float | None = Field(
        default=None, ge=0, le=5, description="用户满意度 0-5",
    )
    outcome_notes: str | None = Field(
        default=None, description="结果备注",
    )

    # 元数据
    created_at: datetime = Field(description="创建时间")
    latency_ms: int = Field(default=0, ge=0, description="决策耗时 (毫秒)")


class UserPreferences(BaseModel):
    """用户在某场景下的偏好画像。

    从历史决策中计算得出, 不是用户手动设置的。
    """

    user_id: str = Field(description="用户 ID")
    scenario: str = Field(description="场景")

    # 个性化权重 (从历史选择中学习)
    weights: dict[str, float] = Field(
        default_factory=dict, description="个性化评分权重",
    )

    # 行为模式
    total_decisions: int = Field(default=0, description="总决策次数")
    accepted_recommendation_rate: float = Field(
        default=0.0, description="接受推荐比率 (0-1)",
    )
    average_satisfaction: float | None = Field(
        default=None, description="平均满意度",
    )

    # 常见选择特征
    common_patterns: list[str] = Field(
        default_factory=list,
        description="常见选择模式, 如 '偏好最低价', '偏好舒适', '预算敏感'",
    )

    # 偏差画像
    known_biases: list[str] = Field(
        default_factory=list,
        description="已识别的决策偏差倾向, 如 'recency_bias', 'loss_aversion'",
    )

    # 元数据
    last_updated: datetime | None = Field(default=None, description="最后更新时间")
    confidence: float = Field(
        default=0.0, ge=0, le=1,
        description="偏好置信度 (决策越多越高)",
    )


# ---------------------------------------------------------------------------
# Stakeholder Mapping Models
# ---------------------------------------------------------------------------


class PreferenceDirection(str, Enum):
    """利益维度的偏好方向。"""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class StakeholderRole(str, Enum):
    """利益相关方角色类型。"""

    USER = "user"
    ORG = "org"
    RELATIONSHIP = "relationship"


class InterestDimension(BaseModel):
    """利益维度, 描述 Stakeholder 关注的决策方面及其偏好方向和权重。"""

    dimension: str = Field(description="维度名称, 如 'cost', 'growth'")
    direction: PreferenceDirection = Field(description="偏好方向")
    weight: float = Field(ge=0.0, le=1.0, description="维度权重 0-1")


class Stakeholder(BaseModel):
    """利益相关方实体。"""

    stakeholder_id: str = Field(description="利益相关方唯一 ID")
    role: StakeholderRole = Field(description="角色: user / org / relationship")
    display_name: str = Field(description="显示名称")
    scenario: str = Field(description="所属场景")
    interest_dimensions: list[InterestDimension] = Field(
        description="利益维度列表",
    )
    influence_weights: dict[str, float] = Field(
        description="维度 → 影响力权重 0..1",
    )
    related_stakeholder_ids: list[str] = Field(
        default_factory=list,
        description="关联的 Stakeholder ID 列表 (role==relationship 时需要恰好 2 个)",
    )
    active: bool = Field(default=True, description="是否活跃")
    version: int = Field(default=1, description="版本号")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")

    @field_validator("influence_weights")
    @classmethod
    def _validate_influence_weights(
        cls, v: dict[str, float],
    ) -> dict[str, float]:
        for dim, weight in v.items():
            if not (0.0 <= weight <= 1.0):
                msg = (
                    f"influence_weights['{dim}'] = {weight} "
                    f"is outside the allowed range [0.0, 1.0]"
                )
                raise ValueError(msg)
        return v


class PairwiseAlignment(BaseModel):
    """两个 Stakeholder 之间的对齐度评分。"""

    stakeholder_a_id: str = Field(description="Stakeholder A ID")
    stakeholder_b_id: str = Field(description="Stakeholder B ID")
    score: float = Field(ge=0.0, le=1.0, description="对齐度评分 0-1")
    classification: str = Field(
        description="分类: aligned / neutral / conflicting",
    )


class Conflict(BaseModel):
    """两个 Stakeholder 之间在某维度上的利益冲突。"""

    stakeholder_a_id: str = Field(description="Stakeholder A ID")
    stakeholder_b_id: str = Field(description="Stakeholder B ID")
    dimension: str = Field(description="冲突维度")
    conflict_type: str = Field(description="冲突类型: direction / weight")
    severity: float = Field(ge=0.0, le=1.0, description="严重程度 0-1")
    details: dict[str, Any] = Field(
        default_factory=dict, description="冲突详情",
    )


class NegotiationProposal(BaseModel):
    """协商提案, 针对某个冲突维度的妥协方案。"""

    dimension: str = Field(description="冲突维度")
    compromise_weight: float = Field(description="妥协后的权重")
    concessions: dict[str, float] = Field(
        description="stakeholder_id → 让步幅度",
    )
    feasibility: float = Field(ge=0.0, le=1.0, description="可行性评分 0-1")
    non_negotiable: bool = Field(
        default=False, description="是否不可协商 (硬约束)",
    )


class StakeholderContext(BaseModel):
    """利益相关方上下文, 注入 DecisionRecord.env_snapshot。"""

    scenario: str = Field(description="场景")
    stakeholder_ids: list[str] = Field(description="参与的 Stakeholder ID 列表")
    alignment_matrix: list[PairwiseAlignment] = Field(
        description="对齐矩阵",
    )
    conflicts: list[Conflict] = Field(description="冲突列表")
    negotiation_proposals: list[NegotiationProposal] = Field(
        description="协商提案列表",
    )
    warnings: list[str] = Field(
        default_factory=list, description="警告信息",
    )


class StakeholderMapModel(BaseModel):
    """利益相关方映射图的可序列化表示。"""

    map_id: str = Field(description="映射图唯一 ID")
    scenario: str = Field(description="场景")
    stakeholders: list[Stakeholder] = Field(description="利益相关方列表")
    alignment_matrix: list[PairwiseAlignment] = Field(
        description="对齐矩阵",
    )
    conflicts: list[Conflict] = Field(description="冲突列表")
    timestamp: datetime = Field(description="时间戳")


class DecisionMetricDefinition(BaseModel):
    """统一决策指标定义。

    这层定义把不同场景里反复出现的指标语义收口到同一份注册表，
    让后续 Phase 2 的算子化改造可以直接复用，而不是继续散落在各个场景函数里。
    """

    metric_id: str = Field(description="指标唯一 ID")
    label: str = Field(description="指标展示名称")
    description: str = Field(default="", description="指标语义说明")
    direction: PreferenceDirection = Field(description="指标偏好方向")
    scenarios: list[str] = Field(default_factory=list, description="适用场景列表")
    aliases: list[str] = Field(default_factory=list, description="兼容旧字段名的别名列表")
    unit: str | None = Field(default=None, description="指标单位")


class DecisionOptionMetric(BaseModel):
    """统一候选项指标值。

    这层结构把“原始值 + 归一化分 + 证据引用”绑在一起，
    为后续多目标求解、解释生成和审计回放提供稳定输入。
    """

    metric_id: str = Field(description="指标 ID")
    raw_value: Any = Field(default=None, description="原始值")
    normalized_score: float = Field(default=0.0, ge=0, le=1, description="归一化评分")
    evidence_refs: list[str] = Field(default_factory=list, description="证据引用列表")


class DecisionOptionSchema(BaseModel):
    """统一候选项 schema。

    不同业务场景都可以把本地字段映射到该模型，
    从而避免后续 operator graph 直接依赖 travel / procurement 的私有字段。
    """

    option_id: str = Field(description="候选项 ID")
    scenario: str = Field(description="候选项所属场景")
    label: str = Field(description="候选项标题")
    metrics: list[DecisionOptionMetric] = Field(default_factory=list, description="统一指标列表")
    summary: str = Field(default="", description="候选项摘要")
    warnings: list[str] = Field(default_factory=list, description="候选项警告列表")
    metadata: dict[str, Any] = Field(default_factory=dict, description="原始扩展信息")


class DecisionAuditSchema(BaseModel):
    """统一审计 schema。

    这个模型对齐设计文档里的 operator contract 与 audit event 关键字段，
    让当前单体实现也能提前稳定出 Phase 2 需要的追踪接口。
    """

    session_id: str = Field(description="会话 ID")
    decision_id: str = Field(description="决策 ID")
    step_name: str = Field(description="当前审计步骤名")
    operator_id: str = Field(description="算子或执行器 ID")
    operator_version: str = Field(description="算子版本")
    input_ref: str = Field(default="", description="输入快照引用")
    output_ref: str = Field(default="", description="输出快照引用")
    evidence_ref: str | None = Field(default=None, description="主证据引用")
    evidence_refs: list[str] = Field(default_factory=list, description="证据引用列表")
    confidence: float = Field(default=0.0, ge=0, le=1, description="结果置信度")
    trace_id: str = Field(default="", description="追踪 ID")
    warnings: list[str] = Field(default_factory=list, description="审计警告")
    created_at: datetime | None = Field(default=None, description="生成时间")

    @model_validator(mode="after")
    def _fill_primary_evidence(self) -> "DecisionAuditSchema":
        """在存在证据列表时自动补齐主证据引用。"""

        if self.evidence_ref is None and self.evidence_refs:
            self.evidence_ref = self.evidence_refs[0]
        return self


_DECISION_METRIC_REGISTRY: dict[str, DecisionMetricDefinition] = {
    "cost": DecisionMetricDefinition(
        metric_id="cost",
        label="成本",
        description="用于描述预算占用或费用大小，越低越好。",
        direction=PreferenceDirection.LOWER_IS_BETTER,
        scenarios=["travel", "tokencost", "robotclaw", "procurement"],
        aliases=["price"],
        unit="cny",
    ),
    "quality": DecisionMetricDefinition(
        metric_id="quality",
        label="质量",
        description="用于描述方案质量或效果保留程度，越高越好。",
        direction=PreferenceDirection.HIGHER_IS_BETTER,
        scenarios=["tokencost", "procurement"],
    ),
    "speed": DecisionMetricDefinition(
        metric_id="speed",
        label="速度",
        description="用于描述执行速度或响应效率，越高越好。",
        direction=PreferenceDirection.HIGHER_IS_BETTER,
        scenarios=["tokencost"],
    ),
    "time": DecisionMetricDefinition(
        metric_id="time",
        label="耗时",
        description="用于描述旅程总耗时，越低越好。",
        direction=PreferenceDirection.LOWER_IS_BETTER,
        scenarios=["travel"],
    ),
    "comfort": DecisionMetricDefinition(
        metric_id="comfort",
        label="舒适度",
        description="用于描述出行或体验舒适度，越高越好。",
        direction=PreferenceDirection.HIGHER_IS_BETTER,
        scenarios=["travel"],
    ),
    "safety": DecisionMetricDefinition(
        metric_id="safety",
        label="安全性",
        description="用于描述高风险场景中的安全余量，越高越好。",
        direction=PreferenceDirection.HIGHER_IS_BETTER,
        scenarios=["robotclaw"],
    ),
    "eta": DecisionMetricDefinition(
        metric_id="eta",
        label="到达时效",
        description="用于描述调度场景的到达时效，越低越好。",
        direction=PreferenceDirection.LOWER_IS_BETTER,
        scenarios=["robotclaw"],
    ),
    "delivery": DecisionMetricDefinition(
        metric_id="delivery",
        label="交付时效",
        description="用于描述采购交付天数，越低越好。",
        direction=PreferenceDirection.LOWER_IS_BETTER,
        scenarios=["procurement"],
        unit="day",
    ),
    "compliance": DecisionMetricDefinition(
        metric_id="compliance",
        label="合规性",
        description="用于描述是否满足组织与监管要求，越高越好。",
        direction=PreferenceDirection.HIGHER_IS_BETTER,
        scenarios=["robotclaw", "procurement"],
    ),
    "risk": DecisionMetricDefinition(
        metric_id="risk",
        label="风险",
        description="用于描述履约或业务风险，越低越好。",
        direction=PreferenceDirection.LOWER_IS_BETTER,
        scenarios=["procurement"],
    ),
}


def get_decision_metrics_registry() -> dict[str, DecisionMetricDefinition]:
    """返回统一指标注册表的深拷贝视图。"""

    return {
        metric_id: metric.model_copy(deep=True)
        for metric_id, metric in _DECISION_METRIC_REGISTRY.items()
    }


def get_decision_metric(metric_id: str) -> DecisionMetricDefinition | None:
    """按 canonical id 或别名读取指标定义。"""

    normalized_metric_id = metric_id.strip().lower()
    for definition in _DECISION_METRIC_REGISTRY.values():
        candidates = {definition.metric_id.lower(), *(alias.lower() for alias in definition.aliases)}
        if normalized_metric_id in candidates:
            return definition.model_copy(deep=True)
    return None


def get_decision_metrics_for_scenario(scenario: str) -> list[DecisionMetricDefinition]:
    """返回某个场景可复用的指标定义列表。"""

    normalized_scenario = scenario.strip().lower()
    return [
        definition.model_copy(deep=True)
        for definition in _DECISION_METRIC_REGISTRY.values()
        if normalized_scenario in {item.lower() for item in definition.scenarios}
    ]
