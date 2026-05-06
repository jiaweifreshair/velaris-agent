"""Velaris 原生业务能力引擎。

实现三类共享能力：
1. 业务场景识别与能力规划（通过 ScenarioRegistry 插件化）。
2. 多维评分与排序。
3. travel / tokencost / robotclaw / procurement / lifegoal / hotel_biztravel 场景执行。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from velaris_agent.decision.graph import execute_decision_graph
from velaris_agent.decision.shared_decision import (
    BundleDecisionResponse,
    build_bundle_decision_request,
    evaluate_bundle_decision,
)
from velaris_agent.biz.hotel_biztravel_inference import enrich_hotel_biztravel_response
from velaris_agent.memory.conflict_engine import ConflictDetectionEngine
from velaris_agent.memory.negotiation import NegotiationStrategy
from velaris_agent.memory.types import (
    DecisionAuditSchema,
    DecisionOptionMetric,
    DecisionOptionSchema,
    StakeholderContext,
    StakeholderMapModel,
    get_decision_metric,
)
from velaris_agent.scenarios.procurement.types import (
    ProcurementAuditTrace,
    ProcurementCompareResult,
    ProcurementIntentSlots,
    ProcurementOption,
    ProcurementWorkflowStatus,
)
from velaris_agent.scenarios.registry import ScenarioRegistry
from velaris_agent.scenarios.travel_protocol import (
    TravelAuditTrace,
    TravelCompareResult,
    TravelIntentSlots,
    TravelNextAction,
    TravelOption,
    TravelWorkflowStatus,
)


# ── ScenarioRegistry：SKILL.md 驱动的场景注册表 ───────────────
# 全局单例，替代原有 _SCENARIO_* 硬编码字典
_registry = ScenarioRegistry()


def get_scenario_registry() -> ScenarioRegistry:
    """获取全局 ScenarioRegistry 实例。"""
    return _registry

_OPENCLAW_MIN_SAFETY = 0.9
_OPENCLAW_MIN_COMPLIANCE = 0.9


def _resolve_entry_point(entry_point: str) -> Any:
    """解析 entry_point 字符串为可调用的场景执行器。

    格式：'module.path:function_name'（与 setuptools entry_point 兼容）。
    """
    if ":" not in entry_point:
        return None
    module_path, func_name = entry_point.rsplit(":", 1)
    try:
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, func_name, None)
    except (ImportError, AttributeError):
        return None

_TRAVEL_CITY_TOKENS: tuple[str, ...] = (
    "北京",
    "上海",
    "广州",
    "深圳",
    "杭州",
    "成都",
    "武汉",
    "南京",
    "西安",
    "重庆",
    "天津",
    "苏州",
    "长沙",
    "青岛",
    "厦门",
    "郑州",
    "昆明",
    "海口",
    "三亚",
)
_TRAVEL_CITY_PATTERN = "|".join(sorted((re.escape(city) for city in _TRAVEL_CITY_TOKENS), key=len, reverse=True))
_TRAVEL_QUERY_ROUTE_PATTERN = re.compile(
    rf"(?:从\s*)?(?P<origin>{_TRAVEL_CITY_PATTERN})\s*(?:飞往|飞去|飞到|到|至)\s*(?P<destination>{_TRAVEL_CITY_PATTERN})"
)
_TRAVEL_QUERY_DESTINATION_PATTERN = re.compile(rf"去\s*(?P<destination>{_TRAVEL_CITY_PATTERN})")
_TRAVEL_TEXT_ROUTE_PATTERN = re.compile(
    rf"(?P<origin>{_TRAVEL_CITY_PATTERN})\s*(?:-|－|—|~|～|/|到|至|→)\s*(?P<destination>{_TRAVEL_CITY_PATTERN})"
)


def infer_scenario(query: str, scenario: str | None = None) -> str:
    """识别业务场景（通过 ScenarioRegistry，含高级匹配规则）。"""
    spec = _registry.match(query, scenario_hint=scenario)
    return spec.name if spec else "general"


def build_capability_plan(
    query: str,
    constraints: dict[str, Any] | None = None,
    scenario: str | None = None,
    stakeholder_map: StakeholderMapModel | None = None,
) -> dict[str, Any]:
    """生成业务能力规划。"""
    normalized_constraints = constraints or {}
    resolved_scenario = infer_scenario(query, scenario)
    capabilities = list(_registry.get_capabilities(resolved_scenario))
    governance = _registry.get_governance(resolved_scenario)
    if "requires_audit" in normalized_constraints:
        governance["requires_audit"] = bool(normalized_constraints["requires_audit"])

    decision_weights = dict(_registry.get_weights(resolved_scenario))

    plan: dict[str, Any] = {
        "scenario": resolved_scenario,
        "query": query,
        "constraints": normalized_constraints,
        "capabilities": capabilities,
        "decision_weights": decision_weights,
        "governance": governance,
        "recommended_tools": list(_registry.get_recommended_tools(resolved_scenario)),
    }

    if stakeholder_map is not None:
        stakeholder_context = _build_stakeholder_context(stakeholder_map)
        plan["stakeholder_context"] = stakeholder_context.model_dump(mode="json")
        plan["decision_weights"] = _merge_stakeholder_weights(
            decision_weights, stakeholder_map,
        )
        # Append warnings for high-severity conflicts.
        warnings: list[str] = []
        for conflict in stakeholder_context.conflicts:
            if conflict.severity > 0.5:
                warnings.append(
                    f"⚠ Unresolved stakeholder conflict on '{conflict.dimension}' "
                    f"(severity={conflict.severity:.2f})"
                )
        if warnings:
            plan["explanation"] = "\n".join(warnings)

    return plan


def _build_stakeholder_context(stakeholder_map: StakeholderMapModel) -> StakeholderContext:
    """Produce a StakeholderContext from a StakeholderMapModel.

    Runs conflict detection and negotiation strategy generation, then
    assembles the full context including warnings for high-severity conflicts.
    """
    conflict_engine = ConflictDetectionEngine()
    conflicts = conflict_engine.detect(stakeholder_map)

    negotiation = NegotiationStrategy()
    proposals = negotiation.generate(conflicts, stakeholder_map)

    warnings: list[str] = []
    for conflict in conflicts:
        if conflict.severity > 0.5:
            warnings.append(
                f"Conflict on '{conflict.dimension}' between "
                f"{conflict.stakeholder_a_id} and {conflict.stakeholder_b_id} "
                f"(severity={conflict.severity:.2f})"
            )

    return StakeholderContext(
        scenario=stakeholder_map.scenario,
        stakeholder_ids=[s.stakeholder_id for s in stakeholder_map.stakeholders],
        alignment_matrix=stakeholder_map.alignment_matrix,
        conflicts=conflicts,
        negotiation_proposals=proposals,
        warnings=warnings,
    )


def _merge_stakeholder_weights(
    decision_weights: dict[str, float],
    stakeholder_map: StakeholderMapModel,
) -> dict[str, float]:
    """Average stakeholder influence weights with existing scenario weights.

    For each dimension in *decision_weights*, if any stakeholder has an
    influence weight on that dimension, the final weight is the average of
    the scenario weight and the mean stakeholder influence for that dimension.
    Dimensions not present in any stakeholder's influence_weights are kept
    unchanged.
    """
    merged = dict(decision_weights)
    for dim, scenario_weight in decision_weights.items():
        influences: list[float] = []
        for s in stakeholder_map.stakeholders:
            if dim in s.influence_weights:
                influences.append(s.influence_weights[dim])
        if influences:
            mean_influence = sum(influences) / len(influences)
            merged[dim] = (scenario_weight + mean_influence) / 2.0
    return merged


def score_options(options: list[dict[str, Any]], weights: dict[str, float]) -> list[dict[str, Any]]:
    """对候选项进行多维评分。"""
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


def run_scenario(scenario: str, payload: dict[str, Any]) -> dict[str, Any]:
    """运行一个业务场景。

    优先从 ScenarioRegistry 的 entry_point 动态加载执行器；
    找不到 entry_point 时回退到本地硬编码映射（向后兼容）；
    场景不存在时走 general 兜底。
    """
    # 1. 尝试从 ScenarioRegistry 的 entry_point 动态加载
    entry_point = _registry.get_entry_point(scenario)
    if entry_point:
        runner = _resolve_entry_point(entry_point)
        if runner is not None:
            return runner(payload)

    # 2. 回退：本地硬编码映射（向后兼容，渐进迁移）
    _HARDCODED_RUNNERS: dict[str, Any] = {
        "lifegoal": _run_lifegoal_scenario,
        "travel": _run_travel_scenario,
        "hotel_biztravel": _run_hotel_biztravel_scenario,
        "tokencost": _run_tokencost_scenario,
        "robotclaw": _run_robotclaw_scenario,
        "procurement": _run_procurement_scenario,
        "general": _run_general_scenario,
    }
    runner = _HARDCODED_RUNNERS.get(scenario)
    if runner is not None:
        return runner(payload)

    # 3. 兜底：场景未注册时走 general
    fallback = _registry.get_fallback_scenario(scenario)
    if fallback and fallback != scenario:
        return run_scenario(fallback, payload)

    # 4. 最终兜底
    return _run_general_scenario(payload)


def _run_travel_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    """执行商旅对比场景。

    这里不仅返回排序结果，还会把结果包装成统一可确认协议，方便前端直接做 Demo。
    """
    query = str(payload.get("query", "") or "")
    user_id = str(payload.get("user_id", "anonymous") or "anonymous")
    session_id = str(payload.get("session_id", "") or f"travel-session-{uuid4().hex[:10]}")
    source_type = str(payload.get("source_type", "inline") or "inline")
    selected_option_id = _as_optional_str(payload.get("selected_option_id"))
    proposal_id = _as_optional_str(payload.get("proposal_id")) or f"travel-proposal-{uuid4().hex[:10]}"
    confirm = bool(payload.get("confirm", False) or payload.get("confirmation", False))

    inferred_budget = _extract_budget_from_query(query)
    budget_raw = payload.get("budget_max", inferred_budget if inferred_budget is not None else 0)
    budget_max = float(budget_raw or 0)
    direct_only = bool(payload.get("direct_only", _infer_direct_only(query)))
    origin, destination = _extract_route_from_query(query)
    raw_options = payload.get("options", [])

    eligible_options = [
        option for option in raw_options
        if (budget_max <= 0 or float(option.get("price", 0)) <= budget_max)
        and (not direct_only or bool(option.get("direct", False)))
    ]
    if not eligible_options:
        summary = "没有满足预算和直飞约束的商旅方案。"
        return TravelCompareResult(
            status=TravelWorkflowStatus.NO_MATCH,
            query=query,
            user_id=user_id,
            session_id=session_id,
            intent_slots=TravelIntentSlots(
                query=query,
                origin=origin,
                destination=destination,
                budget_max=budget_max if budget_max > 0 else None,
                direct_only=direct_only,
            ),
            options=[],
            recommended=None,
            cheapest=None,
            accepted_option_ids=[],
            summary=summary,
            explanation=summary,
            requires_confirmation=False,
            next_actions=[
                TravelNextAction(
                    action="adjust_constraints",
                    label="放宽约束后重试",
                    payload={"budget_max": budget_max if budget_max > 0 else None, "direct_only": direct_only},
                )
            ],
            audit_trace=TravelAuditTrace(
                trace_id=f"travel-trace-{uuid4().hex[:10]}",
                source_type=source_type,
                accepted_option_ids=[],
                recommended_option_id=None,
                selected_option_id=None,
                proposal_id=proposal_id,
                summary=summary,
                created_at=_now_iso(),
            ),
        ).model_dump(mode="json")

    prices = [float(option.get("price", 0)) for option in eligible_options]
    durations = [float(option.get("duration_minutes", 0)) for option in eligible_options]
    route_score_map = {
        str(option.get("id", "")): _score_travel_option_route(
            option=option,
            origin=origin,
            destination=destination,
        )
        for option in eligible_options
    }
    has_exact_route_match = any(score >= 2 for score in route_score_map.values())
    display_options = [
        _prepare_travel_option_for_display(
            option=option,
            origin=origin,
            destination=destination,
            force_route_override=bool(origin and destination and not has_exact_route_match),
        )
        for option in eligible_options
    ]

    scored_input: list[dict[str, Any]] = []
    for option in display_options:
        scored_input.append(
            {
                "id": option.get("id", ""),
                "label": option.get("label", option.get("id", "")),
                "scores": {
                    "price": _inverse_score(float(option.get("price", 0)), prices),
                    "time": _inverse_score(float(option.get("duration_minutes", 0)), durations),
                    "comfort": _clamp_score(float(option.get("comfort", 0))),
                },
            }
        )

    ranked = score_options(scored_input, _registry.get_weights("travel"))
    cheapest = min(display_options, key=lambda option: float(option.get("price", 0)))
    ranked_map = {item["id"]: item for item in ranked}
    normalized_options = [
        _build_travel_option(
            option=option,
            ranked_item=ranked_map.get(str(option.get("id", ""))),
            budget_max=budget_max,
            direct_only=direct_only,
        )
        for option in display_options
    ]
    normalized_options.sort(
        key=lambda item: (
            route_score_map.get(item.id, 0),
            item.total_score if item.total_score is not None else -1.0,
        ),
        reverse=True,
    )

    recommended = normalized_options[0]
    summary = f"共筛选出 {len(eligible_options)} 个满足约束的商旅方案。"
    explanation = _build_travel_explanation(
        option=recommended,
        budget_max=budget_max,
        direct_only=direct_only,
        candidate_count=len(normalized_options),
    )
    accepted_option_ids = [option.id for option in normalized_options]
    selected_id = selected_option_id or recommended.id
    selected_option = next((item for item in normalized_options if item.id == selected_id), None)

    if confirm and selected_option is None:
        summary = f"未找到待确认的商旅方案: {selected_id}"
        return TravelCompareResult(
            status=TravelWorkflowStatus.INVALID_CONFIRMATION,
            query=query,
            user_id=user_id,
            session_id=session_id,
            intent_slots=TravelIntentSlots(
                query=query,
                origin=origin,
                destination=destination,
                budget_max=budget_max if budget_max > 0 else None,
                direct_only=direct_only,
            ),
            options=normalized_options,
            recommended=recommended,
            cheapest={
                "id": cheapest.get("id", ""),
                "price": float(cheapest.get("price", 0)),
                "label": cheapest.get("label", cheapest.get("id", "")),
            },
            accepted_option_ids=accepted_option_ids,
            summary=summary,
            explanation=summary,
            requires_confirmation=True,
            next_actions=[
                TravelNextAction(
                    action="confirm_travel_option",
                    label="改用推荐方案确认",
                    payload={"selected_option_id": recommended.id, "proposal_id": proposal_id},
                )
            ],
            proposal_id=proposal_id,
            audit_trace=TravelAuditTrace(
                trace_id=f"travel-trace-{uuid4().hex[:10]}",
                source_type=source_type,
                accepted_option_ids=accepted_option_ids,
                recommended_option_id=recommended.id,
                selected_option_id=selected_option_id,
                proposal_id=proposal_id,
                summary=summary,
                created_at=_now_iso(),
            ),
        ).model_dump(mode="json")

    if confirm and selected_option is not None:
        external_ref = _as_optional_str(payload.get("external_ref")) or f"TRAVEL-{uuid4().hex[:10].upper()}"
        summary = f"已确认商旅方案 {selected_option.label}，可进入下单或跳转外部履约。"
        return TravelCompareResult(
            status=TravelWorkflowStatus.COMPLETED,
            query=query,
            user_id=user_id,
            session_id=session_id,
            intent_slots=TravelIntentSlots(
                query=query,
                origin=origin,
                destination=destination,
                budget_max=budget_max if budget_max > 0 else None,
                direct_only=direct_only,
            ),
            options=normalized_options,
            recommended=selected_option,
            cheapest={
                "id": cheapest.get("id", ""),
                "price": float(cheapest.get("price", 0)),
                "label": cheapest.get("label", cheapest.get("id", "")),
            },
            accepted_option_ids=accepted_option_ids,
            summary=summary,
            explanation=f"{selected_option.label} 已完成确认，后续可使用 external_ref 追踪履约。",
            requires_confirmation=False,
            next_actions=[
                TravelNextAction(
                    action="track_travel_order",
                    label="查看订单追踪",
                    payload={"external_ref": external_ref},
                )
            ],
            proposal_id=proposal_id,
            execution_status="completed",
            external_ref=external_ref,
            audit_trace=TravelAuditTrace(
                trace_id=f"travel-trace-{uuid4().hex[:10]}",
                source_type=source_type,
                accepted_option_ids=accepted_option_ids,
                recommended_option_id=recommended.id,
                selected_option_id=selected_option.id,
                proposal_id=proposal_id,
                summary=summary,
                created_at=_now_iso(),
            ),
        ).model_dump(mode="json")

    return TravelCompareResult(
        status=TravelWorkflowStatus.REQUIRES_CONFIRMATION,
        query=query,
        user_id=user_id,
        session_id=session_id,
        intent_slots=TravelIntentSlots(
            query=query,
            origin=origin,
            destination=destination,
            budget_max=budget_max if budget_max > 0 else None,
            direct_only=direct_only,
        ),
        options=normalized_options,
        recommended=recommended,
        cheapest={
            "id": cheapest.get("id", ""),
            "price": float(cheapest.get("price", 0)),
            "label": cheapest.get("label", cheapest.get("id", "")),
        },
        accepted_option_ids=accepted_option_ids,
        summary=summary,
        explanation=explanation,
        requires_confirmation=True,
        next_actions=[
            TravelNextAction(
                action="confirm_travel_option",
                label="确认推荐方案",
                payload={"selected_option_id": recommended.id, "proposal_id": proposal_id},
            ),
            TravelNextAction(
                action="view_all_options",
                label="查看全部候选方案",
                payload={"accepted_option_ids": accepted_option_ids},
            ),
        ],
        proposal_id=proposal_id,
        audit_trace=TravelAuditTrace(
            trace_id=f"travel-trace-{uuid4().hex[:10]}",
            source_type=source_type,
            accepted_option_ids=accepted_option_ids,
            recommended_option_id=recommended.id,
            selected_option_id=None,
            proposal_id=proposal_id,
            summary=summary,
            created_at=_now_iso(),
        ),
    ).model_dump(mode="json")


def _run_tokencost_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    current_monthly_cost = float(payload.get("current_monthly_cost", 0))
    target_monthly_cost = float(payload.get("target_monthly_cost", 0))
    raw_suggestions = payload.get("suggestions", [])
    effort_scores = {"low": 1.0, "medium": 0.75, "high": 0.5}

    savings = [float(item.get("estimated_saving", 0)) for item in raw_suggestions]
    max_saving = max(savings) if savings else 0.0

    scored_input: list[dict[str, Any]] = []
    for item in raw_suggestions:
        scored_input.append(
            {
                "id": item.get("id", ""),
                "label": item.get("title", item.get("id", "")),
                "scores": {
                    "cost": (float(item.get("estimated_saving", 0)) / max_saving) if max_saving > 0 else 0.0,
                    "quality": _clamp_score(float(item.get("quality_retention", 0))),
                    "speed": _clamp_score(
                        (float(item.get("execution_speed", 0)) + effort_scores.get(str(item.get("effort", "medium")), 0.75)) / 2
                    ),
                },
            }
        )

    recommendations = score_options(scored_input, _registry.get_weights("tokencost"))
    total_estimated_saving = round(sum(savings), 2)
    projected_monthly_cost = round(max(0.0, current_monthly_cost - total_estimated_saving), 2)
    return {
        "scenario": "tokencost",
        "recommendations": recommendations,
        "total_estimated_saving": total_estimated_saving,
        "projected_monthly_cost": projected_monthly_cost,
        "feasible": projected_monthly_cost <= target_monthly_cost if target_monthly_cost > 0 else True,
        "summary": f"预计月度节省 {total_estimated_saving:.0f}，目标成本 {target_monthly_cost:.0f}。",
    }


def _run_robotclaw_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    max_budget_cny = float(payload.get("max_budget_cny", 0) or 0)
    raw_proposals = payload.get("proposals", [])
    eligible = [
        item for item in raw_proposals
        if bool(item.get("available", False))
        and (max_budget_cny <= 0 or float(item.get("price_cny", 0)) <= max_budget_cny)
    ]
    if not eligible:
        return {
            "scenario": "robotclaw",
            "recommended": None,
            "contract_ready": False,
            "accepted_option_ids": [],
            "summary": "没有满足预算和可用性要求的调度提案。",
        }

    compliant_candidates = [
        item for item in eligible
        if float(item.get("safety_score", 0)) >= _OPENCLAW_MIN_SAFETY
        and float(item.get("compliance_score", 0)) >= _OPENCLAW_MIN_COMPLIANCE
    ]
    ranked_candidates = compliant_candidates or eligible

    prices = [float(item.get("price_cny", 0)) for item in ranked_candidates]
    etas = [float(item.get("eta_minutes", 0)) for item in ranked_candidates]
    scored_input: list[dict[str, Any]] = []
    for item in ranked_candidates:
        scored_input.append(
            {
                "id": item.get("id", ""),
                "label": item.get("label", item.get("id", "")),
                "scores": {
                    "safety": _clamp_score(float(item.get("safety_score", 0))),
                    "eta": _inverse_score(float(item.get("eta_minutes", 0)), etas),
                    "cost": _inverse_score(float(item.get("price_cny", 0)), prices),
                    "compliance": _clamp_score(float(item.get("compliance_score", 0))),
                },
            }
        )

    ranked = score_options(scored_input, _registry.get_weights("robotclaw"))
    top_id = ranked[0]["id"]
    top_source = next(item for item in ranked_candidates if item.get("id", "") == top_id)
    return {
        "scenario": "robotclaw",
        "recommended": ranked[0],
        "accepted_option_ids": [item.get("id", "") for item in ranked_candidates],
        "contract_ready": (
            float(top_source.get("safety_score", 0)) >= 0.9
            and float(top_source.get("compliance_score", 0)) >= 0.9
        ),
        "summary": (
            f"共评估 {len(eligible)} 个可用提案，"
            f"其中 {len(ranked_candidates)} 个通过安全与合规门槛。"
        ),
    }


def _run_procurement_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    """执行企业采购推荐场景。"""

    query = str(payload.get("query", "") or "")
    session_id = str(payload.get("session_id", "") or f"procurement-session-{uuid4().hex[:10]}")
    source_type = str(payload.get("source_type", "inline") or "inline")
    proposal_id = _as_optional_str(payload.get("proposal_id")) or f"procurement-proposal-{uuid4().hex[:10]}"
    budget_in_query = _extract_budget_from_query(query)
    budget_raw = payload.get("budget_max", budget_in_query if budget_in_query is not None else 0)
    budget_max = float(budget_raw or 0)
    require_compliance = bool(payload.get("require_compliance", True))
    max_delivery_days = _as_optional_int(payload.get("max_delivery_days"))
    trace_id = f"procurement-trace-{uuid4().hex[:10]}"
    graph_result = execute_decision_graph(
        scenario="procurement",
        query=query,
        payload=payload,
        constraints={},
    )
    ranked_options = [
        _build_procurement_option_from_graph(
            normalized_option=option,
            budget_max=budget_max,
            require_compliance=require_compliance,
            max_delivery_days=max_delivery_days,
        )
        for option in graph_result.ranked_options
    ]
    recommended = ranked_options[0] if ranked_options else None
    summary = (
        graph_result.explanation
        if recommended is None
        else (
            f"共评估 {len(payload.get('options', []))} 个供应商方案，"
            f"其中 {len(graph_result.accepted_option_ids)} 个通过预算、交付与合规门槛，"
            f"{len(graph_result.pareto_frontier_ids)} 个处于 Pareto 前沿。"
        )
    )
    explanation = graph_result.explanation
    return ProcurementCompareResult(
        status=(
            ProcurementWorkflowStatus.PROPOSAL_READY
            if recommended is not None
            else ProcurementWorkflowStatus.NO_MATCH
        ),
        query=query,
        session_id=session_id,
        intent_slots=ProcurementIntentSlots(
            query=query,
            budget_max=budget_max if budget_max > 0 else None,
            require_compliance=require_compliance,
            max_delivery_days=max_delivery_days,
        ),
        options=ranked_options,
        recommended=recommended,
        accepted_option_ids=graph_result.accepted_option_ids,
        summary=summary,
        explanation=explanation,
        operator_trace=[
            {
                "operator_id": trace.operator_id,
                "operator_version": trace.operator_version,
                "input_schema_version": trace.input_schema_version,
                "output_schema_version": trace.output_schema_version,
                "confidence": trace.confidence,
                "evidence_refs": list(trace.evidence_refs),
                "warnings": list(trace.warnings),
            }
            for trace in graph_result.operator_traces
        ],
        proposal_id=proposal_id,
        audit_trace=_build_procurement_audit_trace_from_graph(
            graph_result=graph_result,
            session_id=session_id,
            proposal_id=proposal_id,
            source_type=source_type,
            trace_id=trace_id,
            summary=summary,
        ),
    ).model_dump(mode="json")


def _run_hotel_biztravel_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    """执行酒店 / 商旅共享决策场景。

    这一层只负责把 payload 归一成共享决策请求，再把结果回给平台层；
    具体的 bundle 可行性过滤和联合排序交给决策内核。
    """

    request = build_bundle_decision_request(payload)
    response: BundleDecisionResponse = evaluate_bundle_decision(request)
    enriched = enrich_hotel_biztravel_response(request=request, response=response)
    return enriched.model_dump(mode="json")


def _build_procurement_option_from_graph(
    *,
    normalized_option: DecisionOptionSchema,
    budget_max: float,
    require_compliance: bool,
    max_delivery_days: int | None,
) -> ProcurementOption:
    """把 decision graph 输出映射回 legacy procurement option 协议。"""

    source = dict(normalized_option.metadata.get("raw_option", {}))
    evidence_refs = _collect_procurement_graph_evidence_refs(normalized_option)
    price_cny = float(source.get("price_cny", 0) or 0)
    delivery_days = float(source.get("delivery_days", 0) or 0)
    quality_score = _clamp_score(float(source.get("quality_score", 0) or 0))
    compliance_score = _clamp_score(float(source.get("compliance_score", 0) or 0))
    risk_score = _clamp_score(float(source.get("risk_score", 0) or 0))
    return ProcurementOption(
        id=normalized_option.option_id,
        label=normalized_option.label,
        vendor=_as_optional_str(source.get("vendor")),
        price_cny=price_cny,
        delivery_days=delivery_days,
        quality_score=quality_score,
        compliance_score=compliance_score,
        risk_score=risk_score,
        total_score=normalized_option.metadata.get("total_score"),
        score_breakdown=dict(normalized_option.metadata.get("score_breakdown", {})),
        reason=_build_procurement_reason(
            price_cny=price_cny,
            budget_max=budget_max,
            delivery_days=delivery_days,
            max_delivery_days=max_delivery_days,
            compliance_score=compliance_score,
            require_compliance=require_compliance,
            risk_score=risk_score,
        ),
        normalized_option=normalized_option,
        metadata={"evidence_refs": evidence_refs},
    )


def _build_procurement_audit_trace_from_graph(
    *,
    graph_result: Any,
    session_id: str,
    proposal_id: str,
    source_type: str,
    trace_id: str,
    summary: str,
) -> ProcurementAuditTrace:
    """把 decision graph trace 映射回 legacy procurement audit 协议。"""

    last_trace = graph_result.operator_traces[-1] if graph_result.operator_traces else None
    return ProcurementAuditTrace(
        trace_id=trace_id,
        source_type=source_type,
        accepted_option_ids=list(graph_result.accepted_option_ids),
        recommended_option_id=graph_result.recommended_option_id,
        proposal_id=proposal_id,
        summary=summary,
        created_at=_now_iso(),
        audit_event=DecisionAuditSchema(
            session_id=session_id,
            decision_id=proposal_id,
            step_name=(
                f"{last_trace.operator_id}.completed"
                if last_trace is not None
                else "decision_graph.completed"
            ),
            operator_id=(
                last_trace.operator_id if last_trace is not None else "decision_graph"
            ),
            operator_version=(
                last_trace.operator_version if last_trace is not None else "v1"
            ),
            input_ref=f"decision://input/{proposal_id}",
            output_ref=f"decision://output/{proposal_id}",
            evidence_refs=(
                list(last_trace.evidence_refs) if last_trace is not None else []
            ),
            confidence=last_trace.confidence if last_trace is not None else 0.0,
            trace_id=trace_id,
            warnings=list(last_trace.warnings) if last_trace is not None else [],
        ),
    )


def _collect_procurement_graph_evidence_refs(
    normalized_option: DecisionOptionSchema,
) -> list[str]:
    """汇总 graph 输出 option 上的证据引用。"""

    evidence_refs: list[str] = []
    for metric in normalized_option.metrics:
        evidence_refs.extend(metric.evidence_refs)
    raw_option = normalized_option.metadata.get("raw_option", {})
    if isinstance(raw_option, dict):
        evidence_refs.extend(str(item) for item in raw_option.get("evidence_refs", []))
    return list(dict.fromkeys(evidence_refs))


def _run_general_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    """通用兜底场景：当无法匹配具体场景时提供基础评分和推荐。

    设计原则：
    - 零假设：不假设输入结构，兼容任意 payload
    - 安全降级：缺少字段时用合理默认值
    - 最小可用：提供排序和推荐，让前端至少有东西可展示
    """
    query = str(payload.get("query", "") or "")
    raw_options = payload.get("options", [])
    weights = dict(_registry.get_weights("general"))

    if not raw_options:
        return {
            "scenario": "general",
            "query": query,
            "recommended": None,
            "alternatives": [],
            "summary": "当前无候选选项，请提供更多选项或约束。",
            "requires_confirmation": False,
        }

    # 通用多维评分：尝试从候选项中提取 scores 子字典
    scored_input: list[dict[str, Any]] = []
    for opt in raw_options:
        dims = opt.get("scores", opt.get("dimensions", {}))
        if not dims and isinstance(opt, dict):
            # 尝试从顶层数值字段推断
            dims = {}
            for key in ("quality", "cost", "speed", "price", "time", "comfort"):
                if key in opt:
                    dims[key] = _clamp_score(float(opt[key]))
        scored_input.append({
            "id": opt.get("id", ""),
            "label": opt.get("label", opt.get("id", "")),
            "scores": {k: _clamp_score(float(v)) for k, v in dims.items()},
        })

    ranked = score_options(scored_input, weights)
    recommended = ranked[0] if ranked else None
    return {
        "scenario": "general",
        "query": query,
        "recommended": recommended,
        "alternatives": ranked[1:3] if len(ranked) > 1 else [],
        "all_ranked": ranked,
        "summary": f"通用场景分析了 {len(ranked)} 个选项。",
        "requires_confirmation": bool(ranked),
    }


def _run_lifegoal_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    """人生目标决策场景。"""
    domain = str(payload.get("domain", "career"))
    raw_options = payload.get("options", [])
    risk_tolerance = str(payload.get("risk_tolerance", "moderate"))
    constraints = payload.get("constraints", [])

    if not raw_options:
        return {
            "scenario": "lifegoal",
            "domain": domain,
            "recommended": None,
            "alternatives": [],
            "summary": "没有提供候选选项, 请描述你面临的选择.",
        }

    # 获取领域权重
    weights = dict(_registry.get_weights("lifegoal"))

    # 风险偏好调整
    if risk_tolerance == "conservative":
        if "stability" in weights:
            weights["stability"] *= 1.3
    elif risk_tolerance == "aggressive":
        if "growth" in weights:
            weights["growth"] *= 1.3

    scored_input: list[dict[str, Any]] = []
    for opt in raw_options:
        dims = opt.get("dimensions", opt.get("scores", {}))
        scored_input.append({
            "id": opt.get("id", ""),
            "label": opt.get("label", opt.get("id", "")),
            "scores": {k: _clamp_score(float(v)) for k, v in dims.items()},
        })

    ranked = score_options(scored_input, weights)
    return {
        "scenario": "lifegoal",
        "domain": domain,
        "risk_tolerance": risk_tolerance,
        "recommended": ranked[0] if ranked else None,
        "alternatives": ranked[1:3] if len(ranked) > 1 else [],
        "all_ranked": ranked,
        "constraints": constraints,
        "summary": f"在 {domain} 领域分析了 {len(ranked)} 个选项.",
    }


def _build_procurement_option(
    *,
    option: dict[str, Any],
    ranked_item: dict[str, Any] | None,
    budget_max: float,
    require_compliance: bool,
    max_delivery_days: int | None,
) -> ProcurementOption:
    """把原始采购候选项标准化为统一协议对象。"""

    option_id = str(option.get("id", ""))
    label = str(option.get("label", option_id))
    vendor = _as_optional_str(option.get("vendor"))
    price_cny = float(option.get("price_cny", 0) or 0)
    delivery_days = float(option.get("delivery_days", 0) or 0)
    quality_score = _clamp_score(float(option.get("quality_score", 0) or 0))
    compliance_score = _clamp_score(float(option.get("compliance_score", 0) or 0))
    risk_score = _clamp_score(float(option.get("risk_score", 0) or 0))
    score_breakdown = dict((ranked_item or {}).get("scores", {}))
    evidence_refs = [str(item) for item in option.get("evidence_refs", [])]
    normalized_option = DecisionOptionSchema(
        option_id=option_id,
        scenario="procurement",
        label=label,
        metrics=_build_procurement_metrics(
            price_cny=price_cny,
            delivery_days=delivery_days,
            quality_score=quality_score,
            compliance_score=compliance_score,
            risk_score=risk_score,
            score_breakdown=score_breakdown,
            evidence_refs=evidence_refs,
        ),
        summary=f"{label} 已标准化为统一采购候选结构。",
        warnings=_build_procurement_warnings(
            price_cny=price_cny,
            budget_max=budget_max,
            delivery_days=delivery_days,
            max_delivery_days=max_delivery_days,
            compliance_score=compliance_score,
            require_compliance=require_compliance,
        ),
        metadata={
            key: value
            for key, value in option.items()
            if key
            not in {
                "id",
                "label",
                "vendor",
                "price_cny",
                "delivery_days",
                "quality_score",
                "compliance_score",
                "risk_score",
                "evidence_refs",
            }
        },
    )
    return ProcurementOption(
        id=option_id,
        label=label,
        vendor=vendor,
        price_cny=price_cny,
        delivery_days=delivery_days,
        quality_score=quality_score,
        compliance_score=compliance_score,
        risk_score=risk_score,
        total_score=(ranked_item or {}).get("total_score"),
        score_breakdown=score_breakdown,
        reason=_build_procurement_reason(
            price_cny=price_cny,
            budget_max=budget_max,
            delivery_days=delivery_days,
            max_delivery_days=max_delivery_days,
            compliance_score=compliance_score,
            require_compliance=require_compliance,
            risk_score=risk_score,
        ),
        normalized_option=normalized_option,
        metadata={"evidence_refs": evidence_refs},
    )


def _looks_like_hotel_biztravel_query(query: str) -> bool:
    """识别是否需要进入酒店 / 商旅共享决策场景。

    这里要避免把普通的 travel 查询误路由到 bundle 场景，
    所以只在明确出现礼宾、鲜花、咖啡、接送、联合决策等组合信号时才命中。
    """

    # 这一组信号只回答“用户是不是在要联合决策 / 组合方案”，
    # 例如 bundle、联合决策、组合、礼宾等；它不负责判断业务域。
    bundle_signals = (
        "鲜花",
        "花束",
        "花店",
        "咖啡",
        "咖啡店",
        "接送",
        "礼宾",
        "餐厅",
        "多店",
        "门店",
        "伴手礼",
        "bundle",
        "组合方案",
        "联合决策",
        "行程套餐",
        "附加服务",
    )
    # 这一组信号只回答“问题是不是落在酒店 / 商旅 / 出行域”，
    # 例如酒店、商旅、差旅、机场、航班等；它不负责判断是否需要 bundle。
    travel_anchor = (
        "酒店",
        "商旅",
        "差旅",
        "出差",
        "机场",
        "送机",
        "接机",
        "候机",
        "航班",
        "行程",
        "旅程",
    )

    if "hotel_biztravel" in query or "bundle_rank" in query:
        return True
    # 两类信号必须同时出现：
    # - bundle_signals 负责发现“需要共享决策”
    # - travel_anchor 负责确认“这是酒店 / 商旅问题”
    # 这样可以减少把普通旅游问句误送进 bundle 路径的概率。
    if any(signal in query for signal in bundle_signals) and any(anchor in query for anchor in travel_anchor):
        return True
    return False


def _build_procurement_metrics(
    *,
    price_cny: float,
    delivery_days: float,
    quality_score: float,
    compliance_score: float,
    risk_score: float,
    score_breakdown: dict[str, float],
    evidence_refs: list[str],
) -> list[DecisionOptionMetric]:
    """构造采购候选项的统一指标输出。"""

    metrics: list[DecisionOptionMetric] = []
    raw_metric_values = {
        "cost": price_cny,
        "quality": quality_score,
        "delivery": delivery_days,
        "compliance": compliance_score,
        "risk": risk_score,
    }
    for metric_id, raw_value in raw_metric_values.items():
        if get_decision_metric(metric_id) is None:
            continue
        metrics.append(
            DecisionOptionMetric(
                metric_id=metric_id,
                raw_value=raw_value,
                normalized_score=_clamp_score(float(score_breakdown.get(metric_id, 0))),
                evidence_refs=list(evidence_refs),
            )
        )
    return metrics


def _build_procurement_reason(
    *,
    price_cny: float,
    budget_max: float,
    delivery_days: float,
    max_delivery_days: int | None,
    compliance_score: float,
    require_compliance: bool,
    risk_score: float,
) -> str:
    """生成单个采购候选项的推荐原因。"""

    clauses = [f"报价 {price_cny:.0f} 元", f"交付 {delivery_days:.0f} 天", f"风险 {risk_score:.2f}"]
    if budget_max > 0:
        clauses.append("预算内" if price_cny <= budget_max else "超预算")
    if max_delivery_days is not None:
        clauses.append("交付达标" if delivery_days <= max_delivery_days else "交付超时")
    if require_compliance:
        clauses.append("合规通过" if compliance_score >= 0.9 else "合规不足")
    else:
        clauses.append(f"合规分 {compliance_score:.2f}")
    return " / ".join(clauses)


def _build_procurement_warnings(
    *,
    price_cny: float,
    budget_max: float,
    delivery_days: float,
    max_delivery_days: int | None,
    compliance_score: float,
    require_compliance: bool,
) -> list[str]:
    """生成采购候选项的标准警告列表。"""

    warnings: list[str] = []
    if budget_max > 0 and price_cny > budget_max:
        warnings.append("报价超出预算上限。")
    if max_delivery_days is not None and delivery_days > max_delivery_days:
        warnings.append("交付周期超过当前要求。")
    if require_compliance and compliance_score < 0.9:
        warnings.append("合规评分低于强制门槛。")
    return warnings


def _build_procurement_explanation(
    *,
    option: ProcurementOption,
    budget_max: float,
    require_compliance: bool,
    max_delivery_days: int | None,
) -> str:
    """生成采购推荐解释。"""

    budget_clause = f"预算上限 {budget_max:.0f} 元" if budget_max > 0 else "当前未设置预算上限"
    delivery_clause = (
        f"交付要求 {max_delivery_days} 天内"
        if max_delivery_days is not None
        else "当前未设置交付上限"
    )
    compliance_clause = "必须满足合规审计" if require_compliance else "合规作为排序维度参与比较"
    return (
        f"推荐 {option.label}：报价 {option.price_cny:.0f} 元，"
        f"交付 {option.delivery_days:.0f} 天，合规分 {option.compliance_score:.2f}，"
        f"风险分 {option.risk_score:.2f}。系统已基于 {budget_clause}、{delivery_clause}、"
        f"{compliance_clause} 完成筛选。"
    )


def _collect_procurement_evidence_refs(option: ProcurementOption) -> list[str]:
    """汇总采购候选项上的证据引用。"""

    evidence_refs: list[str] = []
    for metric in option.normalized_option.metrics:
        evidence_refs.extend(metric.evidence_refs)
    evidence_refs.extend(
        str(item)
        for item in option.metadata.get("evidence_refs", [])
    )
    return list(dict.fromkeys(evidence_refs))


def _inverse_score(value: float, samples: list[float]) -> float:
    if not samples:
        return 0.0
    minimum = min(samples)
    maximum = max(samples)
    if maximum == minimum:
        return 1.0
    return _clamp_score((maximum - value) / (maximum - minimum))


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _build_travel_option(
    option: dict[str, Any],
    ranked_item: dict[str, Any] | None,
    budget_max: float,
    direct_only: bool,
) -> TravelOption:
    """把原始商旅候选项标准化成统一协议对象。"""
    option_id = str(option.get("id", ""))
    price = float(option.get("price", 0) or 0)
    duration_minutes = float(option.get("duration_minutes", 0) or 0)
    direct = bool(option.get("direct", False))
    comfort = _clamp_score(float(option.get("comfort", 0) or 0))
    return TravelOption(
        id=option_id,
        label=str(option.get("label", option_id)),
        price=price,
        duration_minutes=duration_minutes,
        direct=direct,
        comfort=comfort,
        total_score=(ranked_item or {}).get("total_score"),
        score_breakdown=dict((ranked_item or {}).get("scores", {})),
        supplier=_as_optional_str(option.get("supplier")),
        depart_at=_as_optional_str(option.get("depart_at")),
        arrive_at=_as_optional_str(option.get("arrive_at")),
        reason=_build_option_reason(
            price=price,
            duration_minutes=duration_minutes,
            direct=direct,
            comfort=comfort,
            budget_max=budget_max,
            direct_only=direct_only,
        ),
        metadata={
            key: value
            for key, value in option.items()
            if key
            not in {
                "id",
                "label",
                "price",
                "duration_minutes",
                "direct",
                "comfort",
                "supplier",
                "depart_at",
                "arrive_at",
            }
        },
    )


def _build_travel_explanation(
    option: TravelOption,
    budget_max: float,
    direct_only: bool,
    candidate_count: int,
) -> str:
    """生成投资人一眼能看懂的推荐解释。"""
    budget_clause = f"预算 {budget_max:.0f} 内" if budget_max > 0 else "当前预算未设上限"
    direct_clause = "且满足直飞要求" if direct_only else "并兼顾直飞与转机候选"
    return (
        f"推荐 {option.label}：价格 {option.price:.0f}，总耗时 {option.duration_minutes:.0f} 分钟，"
        f"舒适度 {option.comfort:.2f}。系统已从 {candidate_count} 个候选中筛出最优方案，"
        f"{budget_clause}，{direct_clause}。"
    )


def _build_option_reason(
    price: float,
    duration_minutes: float,
    direct: bool,
    comfort: float,
    budget_max: float,
    direct_only: bool,
) -> str:
    """为单个候选项生成简短说明。"""
    clauses = [f"价格 {price:.0f}", f"耗时 {duration_minutes:.0f} 分钟", f"舒适度 {comfort:.2f}"]
    if direct:
        clauses.append("直飞")
    elif direct_only:
        clauses.append("不满足直飞要求")
    if budget_max > 0:
        clauses.append("预算内" if price <= budget_max else "超预算")
    return " / ".join(clauses)


def _extract_budget_from_query(query: str) -> float | None:
    """从自然语言里提取预算上限。

    这样做是为了让前端只传一句话时，也能先完成一个最小可演示闭环。
    """
    if not query:
        return None

    patterns = (
        r"预算\s*([0-9]+(?:\.[0-9]+)?)",
        r"([0-9]+(?:\.[0-9]+)?)\s*(?:元|块|人民币)?以内",
        r"不超过\s*([0-9]+(?:\.[0-9]+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _extract_route_from_query(query: str) -> tuple[str | None, str | None]:
    """从自然语言里抽取出发地和目的地。"""
    if not query:
        return None, None

    named_route = _TRAVEL_QUERY_ROUTE_PATTERN.search(query)
    if named_route:
        return (
            _normalize_location_token(named_route.group("origin")),
            _normalize_location_token(named_route.group("destination")),
        )

    from_to = re.search(r"从\s*([^\s，。,；;]+)\s*(?:飞往|飞去|飞到|到|至)\s*([^\s，。,；;]+)", query)
    if from_to:
        return _normalize_location_token(from_to.group(1)), _normalize_location_token(from_to.group(2))

    fly_to = re.search(r"([^\s，。,；;]+)\s*(?:飞往|飞去|飞到|飞|到|至)\s*([^\s，。,；;]+)", query)
    if fly_to:
        return _normalize_location_token(fly_to.group(1)), _normalize_location_token(fly_to.group(2))

    destination_only = _TRAVEL_QUERY_DESTINATION_PATTERN.search(query)
    if destination_only:
        return None, _normalize_location_token(destination_only.group("destination"))

    return None, None


def _infer_direct_only(query: str) -> bool:
    """从自然语言里推断是否只接受直飞。"""
    if not query:
        return False
    return "直飞" in query or "不转机" in query


def _as_optional_str(value: Any) -> str | None:
    """把输入安全转换成可选字符串。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_optional_int(value: Any) -> int | None:
    """把输入安全转换成可选整数。"""

    if value is None or value == "":
        return None
    return int(value)


