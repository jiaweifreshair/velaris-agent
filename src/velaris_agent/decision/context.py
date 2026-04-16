"""Decision graph 运行期上下文模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from velaris_agent.memory.types import DecisionOptionSchema


@dataclass
class OperatorTraceRecord:
    """单个算子的最小 trace 记录。

    Phase 2 先固定 operator/version/schema/confidence 这些核心字段，
    方便后续把 evidence 与 warnings 逐步接入审计链路。
    """

    operator_id: str
    operator_version: str
    input_schema_version: str
    output_schema_version: str
    confidence: float
    evidence_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DecisionGraphResult:
    """Decision graph 结果模型。

    这层结果既要承接当前过渡态的 procurement graph 输出，
    也要为后续 Pareto frontier / operating point 扩展预留稳定字段。
    """

    scenario: str
    ranked_options: list[DecisionOptionSchema] = field(default_factory=list)
    accepted_option_ids: list[str] = field(default_factory=list)
    rejected_option_ids: list[str] = field(default_factory=list)
    rejection_reasons: dict[str, list[str]] = field(default_factory=dict)
    pareto_frontier_ids: list[str] = field(default_factory=list)
    dominated_option_ids: list[str] = field(default_factory=list)
    frontier_metrics: list[dict[str, Any]] = field(default_factory=list)
    operating_point_summary: dict[str, Any] = field(default_factory=dict)
    recommended_option_id: str | None = None
    explanation: str = ""
    warnings: list[str] = field(default_factory=list)
    operator_traces: list[OperatorTraceRecord] = field(default_factory=list)


@dataclass
class DecisionExecutionContext:
    """Decision graph 执行上下文。

    这层对象为各个 operator 提供共享读写面，
    当前在保持 procurement 过渡链可运行的同时，为多目标求解阶段预留 frontier 字段。
    """

    scenario: str
    query: str
    payload: dict[str, Any]
    constraints: dict[str, Any]
    intent: dict[str, Any] = field(default_factory=dict)
    raw_options: list[dict[str, Any]] = field(default_factory=list)
    normalized_options: list[DecisionOptionSchema] = field(default_factory=list)
    accepted_options: list[DecisionOptionSchema] = field(default_factory=list)
    rejected_options: list[DecisionOptionSchema] = field(default_factory=list)
    rejection_reasons: dict[str, list[str]] = field(default_factory=dict)
    pareto_frontier: list[DecisionOptionSchema] = field(default_factory=list)
    dominated_options: list[DecisionOptionSchema] = field(default_factory=list)
    frontier_metrics: list[dict[str, Any]] = field(default_factory=list)
    operating_point_summary: dict[str, Any] = field(default_factory=dict)
    decision_weights: dict[str, float] = field(default_factory=dict)
    stakeholder_context: dict[str, Any] = field(default_factory=dict)
    ranked_options: list[DecisionOptionSchema] = field(default_factory=list)
    recommended_option_id: str | None = None
    negotiation_summary: dict[str, Any] = field(default_factory=dict)
    bias_summary: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    warnings: list[str] = field(default_factory=list)
    operator_traces: list[OperatorTraceRecord] = field(default_factory=list)
