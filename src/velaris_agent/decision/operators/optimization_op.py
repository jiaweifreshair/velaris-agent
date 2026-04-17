"""Optimization helper 与兼容算子。"""

from __future__ import annotations

from typing import Any

from velaris_agent.decision.context import DecisionExecutionContext, OperatorTraceRecord
from velaris_agent.decision.operators.base import OperatorSpec


class OptimizationOp:
    """兼容旧链路的 weighted-sum 排序算子。"""

    spec = OperatorSpec("optimization")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        """仅对 accepted options 做排序，保留给过渡链或兼容路径使用。"""

        if not context.accepted_options:
            context.ranked_options = []
            context.recommended_option_id = None
            context.operator_traces.append(
                OperatorTraceRecord(
                    operator_id=self.spec.operator_id,
                    operator_version=self.spec.operator_version,
                    input_schema_version=self.spec.input_schema_version,
                    output_schema_version=self.spec.output_schema_version,
                    confidence=0.0,
                    warnings=["no_feasible_option"],
                )
            )
            return context

        ranked = score_weighted_sum(
            options=[
                {
                    "id": option.option_id,
                    "label": option.label,
                    "scores": {
                        metric.metric_id: metric.normalized_score
                        for metric in option.metrics
                    },
                }
                for option in context.accepted_options
            ],
            weights=merge_weights(
                DEFAULT_PROCUREMENT_WEIGHTS,
                context.decision_weights,
            ),
        )
        ranked_ids = [item["id"] for item in ranked]
        ranked_map = {item["id"]: item for item in ranked}
        context.ranked_options = sorted(
            context.accepted_options,
            key=lambda item: ranked_ids.index(item.option_id),
        )
        for option in context.ranked_options:
            option.metadata["total_score"] = ranked_map[option.option_id]["total_score"]
            option.metadata["score_breakdown"] = ranked_map[option.option_id]["scores"]
        context.recommended_option_id = ranked_ids[0] if ranked_ids else None
        context.operator_traces.append(
            OperatorTraceRecord(
                operator_id=self.spec.operator_id,
                operator_version=self.spec.operator_version,
                input_schema_version=self.spec.input_schema_version,
                output_schema_version=self.spec.output_schema_version,
                confidence=1.0 if ranked_ids else 0.0,
            )
        )
        return context


DEFAULT_PROCUREMENT_WEIGHTS = {
    "cost": 0.28,
    "quality": 0.24,
    "delivery": 0.16,
    "compliance": 0.22,
    "risk": 0.10,
}


def score_weighted_sum(
    *,
    options: list[dict[str, Any]],
    weights: dict[str, float],
) -> list[dict[str, Any]]:
    """在 decision core 内实现最小 weighted-sum 排序。"""

    total_weight = sum(max(weight, 0.0) for weight in weights.values())
    normalized_weights = {
        dimension: (max(weight, 0.0) / total_weight if total_weight > 0 else 0.0)
        for dimension, weight in weights.items()
    }

    ranked: list[dict[str, Any]] = []
    for option in options:
        raw_scores = option.get("scores", {})
        total_score = 0.0
        normalized_scores: dict[str, float] = {}
        for dimension, weight in normalized_weights.items():
            score = _clamp_score(raw_scores.get(dimension, 0.0))
            normalized_scores[dimension] = score
            total_score += score * weight
        ranked.append(
            {
                "id": option.get("id", ""),
                "label": option.get("label", option.get("id", "")),
                "scores": normalized_scores,
                "total_score": round(total_score, 4),
            }
        )

    return sorted(ranked, key=lambda item: item["total_score"], reverse=True)


def _clamp_score(value: float) -> float:
    """把分值约束在 0..1 区间。"""

    return max(0.0, min(1.0, float(value)))


def merge_weights(
    default_weights: dict[str, float],
    override_weights: dict[str, float],
) -> dict[str, float]:
    """用显式传入权重覆盖默认权重，并忽略未知维度。"""

    merged = dict(default_weights)
    for dimension, value in override_weights.items():
        if dimension not in merged:
            continue
        merged[dimension] = float(value)
    return merged
