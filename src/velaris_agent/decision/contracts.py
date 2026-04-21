"""酒店 / 商旅共享决策契约。

这组模型定义平台与 velaris-agent 之间的稳定边界：
同类候选集、跨类 bundle 候选集、请求与响应。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class CapabilityCandidate(BaseModel):
    """同类候选项的标准输入。

    这一层只要求平台把原始候选项整理成统一字段，
    其余归一化与打分工作由 velaris-agent 负责。
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    candidate_id: str = Field(
        validation_alias=AliasChoices("candidate_id", "id"),
        description="候选项 ID",
    )
    domain: str = Field(description="候选项所属领域")
    service_type: str = Field(description="候选项服务类型")
    title: str = Field(description="候选项标题")
    price: float | None = Field(default=None, description="价格")
    eta_minutes: float | None = Field(default=None, description="预计耗时或到达时长")
    detour_minutes: float | None = Field(default=None, description="绕路时长")
    inventory_status: str | None = Field(default=None, description="库存或可用性状态")
    available: bool = Field(default=True, description="是否可用")
    time_window: dict[str, Any] = Field(
        default_factory=dict,
        description="时间窗信息，例如开闭店时间或履约窗口",
    )
    location: dict[str, Any] = Field(default_factory=dict, description="地理位置信息")
    tags: list[str] = Field(default_factory=list, description="候选项标签")
    domain_features: dict[str, float] = Field(
        default_factory=dict,
        description="领域侧已经整理好的归一化特征",
    )
    score_features: dict[str, float] = Field(
        default_factory=dict,
        description="平台或上游预先计算好的归一化特征",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="原始扩展信息")
    evidence_refs: list[str] = Field(default_factory=list, description="证据引用")


class CapabilityCandidateSet(BaseModel):
    """同类候选项集合。

    这一层是 domain_rank 的输入边界，
    适合酒店、花店、咖啡、航班等同类能力做同域比较。
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    domain: str = Field(description="候选集合所属领域")
    service_type: str = Field(description="候选集合服务类型")
    request_context: dict[str, Any] = Field(
        default_factory=dict,
        description="请求上下文，保留 session / query / tenant 等信息",
    )
    hard_constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="硬约束，例如预算、绕路上限、时间窗",
    )
    candidates: list[CapabilityCandidate] = Field(
        default_factory=list,
        description="同类候选项列表",
    )


class BundleMemberRef(BaseModel):
    """bundle 中的成员引用。

    这层只记录 bundle 组合里每个成员的来源，
    不重复携带成员本体，避免 bundle 决策对象膨胀。
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    domain: str = Field(description="成员所属领域")
    candidate_id: str = Field(description="成员候选项 ID")
    service_type: str = Field(description="成员服务类型")


class BundleCandidateAggregates(BaseModel):
    """bundle 的聚合指标。

    这些字段由上游 planner 先做确定性组合计算，
    velaris-agent 再基于这些聚合值做联合排序。
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    total_price: float | None = Field(default=None, description="bundle 总价")
    total_eta_minutes: float | None = Field(default=None, description="bundle 总时长")
    detour_minutes: float | None = Field(default=None, description="bundle 绕路时长")
    time_slack_minutes: float | None = Field(default=None, description="时间余量")
    preference_match: float | None = Field(default=None, description="偏好匹配度")
    experience_value: float | None = Field(default=None, description="体验收益")


class BundleCandidate(BaseModel):
    """跨类联合决策中的 bundle 候选项。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    bundle_id: str = Field(description="bundle ID")
    members: list[BundleMemberRef] = Field(default_factory=list, description="bundle 成员")
    sequence_steps: list[str] = Field(default_factory=list, description="bundle 执行顺序")
    aggregates: BundleCandidateAggregates = Field(description="bundle 聚合指标")
    hard_constraint_report: dict[str, Any] = Field(
        default_factory=dict,
        description="上游 planner 给出的硬约束报告",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="扩展信息")
    evidence_refs: list[str] = Field(default_factory=list, description="证据引用")


