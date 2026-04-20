"""酒店 / 商旅共享决策规划器。

这一层承接同类候选与 bundle 候选的可行性过滤、加权排序、
以及解释依据生成。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal
from uuid import uuid4

from velaris_agent.decision.contracts import (
    BundleCandidate,
    BundleDecisionRequest,
    BundleDecisionResponse,
    CapabilityCandidate,
    RankedBundle,
    RankedCandidate,
)


_CANONICAL_WEIGHT_ALIASES: dict[str, str] = {
    "price": "price",
    "cost": "price",
    "eta": "eta",
    "time": "eta",
    "detour": "detour_cost",
    "detour_cost": "detour_cost",
    "preference": "preference_match",
    "preference_match": "preference_match",
    "style_match": "preference_match",
    "experience": "experience_value",
    "experience_value": "experience_value",
}

_DEFAULT_DOMAIN_WEIGHTS: dict[str, float] = {
    "price": 0.20,
    "eta": 0.30,
    "detour_cost": 0.20,
    "preference_match": 0.20,
    "experience_value": 0.10,
}

_DEFAULT_BUNDLE_WEIGHTS: dict[str, float] = {
    "price": 0.20,
    "eta": 0.30,
    "detour_cost": 0.20,
    "preference_match": 0.15,
    "experience_value": 0.15,
}

_UNAVAILABLE_STATUSES = {"sold_out", "unavailable", "out_of_stock", "closed"}

__all__ = [
    "evaluate_bundle_decision",
]


def evaluate_bundle_decision(request: BundleDecisionRequest) -> BundleDecisionResponse:
    """执行共享决策请求。"""

    if request.bundle_candidates or request.decision_type == "bundle_rank":
        return _evaluate_bundle_rank(request)
    return _evaluate_domain_rank(request)


def _evaluate_domain_rank(request: BundleDecisionRequest) -> BundleDecisionResponse:
    """执行同类候选排序。"""

    candidate_set = request.candidate_set
    if candidate_set is None:
        raise ValueError("domain_rank 请求必须携带 candidate_set")

    feasible_candidates, rejected_reasons = _filter_domain_candidates(
        candidate_set.candidates,
        candidate_set.hard_constraints,
    )
    if not feasible_candidates:
        return BundleDecisionResponse(
            decision_type="domain_rank",
            hard_constraint_report={
                "passed": False,
                "checks": _summarize_hard_constraints(candidate_set.hard_constraints),
                "rejected_candidate_ids": list(rejected_reasons),
            },
            why_not_others=[
                {
                    "candidate_id": candidate_id,
                    "reason": " / ".join(reasons) if reasons else "未通过硬约束过滤",
                }
                for candidate_id, reasons in rejected_reasons.items()
            ],
            uncertainty_flags=["no_feasible_candidate"],
            explanation_text="没有同类候选同时满足当前硬约束。",
            decision_trace_id=_build_trace_id("hotel-biztravel"),
        )

    ranked_output = _rank_candidates(
        candidates=feasible_candidates,
        weights=request.decision_weights or _DEFAULT_DOMAIN_WEIGHTS,
        score_builder=lambda candidate, peers: _build_domain_scores(candidate, peers),
        label_getter=lambda candidate: candidate.title,
        id_getter=lambda candidate: candidate.candidate_id,
    )
    candidate_map = {candidate.candidate_id: candidate for candidate in feasible_candidates}
    ranked_candidates = [
        RankedCandidate(
            candidate_id=item["id"],
            label=item["label"],
            score=item["total_score"],
            score_breakdown=dict(item["scores"]),
            hard_constraint_report={
                "passed": True,
                "checks": _candidate_checks(
                    candidate_map[item["id"]],
                    candidate_set.hard_constraints,
                ),
            },
            reason=_build_reason_from_scores(item["scores"], kind="candidate"),
        )
        for item in ranked_output
    ]

    why_selected = _build_why_selected(
        score_breakdown=ranked_candidates[0].score_breakdown,
        hard_constraints=candidate_set.hard_constraints,
        kind="candidate",
        selected_label=ranked_candidates[0].label,
    )
    why_not_others = _build_why_not_others(
        ranked_items=ranked_candidates,
        rejected_reasons=rejected_reasons,
        kind="candidate",
    )
    tradeoffs = _build_tradeoffs(
        top_item=ranked_candidates[0],
        runner_up=ranked_candidates[1] if len(ranked_candidates) > 1 else None,
        kind="candidate",
    )
    hard_constraint_report = {
        "passed": True,
        "checks": _summarize_hard_constraints(candidate_set.hard_constraints),
        "feasible_candidate_ids": [item.candidate_id for item in ranked_candidates],
        "rejected_candidate_ids": list(rejected_reasons),
    }
    explanation_text = _build_explanation_text(
        kind="candidate",
        selected_label=ranked_candidates[0].label,
        why_selected=why_selected,
        tradeoffs=tradeoffs,
    )
    return BundleDecisionResponse(
        decision_type="domain_rank",
        selected_candidate_id=ranked_candidates[0].candidate_id,
        ranked_candidates=ranked_candidates,
        score_breakdown=dict(ranked_candidates[0].score_breakdown),
        hard_constraint_report=hard_constraint_report,
        why_selected=why_selected,
        why_not_others=why_not_others,
        tradeoffs=tradeoffs,
        uncertainty_flags=_build_uncertainty_flags(
            hard_constraints=candidate_set.hard_constraints,
            feasible_count=len(ranked_candidates),
        ),
        explanation_text=explanation_text,
        decision_trace_id=_build_trace_id("hotel-biztravel"),
    )


def _evaluate_bundle_rank(request: BundleDecisionRequest) -> BundleDecisionResponse:
    """执行跨类 bundle 联合排序。"""

    feasible_bundles: list[BundleCandidate] = []
    rejected_reasons: dict[str, list[str]] = {}
    for bundle in request.bundle_candidates:
        reasons = _bundle_rejection_reasons(bundle, request.hard_constraints)
        if reasons:
            rejected_reasons[bundle.bundle_id] = reasons
            continue
        feasible_bundles.append(bundle)

    if not feasible_bundles:
        return BundleDecisionResponse(
            decision_type="bundle_rank",
            hard_constraint_report={
                "passed": False,
                "checks": _summarize_hard_constraints(request.hard_constraints),
                "rejected_bundle_ids": list(rejected_reasons),
            },
            why_not_others=[
                {
                    "bundle_id": bundle_id,
                    "reason": " / ".join(reasons) if reasons else "未通过 bundle 硬约束过滤",
                }
                for bundle_id, reasons in rejected_reasons.items()
            ],
            uncertainty_flags=["no_feasible_bundle"],
            explanation_text="没有 bundle 同时满足当前硬约束。",
            decision_trace_id=_build_trace_id("hotel-biztravel"),
        )

    ranked_output = _rank_bundles(
        bundles=feasible_bundles,
        weights=request.decision_weights or _DEFAULT_BUNDLE_WEIGHTS,
    )
    ranked_bundles = [
        RankedBundle(
            bundle_id=item["id"],
            score=item["total_score"],
            score_breakdown=dict(item["scores"]),
            hard_constraint_report=dict(
                next(
                    bundle.hard_constraint_report
                    for bundle in feasible_bundles
                    if bundle.bundle_id == item["id"]
                )
            ),
            reason=_build_reason_from_scores(item["scores"], kind="bundle"),
        )
        for item in ranked_output
    ]
    selected = ranked_bundles[0]
    selected_bundle = next(
        bundle for bundle in feasible_bundles if bundle.bundle_id == selected.bundle_id
    )
    why_selected = _build_why_selected(
        score_breakdown=selected.score_breakdown,
        hard_constraints=request.hard_constraints,
        kind="bundle",
        selected_label=selected.bundle_id,
    )
    why_not_others = _build_why_not_others(
        ranked_items=ranked_bundles,
        rejected_reasons=rejected_reasons,
        kind="bundle",
    )
    tradeoffs = _build_tradeoffs(
        top_item=selected,
        runner_up=ranked_bundles[1] if len(ranked_bundles) > 1 else None,
        kind="bundle",
    )
    hard_constraint_report = {
        "passed": True,
        "checks": _summarize_hard_constraints(request.hard_constraints),
        "feasible_bundle_ids": [item.bundle_id for item in ranked_bundles],
        "rejected_bundle_ids": list(rejected_reasons),
        "time_slack_minutes": selected_bundle.aggregates.time_slack_minutes,
    }
    explanation_text = _build_explanation_text(
        kind="bundle",
        selected_label=selected.bundle_id,
        why_selected=why_selected,
        tradeoffs=tradeoffs,
    )
    return BundleDecisionResponse(
        decision_type="bundle_rank",
        selected_bundle_id=selected.bundle_id,
        ranked_bundles=ranked_bundles,
        score_breakdown=dict(selected.score_breakdown),
        hard_constraint_report=hard_constraint_report,
        why_selected=why_selected,
        why_not_others=why_not_others,
        tradeoffs=tradeoffs,
        uncertainty_flags=_build_uncertainty_flags(
            hard_constraints=request.hard_constraints,
            feasible_count=len(ranked_bundles),
        ),
        explanation_text=explanation_text,
        decision_trace_id=_build_trace_id("hotel-biztravel"),
    )


def _rank_candidates(
    *,
    candidates: list[CapabilityCandidate],
    weights: dict[str, float],
    score_builder: Any,
    label_getter: Any,
    id_getter: Any,
) -> list[dict[str, Any]]:
    """把同类候选整理成统一加权排序结果。"""

    score_inputs: list[dict[str, Any]] = []
    for candidate in candidates:
        score_inputs.append(
            {
                "id": id_getter(candidate),
                "label": label_getter(candidate),
                "scores": score_builder(candidate, candidates),
            }
        )
    return _score_options(score_inputs, weights)


def _rank_bundles(*, bundles: list[BundleCandidate], weights: dict[str, float]) -> list[dict[str, Any]]:
    """把 bundle 候选整理成统一加权排序结果。"""

    score_inputs: list[dict[str, Any]] = []
    for bundle in bundles:
        score_inputs.append(
            {
                "id": bundle.bundle_id,
                "label": bundle.bundle_id,
                "scores": _build_bundle_scores(bundle, bundles),
            }
        )
    return _score_options(score_inputs, weights)


def _build_domain_scores(
    candidate: CapabilityCandidate,
    peers: list[CapabilityCandidate],
) -> dict[str, float]:
    """把同类候选的原始值转成 0..1 的可比较分数。"""

    prices = [peer.price for peer in peers if peer.price is not None]
    etas = [peer.eta_minutes for peer in peers if peer.eta_minutes is not None]
    detours = [peer.detour_minutes for peer in peers if peer.detour_minutes is not None]
    scores = dict(candidate.score_features)
    scores.setdefault("price", _inverse_score(candidate.price, prices))
    scores.setdefault("eta", _inverse_score(candidate.eta_minutes, etas))
    scores.setdefault("detour_cost", _inverse_score(candidate.detour_minutes, detours))
    scores.setdefault(
        "preference_match",
        _feature_value(candidate, "preference_match", fallback_keys=("style_match",)),
    )
    scores.setdefault(
        "experience_value",
        _feature_value(candidate, "experience_value", fallback_keys=("experience",)),
    )
    return _normalize_score_map(scores)


def _build_bundle_scores(
    bundle: BundleCandidate,
    peers: list[BundleCandidate],
) -> dict[str, float]:
    """把 bundle 聚合指标转成 0..1 的可比较分数。"""

    prices = [peer.aggregates.total_price for peer in peers if peer.aggregates.total_price is not None]
    etas = [peer.aggregates.total_eta_minutes for peer in peers if peer.aggregates.total_eta_minutes is not None]
    detours = [peer.aggregates.detour_minutes for peer in peers if peer.aggregates.detour_minutes is not None]
    scores = {
        "price": _inverse_score(bundle.aggregates.total_price, prices),
        "eta": _inverse_score(bundle.aggregates.total_eta_minutes, etas),
        "detour_cost": _inverse_score(bundle.aggregates.detour_minutes, detours),
        "preference_match": _clamp_score(bundle.aggregates.preference_match),
        "experience_value": _clamp_score(bundle.aggregates.experience_value),
    }
    return _normalize_score_map(scores)


def _filter_domain_candidates(
    candidates: list[CapabilityCandidate],
    hard_constraints: dict[str, Any],
) -> tuple[list[CapabilityCandidate], dict[str, list[str]]]:
    """按预算、可用性与绕路上限过滤同类候选。"""

    feasible: list[CapabilityCandidate] = []
    rejected: dict[str, list[str]] = {}
    for candidate in candidates:
        reasons = _candidate_rejection_reasons(candidate, hard_constraints)
        if reasons:
            rejected[candidate.candidate_id] = reasons
            continue
        feasible.append(candidate)
    return feasible, rejected


def _candidate_rejection_reasons(
    candidate: CapabilityCandidate,
    hard_constraints: dict[str, Any],
) -> list[str]:
    """生成同类候选的硬约束拒绝原因。"""

    reasons: list[str] = []
    if not candidate.available or candidate.inventory_status in _UNAVAILABLE_STATUSES:
        reasons.append("inventory_unavailable")

    budget_max = _coerce_float(hard_constraints.get("budget_max"))
    if budget_max is not None and candidate.price is not None and candidate.price > budget_max:
        reasons.append("budget_exceeded")

    max_detour_minutes = _coerce_float(hard_constraints.get("max_detour_minutes"))
    if (
        max_detour_minutes is not None
        and candidate.detour_minutes is not None
        and candidate.detour_minutes > max_detour_minutes
    ):
        reasons.append("detour_exceeded")

    required_status = hard_constraints.get("required_inventory_status")
    if required_status and candidate.inventory_status != required_status:
        reasons.append("inventory_status_mismatch")

    candidate_report = candidate.metadata.get("hard_constraint_report", {})
    if isinstance(candidate_report, dict) and candidate_report.get("passed") is False:
        reasons.extend(
            str(item)
            for item in candidate_report.get("checks", [])
        )
    return list(dict.fromkeys(reasons))


def _bundle_rejection_reasons(
    bundle: BundleCandidate,
    hard_constraints: dict[str, Any],
) -> list[str]:
    """生成 bundle 的硬约束拒绝原因。"""

    reasons: list[str] = []
    bundle_report = bundle.hard_constraint_report
    if isinstance(bundle_report, dict) and bundle_report.get("passed") is False:
        reasons.extend(str(item) for item in bundle_report.get("checks", []))

    budget_max = _coerce_float(hard_constraints.get("budget_max"))
    if (
        budget_max is not None
        and bundle.aggregates.total_price is not None
        and bundle.aggregates.total_price > budget_max
    ):
        reasons.append("budget_exceeded")

    max_detour_minutes = _coerce_float(hard_constraints.get("max_detour_minutes"))
    if (
        max_detour_minutes is not None
        and bundle.aggregates.detour_minutes is not None
        and bundle.aggregates.detour_minutes > max_detour_minutes
    ):
        reasons.append("detour_exceeded")

    if (
        bundle.aggregates.time_slack_minutes is not None
        and bundle.aggregates.time_slack_minutes <= 0
    ):
        reasons.append("time_slack_exhausted")

    return list(dict.fromkeys(reasons))


def _build_why_selected(
    *,
    score_breakdown: dict[str, float],
    hard_constraints: dict[str, Any],
    kind: Literal["candidate", "bundle"],
    selected_label: str,
) -> list[str]:
    """把综合得分拆成用户能理解的选择原因。"""

    reasons: list[str] = []
    if hard_constraints.get("budget_max") is not None:
        reasons.append("价格在当前预算内")
    if hard_constraints.get("max_detour_minutes") is not None:
        reasons.append("绕路成本控制在限制内")
    if score_breakdown.get("preference_match", 0.0) >= 0.8:
        reasons.append("更符合当前偏好")
    if score_breakdown.get("eta", 0.0) >= 0.8:
        reasons.append("完成/到达更快")
    if score_breakdown.get("detour_cost", 0.0) >= 0.8:
        reasons.append("路线更顺路")
    if kind == "bundle" and score_breakdown.get("experience_value", 0.0) >= 0.75:
        reasons.append("整体体验收益更高")
    if not reasons:
        reasons.append(f"{selected_label} 的综合权衡最优")
    return reasons


def _build_why_not_others(
    *,
    ranked_items: list[RankedCandidate] | list[RankedBundle],
    rejected_reasons: dict[str, list[str]],
    kind: Literal["candidate", "bundle"],
) -> list[dict[str, Any]]:
    """把未选项的原因整理成结构化说明。"""

    reasons: list[dict[str, Any]] = []
    for item_id, rejected in rejected_reasons.items():
        key = "candidate_id" if kind == "candidate" else "bundle_id"
        reasons.append(
            {
                key: item_id,
                "reason": " / ".join(rejected) if rejected else "未通过硬约束过滤",
            }
        )

    if len(ranked_items) <= 1:
        return reasons

    selected = ranked_items[0]
    for peer in ranked_items[1:]:
        gap_reason = _compare_ranked_items(selected.score_breakdown, peer.score_breakdown)
        key = "candidate_id" if kind == "candidate" else "bundle_id"
        if not any(entry.get(key) == getattr(peer, key) for entry in reasons):
            reasons.append(
                {
                    key: getattr(peer, key),
                    "reason": gap_reason,
                }
            )
    return reasons


def _build_tradeoffs(
    *,
    top_item: RankedCandidate | RankedBundle,
    runner_up: RankedCandidate | RankedBundle | None,
    kind: Literal["candidate", "bundle"],
) -> list[str]:
    """总结 top1 与备选方案之间的关键权衡。"""

    if runner_up is None:
        return []

    clauses: list[str] = []
    if top_item.score_breakdown.get("price", 0.0) < runner_up.score_breakdown.get("price", 0.0):
        clauses.append("价格略高，但综合体验更稳")
    elif top_item.score_breakdown.get("price", 0.0) > runner_up.score_breakdown.get("price", 0.0):
        clauses.append("价格更友好，但在其他维度上更均衡")

    if top_item.score_breakdown.get("eta", 0.0) > runner_up.score_breakdown.get("eta", 0.0):
        clauses.append("总 ETA 更短，时间余量更安全")
    if top_item.score_breakdown.get("detour_cost", 0.0) > runner_up.score_breakdown.get("detour_cost", 0.0):
        clauses.append("绕路更少，行程组织更顺")
    if kind == "bundle" and top_item.score_breakdown.get("experience_value", 0.0) > runner_up.score_breakdown.get("experience_value", 0.0):
        clauses.append("整体体验价值更高")
    return list(dict.fromkeys(clauses))


def _build_explanation_text(
    *,
    kind: Literal["candidate", "bundle"],
    selected_label: str,
    why_selected: list[str],
    tradeoffs: list[str],
) -> str:
    """生成可直接渲染给用户的自然语言解释。"""

    if kind == "bundle":
        prefix = f"推荐 bundle {selected_label}"
    else:
        prefix = f"推荐 {selected_label}"

    if tradeoffs:
        return f"{prefix}：{'；'.join(why_selected)}。权衡上，{'；'.join(tradeoffs)}。"
    return f"{prefix}：{'；'.join(why_selected)}。"


def _build_reason_from_scores(scores: dict[str, float], *, kind: Literal["candidate", "bundle"]) -> str:
    """把 top score 拆成简短的排序原因。"""

    if kind == "bundle":
        return (
            f"总价 {scores.get('price', 0.0):.2f}，"
            f"总 ETA {scores.get('eta', 0.0):.2f}，"
            f"绕路 {scores.get('detour_cost', 0.0):.2f}，"
            f"体验 {scores.get('experience_value', 0.0):.2f}"
        )
    return (
        f"价格 {scores.get('price', 0.0):.2f}，"
        f"ETA {scores.get('eta', 0.0):.2f}，"
        f"绕路 {scores.get('detour_cost', 0.0):.2f}，"
        f"偏好 {scores.get('preference_match', 0.0):.2f}"
    )


def _compare_ranked_items(lhs: dict[str, float], rhs: dict[str, float]) -> str:
    """比较两个评分拆解，提炼出最明显的差异点。"""

    deltas = {
        "price": lhs.get("price", 0.0) - rhs.get("price", 0.0),
        "eta": lhs.get("eta", 0.0) - rhs.get("eta", 0.0),
        "detour_cost": lhs.get("detour_cost", 0.0) - rhs.get("detour_cost", 0.0),
        "preference_match": lhs.get("preference_match", 0.0) - rhs.get("preference_match", 0.0),
        "experience_value": lhs.get("experience_value", 0.0) - rhs.get("experience_value", 0.0),
    }
    dominant = max(deltas, key=lambda key: abs(deltas[key]))
    if dominant == "price":
        return "价格权衡不如更优项"
    if dominant == "eta":
        return "总 ETA 更长，时间余量更弱"
    if dominant == "detour_cost":
        return "绕路更大，路线不如更优项顺"
    if dominant == "preference_match":
        return "偏好匹配度更弱"
    if dominant == "experience_value":
        return "整体体验价值更低"
    return "综合权衡不如更优项"


def _candidate_checks(
    candidate: CapabilityCandidate,
    hard_constraints: dict[str, Any],
) -> list[str]:
    """生成候选项通过硬约束后的检查摘要。"""

    checks: list[str] = []
    budget_max = _coerce_float(hard_constraints.get("budget_max"))
    if budget_max is not None and candidate.price is not None and candidate.price <= budget_max:
        checks.append("预算满足")
    if candidate.available and candidate.inventory_status not in _UNAVAILABLE_STATUSES:
        checks.append("可用")
    max_detour_minutes = _coerce_float(hard_constraints.get("max_detour_minutes"))
    if (
        max_detour_minutes is not None
        and candidate.detour_minutes is not None
        and candidate.detour_minutes <= max_detour_minutes
    ):
        checks.append("绕路满足")
    return checks


def _summarize_hard_constraints(hard_constraints: dict[str, Any]) -> list[str]:
    """把硬约束整理成短摘要，方便前端直接展示。"""

    summary: list[str] = []
    if hard_constraints.get("budget_max") is not None:
        summary.append("预算满足")
    if hard_constraints.get("max_detour_minutes") is not None:
        summary.append("绕路上限满足")
    if hard_constraints.get("required_inventory_status") is not None:
        summary.append("库存状态受限")
    if hard_constraints.get("must_finish_before") is not None:
        summary.append("完成时间受限")
    return summary


def _build_uncertainty_flags(
    *,
    hard_constraints: dict[str, Any],
    feasible_count: int,
) -> list[str]:
    """生成需要向用户或审计层提示的不确定性标记。"""

    flags: list[str] = []
    if feasible_count <= 1:
        flags.append("small_feasible_set")
    if hard_constraints.get("must_finish_before") is not None:
        flags.append("time_deadline_sensitive")
    return flags


def _normalize_score_map(scores: dict[str, float]) -> dict[str, float]:
    """把别名分数统一收口到 canonical key。"""

    normalized: dict[str, float] = {}
    for key, value in scores.items():
        canonical = _CANONICAL_WEIGHT_ALIASES.get(key, key)
        normalized[canonical] = _clamp_score(value)
    return normalized


def _feature_value(
    candidate: CapabilityCandidate,
    preferred_key: str,
    *,
    fallback_keys: tuple[str, ...] = (),
) -> float:
    """从候选项里提取单个归一化特征值。"""

    if preferred_key in candidate.score_features:
        return _clamp_score(candidate.score_features[preferred_key])
    if preferred_key in candidate.domain_features:
        return _clamp_score(candidate.domain_features[preferred_key])
    for key in fallback_keys:
        if key in candidate.score_features:
            return _clamp_score(candidate.score_features[key])
        if key in candidate.domain_features:
            return _clamp_score(candidate.domain_features[key])
    return 0.0


def _score_options(options: list[dict[str, Any]], weights: dict[str, float]) -> list[dict[str, Any]]:
    """对候选项按加权和做统一排序。"""

    normalized_weights = _normalize_weights(weights)
    ranked: list[dict[str, Any]] = []
    for option in options:
        raw_scores = option.get("scores", {})
        total_score = 0.0
        normalized_scores: dict[str, float] = {}
        for dimension, weight in normalized_weights.items():
            score = _clamp_score(float(raw_scores.get(dimension, 0.0) or 0.0))
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


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """把权重别名收口，并归一化到总和为 1。"""

    normalized: dict[str, float] = {}
    for key, value in weights.items():
        canonical = _CANONICAL_WEIGHT_ALIASES.get(key, key)
        normalized[canonical] = max(0.0, float(value))

    total_weight = sum(normalized.values())
    if total_weight <= 0:
        return {key: 0.0 for key in normalized}
    return {key: value / total_weight for key, value in normalized.items()}


def _inverse_score(value: float | None, samples: Sequence[float | None]) -> float:
    """把越低越好的原始值映射到 0..1。"""

    valid_samples = [float(item) for item in samples if item is not None]
    if value is None or not valid_samples:
        return 0.0
    minimum = min(valid_samples)
    maximum = max(valid_samples)
    if maximum == minimum:
        return 1.0
    return _clamp_score((maximum - float(value)) / (maximum - minimum))


def _clamp_score(value: float | None) -> float:
    """把分数限制在 0..1。"""

    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _coerce_float(value: Any) -> float | None:
    """尽量把任意输入转成浮点数。"""

    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_trace_id(prefix: str) -> str:
    """生成便于审计追踪的稳定前缀 trace ID。"""

    return f"{prefix}-{uuid4().hex[:12]}"