def _normalize_location_token(value: str) -> str:
    """清洗从自然语言里截取的地名片段。"""
    cleaned = value.strip()
    if "的" in cleaned:
        cleaned = cleaned.split("的", 1)[0]

    prefixes = (
        "帮我规划一次",
        "帮我规划",
        "规划一次",
        "请帮我规划",
        "帮我安排一次",
        "帮我安排",
        "安排一次",
        "请帮我安排",
        "一次",
        "一趟",
        "一程",
        "去",
        "从",
    )
    prefix_changed = True
    while prefix_changed and cleaned:
        prefix_changed = False
        for prefix in prefixes:
            if cleaned.startswith(prefix) and len(cleaned) > len(prefix):
                cleaned = cleaned[len(prefix):].strip()
                prefix_changed = True

    for suffix in ("出差", "旅行", "机票", "酒店", "商务", "商旅", "开会"):
        if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
            cleaned = cleaned[: -len(suffix)]
    return cleaned


def _extract_option_route(option: dict[str, Any]) -> tuple[str | None, str | None]:
    """从候选项字段或标题中解析路线信息。"""
    nested_sources = [option]
    for key in ("metadata", "meta"):
        nested = option.get(key)
        if isinstance(nested, dict):
            nested_sources.append(nested)

    for source in nested_sources:
        origin = _as_optional_str(source.get("origin"))
        destination = _as_optional_str(source.get("destination"))
        if origin or destination:
            return (
                _normalize_location_token(origin) if origin else None,
                _normalize_location_token(destination) if destination else None,
            )

    label = _as_optional_str(option.get("label"))
    if not label:
        return None, None

    route_match = _TRAVEL_TEXT_ROUTE_PATTERN.search(label)
    if not route_match:
        return None, None
    return (
        _normalize_location_token(route_match.group("origin")),
        _normalize_location_token(route_match.group("destination")),
    )