class BundleDecisionRequest(BaseModel):
    """共享决策请求。

    这一层把同类比较和 bundle 比较收敛到同一条入口，
    方便后续统一接入 orchestrator、审计与学习闭环。
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    decision_type: Literal["domain_rank", "bundle_rank"] = Field(
        default="domain_rank",
        description="决策类型：同类排序或跨类联合排序",
    )
    candidate_set: CapabilityCandidateSet | None = Field(
        default=None,
        description="同类候选集合",
    )
    bundle_candidates: list[BundleCandidate] = Field(
        default_factory=list,
        description="bundle 候选列表",
    )
    request_context: dict[str, Any] = Field(
        default_factory=dict,
        description="请求上下文，供解释与审计回放使用",
    )
    hard_constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="全局硬约束",
    )
    decision_weights: dict[str, float] = Field(
        default_factory=dict,
        description="显式排序权重",
    )

    @model_validator(mode="after")
    def _fill_request_context(self) -> "BundleDecisionRequest":
        """把嵌套 candidate_set 的上下文提升到请求层，方便后续统一读取。"""

        if self.candidate_set is not None:
            if not self.request_context:
                self.request_context = dict(self.candidate_set.request_context)
            if not self.hard_constraints:
                self.hard_constraints = dict(self.candidate_set.hard_constraints)
        return self


class RankedCandidate(BaseModel):
    """同类排序中的单个候选项结果。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    candidate_id: str = Field(description="候选项 ID")
    label: str = Field(description="候选项标题")
    score: float = Field(description="综合评分")
    score_breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="评分拆解",
    )
    hard_constraint_report: dict[str, Any] = Field(
        default_factory=dict,
        description="候选项硬约束报告",
    )
    reason: str = Field(default="", description="排序原因摘要")


class RankedBundle(BaseModel):
    """bundle 排序中的单个 bundle 结果。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    bundle_id: str = Field(description="bundle ID")
    score: float = Field(description="综合评分")
    score_breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="评分拆解",
    )
    hard_constraint_report: dict[str, Any] = Field(
        default_factory=dict,
        description="bundle 硬约束报告",
    )
    reason: str = Field(default="", description="排序原因摘要")


class BundleDecisionResponse(BaseModel):
    """共享决策响应。

    这层输出必须同时满足平台渲染、治理审计和学习回写，
    所以会保留选中项、备选项和结构化解释。
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    decision_type: Literal["domain_rank", "bundle_rank"] = Field(
        description="决策类型",
    )
    selected_candidate_id: str | None = Field(
        default=None,
        description="被选中的同类候选项 ID",
    )
    selected_bundle_id: str | None = Field(
        default=None,
        description="被选中的 bundle ID",
    )
    ranked_candidates: list[RankedCandidate] = Field(
        default_factory=list,
        description="同类候选排序结果",
    )
    ranked_bundles: list[RankedBundle] = Field(
        default_factory=list,
        description="bundle 排序结果",
    )
    candidate_briefs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="面向前端展示的同类候选摘要",
    )
    bundle_briefs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="面向前端展示的 bundle 摘要",
    )
    inferred_user_needs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="根据 query 与候选信息推断出的用户需求假设",
    )
    writeback_hints: dict[str, Any] = Field(
        default_factory=dict,
        description="偏好回写与知识库写入边界提示",
    )
    score_breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="被选中项的评分拆解",
    )
    hard_constraint_report: dict[str, Any] = Field(
        default_factory=dict,
        description="整体硬约束报告",
    )
    why_selected: list[str] = Field(
        default_factory=list,
        description="为什么选中它",
    )
    why_not_others: list[dict[str, Any]] = Field(
        default_factory=list,
        description="为什么没有选其他项",
    )
    tradeoffs: list[str] = Field(
        default_factory=list,
        description="这次决策的权衡项",
    )
    uncertainty_flags: list[str] = Field(
        default_factory=list,
        description="不确定性标记",
    )
    explanation_text: str = Field(
        default="",
        description="可直接渲染给用户的解释文本",
    )
    decision_trace_id: str = Field(
        default="",
        description="决策追踪 ID",
    )


def build_bundle_decision_request(payload: dict[str, Any]) -> BundleDecisionRequest:
    """把平台传入的原始 payload 归一成共享决策请求。

    这样做的目的是让 engine 入口支持更宽松的 JSON 形态，
    同时内部始终只处理一个稳定的数据模型。
    """

    normalized = dict(payload)
    if "candidate_set" not in normalized and "candidates" in normalized:
        normalized["candidate_set"] = {
            "domain": normalized.pop("domain", normalized.get("domain", "general")),
            "service_type": normalized.pop("service_type", normalized.get("service_type", "general")),
            "request_context": normalized.get("request_context", {}),
            "hard_constraints": normalized.get("hard_constraints", {}),
            "candidates": normalized.pop("candidates"),
        }
        normalized.setdefault("decision_type", "domain_rank")
    if "bundle_candidates" in normalized and "decision_type" not in normalized:
        normalized["decision_type"] = "bundle_rank"
    return BundleDecisionRequest.model_validate(normalized)
