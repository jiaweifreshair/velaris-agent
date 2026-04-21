"""酒店 / 商旅共享决策结果丰富化助手。

这一层只做三件事：
1. 把排序结果整理成更适合前端展示的候选摘要。
2. 基于 query 和候选元数据推断低置信度需求假设。
3. 明确偏好回写只走决策记忆，不把隐式推断写进知识库。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from velaris_agent.decision.contracts import (
    BundleCandidate,
    BundleDecisionRequest,
    BundleDecisionResponse,
    CapabilityCandidate,
)

_CHINESE_NUMERAL_TO_INT: dict[str, int] = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

_AIRCRAFT_MODEL_RE = re.compile(
    r"\b(?:A\d{3}|B\d{3}|737|747|757|767|777|787|CRJ\d+|E\d{3})\b",
    flags=re.IGNORECASE,
)
_FLOWER_QUANTITY_RE = re.compile(r"(?P<count>\d+|[一二两三四五六七八九十])(?:束|支|盒|份|朵)?")
_COFFEE_MODEL_KEYS = (
    "coffee_type",
    "drink_type",
    "beverage_type",
    "product_type",
    "style",
)
_AIRCRAFT_KEYS = (
    "aircraft_model",
    "plane_model",
    "flight_model",
    "aircraftType",
    "aircraft_type",
)


def enrich_hotel_biztravel_response(
    *,
    request: BundleDecisionRequest,
    response: BundleDecisionResponse,
) -> BundleDecisionResponse:
    """把共享决策结果补成平台更容易展示和回写的结构。"""

    query = _extract_query(request)
    if response.decision_type == "domain_rank":
        candidate_briefs = _build_candidate_briefs(request=request, response=response, query=query)
        bundle_briefs: list[dict[str, Any]] = []
    else:
        candidate_briefs = []
        bundle_briefs = _build_bundle_briefs(request=request, response=response, query=query)

    inferred_user_needs = _infer_user_needs(
        request=request,
        response=response,
        query=query,
    )
    writeback_hints = _build_writeback_hints(response=response)
    return response.model_copy(
        update={
            "candidate_briefs": candidate_briefs,
            "bundle_briefs": bundle_briefs,
            "inferred_user_needs": inferred_user_needs,
            "writeback_hints": writeback_hints,
        }
    )


def _extract_query(request: BundleDecisionRequest) -> str:
    """从请求上下文中提取 query。"""

    candidate_context = request.candidate_set.request_context if request.candidate_set else {}
    for context in (request.request_context, candidate_context):
        query = context.get("query")
        if isinstance(query, str) and query.strip():
            return query.strip()
    return ""


def _build_candidate_briefs(
    *,
    request: BundleDecisionRequest,
    response: BundleDecisionResponse,
    query: str,
) -> list[dict[str, Any]]:
    """把同类候选整理成可直接展示给用户的摘要。"""

    candidate_map = _build_candidate_map(request.candidate_set.candidates if request.candidate_set else [])
    candidate_set = request.candidate_set
    domain = candidate_set.domain if candidate_set is not None else ""
    service_type = candidate_set.service_type if candidate_set is not None else ""

    briefs: list[dict[str, Any]] = []
    for ranked_candidate in response.ranked_candidates:
        source = candidate_map.get(ranked_candidate.candidate_id)
        highlights = _candidate_highlights(source, query=query)
        briefs.append(
            {
                "candidate_id": ranked_candidate.candidate_id,
                "store_name": _candidate_store_name(source, ranked_candidate.label),
                "label": ranked_candidate.label,
                "domain": source.domain if source is not None else domain,
                "service_type": source.service_type if source is not None else service_type,
                "price": source.price if source is not None else None,
                "eta_minutes": source.eta_minutes if source is not None else None,
                "detour_minutes": source.detour_minutes if source is not None else None,
                "inventory_status": source.inventory_status if source is not None else None,
                "available": source.available if source is not None else None,
                "tags": list(source.tags) if source is not None else [],
                "highlights": highlights,
                "metadata": dict(source.metadata) if source is not None else {},
                "evidence_refs": list(source.evidence_refs) if source is not None else [],
                "score": ranked_candidate.score,
                "score_breakdown": dict(ranked_candidate.score_breakdown),
                "selected": ranked_candidate.candidate_id == response.selected_candidate_id,
            }
        )
    return briefs


def _build_bundle_briefs(
    *,
    request: BundleDecisionRequest,
    response: BundleDecisionResponse,
    query: str,
) -> list[dict[str, Any]]:
    """把 bundle 候选整理成可直接展示给用户的摘要。"""

    bundle_map = _build_bundle_map(request.bundle_candidates)
    candidate_map = _build_candidate_map(request.candidate_set.candidates if request.candidate_set else [])

    briefs: list[dict[str, Any]] = []
    for ranked_bundle in response.ranked_bundles:
        source = bundle_map.get(ranked_bundle.bundle_id)
        members = _bundle_member_briefs(source, candidate_map=candidate_map)
        aggregates = source.aggregates.model_dump(mode="json") if source is not None else {}
        briefs.append(
            {
                "bundle_id": ranked_bundle.bundle_id,
                "members": members,
                "sequence_steps": list(source.sequence_steps) if source is not None else [],
                "aggregates": aggregates,
                "hard_constraint_report": dict(source.hard_constraint_report) if source is not None else {},
                "metadata": dict(source.metadata) if source is not None else {},
                "evidence_refs": list(source.evidence_refs) if source is not None else [],
                "score": ranked_bundle.score,
                "score_breakdown": dict(ranked_bundle.score_breakdown),
                "highlights": _bundle_highlights(source, query=query, members=members),
                "selected": ranked_bundle.bundle_id == response.selected_bundle_id,
            }
        )
    return briefs


def _infer_user_needs(
    *,
    request: BundleDecisionRequest,
    response: BundleDecisionResponse,
    query: str,
) -> list[dict[str, Any]]:
    """基于 query 与候选特征，生成低置信度需求假设。"""

    needs: list[dict[str, Any]] = []
    service_types = _collect_service_types(request)
    candidate_map = _build_candidate_map(request.candidate_set.candidates if request.candidate_set else [])

    if "flower" in service_types or "花" in query or "花束" in query:
        quantity = _infer_flower_quantity(query)
        _append_need(
            needs,
            need_type="flower_quantity",
            value=quantity,
            unit="bouquet",
            confidence=0.86 if _flower_quantity_is_explicit(query) else 0.46,
            source="query_explicit" if _flower_quantity_is_explicit(query) else "query_default",
            needs_confirmation=not _flower_quantity_is_explicit(query),
        )
        occasion = _infer_occasion(query)
        if occasion is not None:
            _append_need(
                needs,
                need_type="occasion",
                value=occasion,
                confidence=0.63,
                source="query_keywords",
                needs_confirmation=True,
            )
        style = _infer_flower_style(query, candidate_map.values())
        if style is not None:
            _append_need(
                needs,
                need_type="flower_style",
                value=style,
                confidence=0.67 if style else 0.0,
                source="candidate_metadata_or_query",
                needs_confirmation=True,
            )

    if "coffee" in service_types or "咖啡" in query:
        coffee_type = _infer_coffee_type(query, candidate_map.values())
        if coffee_type is not None:
            _append_need(
                needs,
                need_type="coffee_type",
                value=coffee_type,
                confidence=0.79 if coffee_type in {"美式", "热美式", "拿铁", "冰美式"} else 0.65,
                source="query_keywords" if _explicit_coffee_type(query) else "candidate_metadata_or_context",
                needs_confirmation=not _explicit_coffee_type(query),
            )
        sweetness = _infer_coffee_sweetness(query)
        if sweetness is not None:
            _append_need(
                needs,
                need_type="coffee_sweetness",
                value=sweetness,
                confidence=0.68,
                source="query_keywords",
                needs_confirmation=True,
            )

    aircraft_model = _infer_aircraft_model(query, request.bundle_candidates, candidate_map.values())
    if aircraft_model is not None:
        _append_need(
            needs,
            need_type="aircraft_model",
            value=aircraft_model,
            confidence=0.94 if _aircraft_model_from_metadata(request.bundle_candidates, candidate_map.values()) else 0.74,
            source="candidate_metadata" if _aircraft_model_from_metadata(request.bundle_candidates, candidate_map.values()) else "query_or_label",
            needs_confirmation=False,
        )

    if any(token in query for token in ("赶时间", "误机", "起飞前", "尽快", "马上")):
        _append_need(
            needs,
            need_type="time_sensitivity",
            value="high",
            confidence=0.72,
            source="query_keywords",
            needs_confirmation=True,
        )

    return needs


def _build_writeback_hints(*, response: BundleDecisionResponse) -> dict[str, Any]:
    """告诉上游：这次结果应该怎么写回偏好记忆。"""

    selected_field = "selected_bundle_id" if response.decision_type == "bundle_rank" else "selected_candidate_id"
    ranked_field = "bundle_briefs" if response.decision_type == "bundle_rank" else "candidate_briefs"
    return {
        "preference_tool": "save_decision",
        "preference_store": "DecisionMemory",
        "preference_learner": "PreferenceLearner",
        "next_recall_tool": "recall_preferences",
        "capture_trigger": "user_choice_confirmed",
        "capture_fields": [
            selected_field,
            ranked_field,
            "inferred_user_needs",
            "score_breakdown",
            "why_selected",
            "why_not_others",
            "tradeoffs",
        ],
        "knowledge_policy": "explicit-only",
        "knowledge_note": "隐式推断只用于推荐和偏好回写，不直接写入知识库。",
    }


def _build_candidate_map(candidates: Iterable[CapabilityCandidate]) -> dict[str, CapabilityCandidate]:
    """把候选项转换成按 ID 快速检索的映射。"""

    return {candidate.candidate_id: candidate for candidate in candidates}


def _build_bundle_map(bundles: Iterable[BundleCandidate]) -> dict[str, BundleCandidate]:
    """把 bundle 转换成按 ID 快速检索的映射。"""

    return {bundle.bundle_id: bundle for bundle in bundles}


def _candidate_store_name(candidate: CapabilityCandidate | None, fallback: str) -> str:
    """提取候选店铺名称。"""

    if candidate is None:
        return fallback
    store_name = candidate.metadata.get("store_name")
    if isinstance(store_name, str) and store_name.strip():
        return store_name.strip()
    return candidate.title.strip() or fallback


def _candidate_highlights(candidate: CapabilityCandidate | None, *, query: str) -> list[str]:
    """从候选元数据里提取简短展示点。"""

    if candidate is None:
        return []

    highlights: list[str] = []
    for tag in candidate.tags[:3]:
        if tag:
            highlights.append(str(tag))

    for key in ("store_name", "aircraft_model", "coffee_type", "flower_style", "style"):
        value = candidate.metadata.get(key)
        if isinstance(value, str) and value.strip():
            highlights.append(value.strip())

    if candidate.service_type == "coffee" and any(term in query for term in ("提神", "会议前", "赶时间")):
        highlights.append("适合赶时间")
    if candidate.service_type == "flower" and any(term in query for term in ("送礼", "送机", "接机")):
        highlights.append("适合送礼 / 接机")

    return list(dict.fromkeys(highlights))


def _bundle_member_briefs(
    bundle: BundleCandidate | None,
    *,
    candidate_map: dict[str, CapabilityCandidate],
) -> list[dict[str, Any]]:
    """把 bundle 的成员整理成更短的展示摘要。"""

    if bundle is None:
        return []

    briefs: list[dict[str, Any]] = []
    for member in bundle.members:
        candidate = candidate_map.get(member.candidate_id)
        briefs.append(
            {
                "domain": member.domain,
                "candidate_id": member.candidate_id,
                "service_type": member.service_type,
                "store_name": _candidate_store_name(candidate, member.candidate_id),
                "label": candidate.title if candidate is not None else member.candidate_id,
                "metadata": dict(candidate.metadata) if candidate is not None else {},
            }
        )
    return briefs


def _bundle_highlights(
    bundle: BundleCandidate | None,
    *,
    query: str,
    members: list[dict[str, Any]],
) -> list[str]:
    """把 bundle 的核心卖点压缩成短句。"""

    if bundle is None:
        return []

    highlights: list[str] = []
    aggregate = bundle.aggregates
    if aggregate.total_price is not None:
        highlights.append(f"总价 {aggregate.total_price:.0f}")
    if aggregate.time_slack_minutes is not None:
        highlights.append(f"时间余量 {aggregate.time_slack_minutes:.0f} 分钟")
    if aggregate.detour_minutes is not None:
        highlights.append(f"绕路 {aggregate.detour_minutes:.0f} 分钟")
    if any(term in query for term in ("起飞前", "赶时间", "误机")):
        highlights.append("更适合紧凑行程")
    if members:
        highlights.append(f"{len(members)} 个成员")
    return list(dict.fromkeys(highlights))


def _collect_service_types(request: BundleDecisionRequest) -> set[str]:
    """收集本次请求涉及的服务类型。"""

    service_types: set[str] = set()
    if request.candidate_set is not None:
        service_types.add(request.candidate_set.service_type)
        for candidate in request.candidate_set.candidates:
            service_types.add(candidate.service_type)
    for bundle in request.bundle_candidates:
        for member in bundle.members:
            service_types.add(member.service_type)
    return {item for item in service_types if item}


def _infer_flower_quantity(query: str) -> int:
    """推断花束数量，默认按 1 束处理。"""

    match = _FLOWER_QUANTITY_RE.search(query)
    if match is not None:
        return _coerce_count(match.group("count"))
    if any(term in query for term in ("送礼", "送机", "接机", "探望", "表白")):
        return 1
    return 1


def _flower_quantity_is_explicit(query: str) -> bool:
    """判断花束数量是不是被用户明确说出来了。"""

    return _FLOWER_QUANTITY_RE.search(query) is not None


def _infer_occasion(query: str) -> str | None:
    """从 query 中推断花礼或礼宾场景。"""

    if "送机" in query or "接机" in query:
        return "送机/接机"
    if "送礼" in query or "礼物" in query:
        return "送礼"
    if "探望" in query:
        return "探望"
    if "表白" in query:
        return "表白"
    return None


def _infer_flower_style(query: str, candidates: Iterable[CapabilityCandidate]) -> str | None:
    """推断花束风格，优先取候选元数据里的明确值。"""

    for candidate in candidates:
        for key in ("flower_style", "style", "bouquet_style", "theme"):
            value = candidate.metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if "体面" in query or "商务" in query:
        return "体面送礼"
    if "浪漫" in query or "表白" in query:
        return "浪漫"
    return None


def _infer_coffee_type(query: str, candidates: Iterable[CapabilityCandidate]) -> str | None:
    """推断咖啡类型。"""

    explicit = _explicit_coffee_type(query)
    if explicit is not None:
        return explicit

    if any(term in query for term in ("提神", "会议前", "赶时间", "熬夜")):
        return "美式"
    if "热" in query and "冰" not in query:
        return "热咖啡"
    if "冰" in query:
        return "冰咖啡"

    for candidate in candidates:
        for key in _COFFEE_MODEL_KEYS:
            value = candidate.metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _explicit_coffee_type(query: str) -> str | None:
    """从 query 中直接提取明确的咖啡类型。"""

    for keyword in ("美式", "拿铁", "摩卡", "卡布奇诺", "latte", "americano", "cappuccino"):
        if keyword.lower() in query.lower():
            return keyword if keyword.isascii() else keyword
    return None


def _infer_coffee_sweetness(query: str) -> str | None:
    """推断咖啡甜度偏好。"""

    if "无糖" in query or "不甜" in query:
        return "无糖"
    if "少糖" in query or "半糖" in query:
        return "少糖"
    return None


def _infer_aircraft_model(
    query: str,
    bundle_candidates: Iterable[BundleCandidate],
    candidates: Iterable[CapabilityCandidate],
) -> str | None:
    """推断航班机型，优先使用元数据中的明确值。"""

    for bundle in bundle_candidates:
        model = _metadata_aircraft_model(bundle.metadata)
        if model is not None:
            return model
        model = _regex_aircraft_model(bundle.bundle_id)
        if model is not None:
            return model

    for candidate in candidates:
        model = _metadata_aircraft_model(candidate.metadata)
        if model is not None:
            return model
        model = _regex_aircraft_model(candidate.title)
        if model is not None:
            return model

    return _regex_aircraft_model(query)


def _aircraft_model_from_metadata(
    bundle_candidates: Iterable[BundleCandidate],
    candidates: Iterable[CapabilityCandidate],
) -> bool:
    """判断机型是否来自候选元数据。"""

    for bundle in bundle_candidates:
        if _metadata_aircraft_model(bundle.metadata) is not None:
            return True
    for candidate in candidates:
        if _metadata_aircraft_model(candidate.metadata) is not None:
            return True
    return False


def _metadata_aircraft_model(metadata: dict[str, Any]) -> str | None:
    """从元数据里读取机型。"""

    for key in _AIRCRAFT_KEYS:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _regex_aircraft_model(text: str) -> str | None:
    """从文本中抓取常见机型。"""

    match = _AIRCRAFT_MODEL_RE.search(text)
    if match is None:
        return None
    return match.group(0).upper()


def _append_need(
    needs: list[dict[str, Any]],
    *,
    need_type: str,
    value: Any,
    confidence: float,
    source: str,
    needs_confirmation: bool,
    unit: str | None = None,
) -> None:
    """把单条需求假设写入结果，并避免重复。"""

    for existing in needs:
        if existing.get("need_type") == need_type:
            return

    item: dict[str, Any] = {
        "need_type": need_type,
        "value": value,
        "confidence": round(confidence, 2),
        "source": source,
        "needs_confirmation": needs_confirmation,
    }
    if unit is not None:
        item["unit"] = unit
    needs.append(item)


def _coerce_count(value: str) -> int:
    """把中文数字或阿拉伯数字统一转成整数。"""

    if value.isdigit():
        return int(value)
    return _CHINESE_NUMERAL_TO_INT.get(value, 1)
