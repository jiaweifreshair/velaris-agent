"""酒店 / 商旅共享决策结果丰富化测试。"""

from __future__ import annotations

from velaris_agent.biz.hotel_biztravel_inference import enrich_hotel_biztravel_response
from velaris_agent.decision.contracts import (
    BundleCandidate,
    BundleCandidateAggregates,
    BundleDecisionRequest,
    BundleMemberRef,
    CapabilityCandidate,
    CapabilityCandidateSet,
)
from velaris_agent.decision.shared_decision import evaluate_bundle_decision


def test_enrich_domain_rank_builds_candidate_briefs_and_flower_need() -> None:
    """花店同类排序应输出店铺摘要、花束数量假设和回写提示。"""

    request = BundleDecisionRequest(
        decision_type="domain_rank",
        candidate_set=CapabilityCandidateSet(
            domain="shopping",
            service_type="flower",
            request_context={
                "session_id": "session-flower-demo",
                "query": "送机前买花，想要体面一点。",
            },
            hard_constraints={
                "budget_max": 400,
                "max_detour_minutes": 20,
            },
            candidates=[
                CapabilityCandidate(
                    candidate_id="flower-1",
                    domain="shopping",
                    service_type="flower",
                    title="机场店花束 A",
                    price=299,
                    eta_minutes=18,
                    detour_minutes=6,
                    inventory_status="in_stock",
                    available=True,
                    tags=["送机", "现货"],
                    metadata={
                        "store_name": "机场店",
                        "flower_style": "体面送礼",
                    },
                    domain_features={"style_match": 0.9},
                    score_features={"preference_match": 0.92, "experience_value": 0.84},
                ),
                CapabilityCandidate(
                    candidate_id="flower-2",
                    domain="shopping",
                    service_type="flower",
                    title="社区花店 B",
                    price=269,
                    eta_minutes=24,
                    detour_minutes=14,
                    inventory_status="in_stock",
                    available=True,
                    tags=["预算友好"],
                    metadata={"store_name": "社区花店"},
                    domain_features={"style_match": 0.72},
                    score_features={"preference_match": 0.76, "experience_value": 0.71},
                ),
            ],
        ),
        decision_weights={
            "price": 0.2,
            "eta": 0.25,
            "detour": 0.2,
            "preference_match": 0.25,
            "experience_value": 0.1,
        },
    )

    response = evaluate_bundle_decision(request)
    enriched = enrich_hotel_biztravel_response(request=request, response=response)

    assert enriched.candidate_briefs[0]["store_name"] == "机场店"
    assert enriched.candidate_briefs[0]["selected"] is True
    assert enriched.inferred_user_needs[0]["need_type"] == "flower_quantity"
    assert enriched.inferred_user_needs[0]["value"] == 1
    assert any(item["need_type"] == "occasion" for item in enriched.inferred_user_needs)
    assert enriched.writeback_hints["preference_tool"] == "save_decision"
    assert enriched.writeback_hints["knowledge_policy"] == "explicit-only"


def test_enrich_domain_rank_infers_coffee_type_and_highlights() -> None:
    """咖啡同类排序应推断咖啡类型并保留店铺展示信息。"""

    request = BundleDecisionRequest(
        decision_type="domain_rank",
        candidate_set=CapabilityCandidateSet(
            domain="food",
            service_type="coffee",
            request_context={
                "session_id": "session-coffee-demo",
                "query": "会议前提神，帮我顺路找一家咖啡店。",
            },
            hard_constraints={
                "budget_max": 60,
                "max_detour_minutes": 15,
            },
            candidates=[
                CapabilityCandidate(
                    candidate_id="coffee-1",
                    domain="food",
                    service_type="coffee",
                    title="写字楼咖啡店",
                    price=28,
                    eta_minutes=12,
                    detour_minutes=5,
                    inventory_status="in_stock",
                    available=True,
                    tags=["提神", "顺路"],
                    metadata={
                        "store_name": "写字楼咖啡",
                        "coffee_type": "热美式",
                    },
                    domain_features={"taste_match": 0.8},
                    score_features={"preference_match": 0.89, "experience_value": 0.76},
                ),
                CapabilityCandidate(
                    candidate_id="coffee-2",
                    domain="food",
                    service_type="coffee",
                    title="商场咖啡店",
                    price=32,
                    eta_minutes=18,
                    detour_minutes=10,
                    inventory_status="in_stock",
                    available=True,
                    tags=["拿铁"],
                    metadata={
                        "store_name": "商场咖啡",
                        "coffee_type": "拿铁",
                    },
                    domain_features={"taste_match": 0.73},
                    score_features={"preference_match": 0.74, "experience_value": 0.69},
                ),
            ],
        ),
        decision_weights={
            "price": 0.2,
            "eta": 0.25,
            "detour": 0.2,
            "preference_match": 0.25,
            "experience_value": 0.1,
        },
    )

    response = evaluate_bundle_decision(request)
    enriched = enrich_hotel_biztravel_response(request=request, response=response)

    assert enriched.candidate_briefs[0]["store_name"] == "写字楼咖啡"
    assert "适合赶时间" in enriched.candidate_briefs[0]["highlights"]
    coffee_need = next(item for item in enriched.inferred_user_needs if item["need_type"] == "coffee_type")
    assert coffee_need["value"] == "美式"
    assert coffee_need["needs_confirmation"] is True


