"""企业采购场景协议模型。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from velaris_agent.memory.types import DecisionAuditSchema, DecisionOptionSchema


class ProcurementWorkflowStatus(str, Enum):
    """采购推荐工作流状态。"""

    PROPOSAL_READY = "proposal_ready"
    NO_MATCH = "no_match"


class ProcurementIntentSlots(BaseModel):
    """采购意图槽位。

    这层结构把预算、合规和交付约束标准化，
    方便后续 operator graph 直接消费，而不必重新解析原始 payload。
    """

    query: str = Field(default="", description="用户原始自然语言请求")
    budget_max: float | None = Field(default=None, description="预算上限")
    require_compliance: bool = Field(default=True, description="是否强制通过合规门槛")
    max_delivery_days: int | None = Field(default=None, description="最大可接受交付天数")


class ProcurementOption(BaseModel):
    """标准化采购候选项。"""

    id: str = Field(description="候选项 ID")
    label: str = Field(description="候选项标题")
    vendor: str | None = Field(default=None, description="供应商名称")
    price_cny: float = Field(ge=0, description="报价金额")
    delivery_days: float = Field(ge=0, description="交付周期（天）")
    quality_score: float = Field(default=0, ge=0, le=1, description="质量评分")
    compliance_score: float = Field(default=0, ge=0, le=1, description="合规评分")
    risk_score: float = Field(default=0, ge=0, le=1, description="风险评分")
    total_score: float | None = Field(default=None, description="综合评分")
    score_breakdown: dict[str, float] = Field(default_factory=dict, description="评分拆解")
    reason: str | None = Field(default=None, description="推荐原因")
    normalized_option: DecisionOptionSchema = Field(description="统一 option schema")
    metadata: dict[str, Any] = Field(default_factory=dict, description="原始扩展信息")


class ProcurementAuditTrace(BaseModel):
    """采购场景审计轨迹。"""

    trace_id: str = Field(description="追踪 ID")
    source_type: str = Field(description="数据源类型")
    accepted_option_ids: list[str] = Field(default_factory=list, description="通过约束过滤的候选项 ID")
    recommended_option_id: str | None = Field(default=None, description="推荐候选项 ID")
    proposal_id: str | None = Field(default=None, description="提案 ID")
    summary: str = Field(default="", description="执行摘要")
    created_at: str = Field(description="协议生成时间")
    audit_event: DecisionAuditSchema = Field(description="统一审计事件")


class ProcurementCompareResult(BaseModel):
    """统一采购比较结果。"""

    scenario: str = Field(default="procurement", description="场景标识")
    intent: str = Field(default="procurement_compare", description="统一工具意图")
    status: ProcurementWorkflowStatus = Field(description="当前工作流状态")
    query: str = Field(default="", description="用户原始请求")
    session_id: str = Field(description="会话 ID")
    intent_slots: ProcurementIntentSlots = Field(description="解析后的意图槽位")
    options: list[ProcurementOption] = Field(default_factory=list, description="候选方案")
    recommended: ProcurementOption | None = Field(default=None, description="推荐方案")
    accepted_option_ids: list[str] = Field(default_factory=list, description="通过约束过滤的候选项 ID")
    summary: str = Field(default="", description="简要摘要")
    explanation: str = Field(default="", description="推荐或失败说明")
    operator_trace: list[dict[str, Any]] = Field(default_factory=list, description="Phase 2 算子执行轨迹")
    proposal_id: str | None = Field(default=None, description="提案 ID")
    audit_trace: ProcurementAuditTrace = Field(description="审计轨迹")