def _score_travel_option_route(
    *,
    option: dict[str, Any],
    origin: str | None,
    destination: str | None,
) -> int:
    """按 query 路线给候选项打对齐分。"""
    if not origin and not destination:
        return 0

    option_origin, option_destination = _extract_option_route(option)
    score = 0
    if origin and option_origin:
        score += 1 if option_origin == origin else -1
    if destination and option_destination:
        score += 1 if option_destination == destination else -1
    return score


def _prepare_travel_option_for_display(
    *,
    option: dict[str, Any],
    origin: str | None,
    destination: str | None,
    force_route_override: bool,
) -> dict[str, Any]:
    """在只有 demo 默认候选时，用 query 路线修正展示字段。"""
    normalized_option = dict(option)
    if not (force_route_override and origin and destination):
        return normalized_option

    normalized_option["origin"] = origin
    normalized_option["destination"] = destination
    normalized_option["label"] = _replace_route_in_label(
        label=str(normalized_option.get("label", "") or ""),
        origin=origin,
        destination=destination,
    )
    return normalized_option


def _replace_route_in_label(label: str, origin: str, destination: str) -> str:
    """把标题里的路线片段替换成 query 路线。"""
    if not label:
        return f"{origin}-{destination} 出行方案"
    replacement = f"{origin}-{destination}"
    if _TRAVEL_TEXT_ROUTE_PATTERN.search(label):
        return _TRAVEL_TEXT_ROUTE_PATTERN.sub(replacement, label, count=1)
    return f"{replacement} {label}"


def _now_iso() -> str:
    """返回统一的 UTC ISO 时间戳。"""
    return datetime.now(UTC).isoformat()