def test_enrich_bundle_rank_builds_bundle_briefs_and_aircraft_need() -> None:
    """bundle 排序应输出 bundle 摘要和机型推断。"""

    request = BundleDecisionRequest(
        decision_type="bundle_rank",
        candidate_set=CapabilityCandidateSet(
            domain="travel",
            service_type="hotel",
            request_context={
                "session_id": "session-bundle-demo",
                "query": "帮我把酒店、咖啡和接送排成一个 bundle，记得赶 CA1234 这班 A320。",
            },
            hard_constraints={
                "budget_max": 360,
                "max_detour_minutes": 15,
            },
            candidates=[
                CapabilityCandidate(
                    candidate_id="travel-1",
                    domain="travel",
                    service_type="hotel",
                    title="商务酒店 A",
                    price=231,
                    eta_minutes=18,
                    detour_minutes=4,
                    inventory_status="in_stock",
                    available=True,
                    metadata={"store_name": "商务酒店 A"},
                    domain_features={"comfort": 0.88},
                    score_features={"preference_match": 0.9, "experience_value": 0.84},
                ),
                CapabilityCandidate(
                    candidate_id="coffee-1",
                    domain="food",
                    service_type="coffee",
                    title="写字楼咖啡店",
                    price=28,
                    eta_minutes=12,
                    detour_minutes=5,
                    inventory_status="in_stock",
                    available=True,
                    metadata={"store_name": "写字楼咖啡"},
                    domain_features={"taste_match": 0.8},
                    score_features={"preference_match": 0.89, "experience_value": 0.76},
                ),
                CapabilityCandidate(
                    candidate_id="travel-2",
                    domain="travel",
                    service_type="hotel",
                    title="转机酒店 B",
                    price=180,
                    eta_minutes=26,
                    detour_minutes=8,
                    inventory_status="in_stock",
                    available=True,
                    metadata={"store_name": "转机酒店 B"},
                    domain_features={"comfort": 0.74},
                    score_features={"preference_match": 0.66, "experience_value": 0.62},
                ),
                CapabilityCandidate(
                    candidate_id="coffee-2",
                    domain="food",
                    service_type="coffee",
                    title="商场咖啡店",
                    price=32,
                    eta_minutes=18,
                    detour_minutes=10,
                    inventory_status="in_stock",
                    available=True,
                    metadata={"store_name": "商场咖啡"},
                    domain_features={"taste_match": 0.73},
                    score_features={"preference_match": 0.74, "experience_value": 0.69},
                ),
            ],
        ),
        request_context={
            "session_id": "session-bundle-demo",
            "query": "帮我把酒店、咖啡和接送排成一个 bundle，记得赶 CA1234 这班 A320。",
        },
        hard_constraints={
            "budget_max": 360,
            "max_detour_minutes": 15,
        },
        bundle_candidates=[
            BundleCandidate(
                bundle_id="bundle-1",
                members=[
                    BundleMemberRef(domain="travel", candidate_id="travel-1", service_type="hotel"),
                    BundleMemberRef(domain="food", candidate_id="coffee-1", service_type="coffee"),
                ],
                sequence_steps=["hotel", "coffee", "airport"],
                aggregates=BundleCandidateAggregates(
                    total_price=331,
                    total_eta_minutes=42,
                    detour_minutes=11,
                    time_slack_minutes=28,
                    preference_match=0.88,
                    experience_value=0.79,
                ),
                hard_constraint_report={
                    "passed": True,
                    "checks": ["不误机", "都在营业时间内"],
                },
                metadata={
                    "flight_number": "CA1234",
                    "aircraft_model": "A320",
                },
            ),
            BundleCandidate(
                bundle_id="bundle-2",
                members=[
                    BundleMemberRef(domain="travel", candidate_id="travel-2", service_type="hotel"),
                    BundleMemberRef(domain="food", candidate_id="coffee-2", service_type="coffee"),
                ],
                sequence_steps=["coffee", "hotel", "airport"],
                aggregates=BundleCandidateAggregates(
                    total_price=305,
                    total_eta_minutes=52,
                    detour_minutes=14,
                    time_slack_minutes=14,
                    preference_match=0.66,
                    experience_value=0.62,
                ),
                hard_constraint_report={
                    "passed": True,
                    "checks": ["不误机"],
                },
                metadata={
                    "flight_number": "MU9988",
                    "aircraft_model": "B787",
                },
            ),
        ],
        decision_weights={
            "price": 0.2,
            "eta": 0.3,
            "detour": 0.2,
            "preference_match": 0.15,
            "experience_value": 0.15,
        },
    )

    response = evaluate_bundle_decision(request)
    enriched = enrich_hotel_biztravel_response(request=request, response=response)

    assert enriched.bundle_briefs[0]["bundle_id"] == "bundle-1"
    assert enriched.bundle_briefs[0]["selected"] is True
    assert enriched.bundle_briefs[0]["aggregates"]["time_slack_minutes"] == 28
    assert enriched.bundle_briefs[0]["members"][0]["store_name"] == "商务酒店 A"
    aircraft_need = next(item for item in enriched.inferred_user_needs if item["need_type"] == "aircraft_model")
    assert aircraft_need["value"] == "A320"
    assert aircraft_need["needs_confirmation"] is False
    assert enriched.writeback_hints["preference_tool"] == "save_decision"
