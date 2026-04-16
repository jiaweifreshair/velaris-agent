"""Procurement feasibility operator。"""

from __future__ import annotations

from velaris_agent.decision.context import DecisionExecutionContext, OperatorTraceRecord
from velaris_agent.decision.operators.base import OperatorSpec
from velaris_agent.memory.types import DecisionOptionSchema


class FeasibilityOp:
    """按采购硬约束划分可行域。

    这个算子把预算、交付、合规、可用性过滤从 NormalizationOp 中拆出来，
    让标准化与可行域判断分层，方便后续接入 Pareto frontier。
    """

    spec = OperatorSpec("feasibility")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        """基于 normalized options 产出 accepted/rejected options。"""

        accepted: list[DecisionOptionSchema] = []
        rejected: list[DecisionOptionSchema] = []
        rejection_reasons: dict[str, list[str]] = {}

        for option in context.normalized_options:
            raw_option = dict(option.metadata.get("raw_option", {}))
            reasons = _collect_rejection_reasons(
                option=raw_option,
                intent=context.intent,
            )
            if reasons:
                rejected.append(option)
                rejection_reasons[option.option_id] = reasons
            else:
                accepted.append(option)

        _normalize_lower_is_better_metrics(
            accepted,
            metric_ids=["cost", "delivery"],
        )

        context.accepted_options = accepted
        context.rejected_options = rejected
        context.rejection_reasons = rejection_reasons
        context.operator_traces.append(
            OperatorTraceRecord(
                operator_id=self.spec.operator_id,
                operator_version=self.spec.operator_version,
                input_schema_version=self.spec.input_schema_version,
                output_schema_version=self.spec.output_schema_version,
                confidence=1.0 if accepted else 0.0,
                warnings=["no_feasible_option"] if not accepted else [],
            )
        )
        return context


def _collect_rejection_reasons(
    *,
    option: dict[str, object],
    intent: dict[str, object],
) -> list[str]:
    """按采购场景的硬约束生成拒绝原因列表。"""

    reasons: list[str] = []
    if not bool(option.get("available", True)):
        reasons.append("option_unavailable")

    budget_max = intent.get("budget_max")
    if budget_max is not None and float(option.get("price_cny", 0) or 0) > float(budget_max):
        reasons.append("budget_exceeded")

    max_delivery_days = intent.get("max_delivery_days")
    if max_delivery_days is not None and float(
        option.get("delivery_days", 0) or 0
    ) > float(max_delivery_days):
        reasons.append("delivery_exceeds_limit")

    if bool(intent.get("require_compliance", True)) and float(
        option.get("compliance_score", 0) or 0
    ) < 0.9:
        reasons.append("compliance_below_threshold")

    return reasons


def _normalize_lower_is_better_metrics(
    options: list[DecisionOptionSchema],
    *,
    metric_ids: list[str],
) -> None:
    """只在可行集合上重算 lower-is-better 指标，保证排序口径一致。"""

    for metric_id in metric_ids:
        samples = _collect_metric_samples(options, metric_id)
        for option in options:
            metric = next(
                (item for item in option.metrics if item.metric_id == metric_id),
                None,
            )
            if metric is None:
                continue
            metric.normalized_score = _inverse_score(
                float(metric.raw_value or 0),
                samples,
            )


def _collect_metric_samples(
    options: list[DecisionOptionSchema],
    metric_id: str,
) -> list[float]:
    """从可行候选中提取指定指标的原始样本，用于反向归一化。"""

    samples: list[float] = []
    for option in options:
        metric = next(
            (item for item in option.metrics if item.metric_id == metric_id),
            None,
        )
        if metric is None:
            continue
        samples.append(float(metric.raw_value or 0))
    return samples


def _inverse_score(value: float, samples: list[float]) -> float:
    """把越低越好的原始值映射为 0..1 分值。"""

    if not samples:
        return 0.0
    minimum = min(samples)
    maximum = max(samples)
    if maximum == minimum:
        return 1.0
    return max(0.0, min(1.0, (maximum - value) / (maximum - minimum)))
