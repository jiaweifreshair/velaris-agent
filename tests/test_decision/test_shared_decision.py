"""共享决策内核的 bundle/domain 排序测试。"""

from __future__ import annotations

from velaris_agent.decision.shared_decision import (
    BundleCandidate,
    BundleCandidateAggregates,
    BundleDecisionRequest,
    BundleMemberRef,
    CapabilityCandidate,
    CapabilityCandidateSet,
    evaluate_bundle_decision,
)


def test_domain_rank_filters_and_ranks_candidates() -> None:
    """同类候选应先过硬约束，再按共享权重稳定排序。"""

    request = BundleDecisionRequest(
        decision_type="domain_rank",
        candidate_set=CapabilityCandidateSet(
            domain="shopping",
            service_type="flower",
            request_context={
                "session_id": "session-domain-rank",
                "query": "送机前买花",
            },
            hard_constraints={
                "budget_max": 400,
                "max_detour_minutes": 20,
            },
            candidates=[
                CapabilityCandidate(
                    id="flower-1",
                    domain="shopping",
                    service_type="flower",
                    title="机场店花束 A",
                    price=299,
                    eta_minutes=18,
                    detour_minutes=6,
                    inventory_status="in_stock",
                    available=True,
                    tags=["送机", "现货"],
                    domain_features={"style_match": 0.90},
                    score_features={"preference_match": 0.92, "experience_value": 0.84},
                    evidence_refs=["flower://a"],
                ),
                CapabilityCandidate(
                    id="flower-2",
                    domain="shopping",
                    service_type="flower",
                    title="社区花店 B",
                    price=269,
                    eta_minutes=24,
                    detour_minutes=14,
                    inventory_status="in_stock",
                    available=True,
                    tags=["预算友好"],
                    domain_features={"style_match": 0.72},
                    score_features={"preference_match": 0.76, "experience_value": 0.71},
                    evidence_refs=["flower://b"],
                ),
                CapabilityCandidate(
                    id="flower-3",
                    domain="shopping",
                    service_type="flower",
                    title="已售罄花店 C",
                    price=310,
                    eta_minutes=16,
                    detour_minutes=8,
                    inventory_status="sold_out",
                    available=False,
                    tags=["售罄"],
                    domain_features={"style_match": 0.80},
                    score_features={"preference_match": 0.80, "experience_value": 0.73},
                    evidence_refs=["flower://c"],
                ),
            ],
        ),
        decision_weights={
            "price": 0.20,
            "eta": 0.25,
            "detour": 0.20,
            "preference_match": 0.25,
            "experience_value": 0.10,
        },
    )

    result = evaluate_bundle_decision(request)

    assert result.decision_type == "domain_rank"
    assert result.selected_candidate_id == "flower-1"
    assert [item.candidate_id for item in result.ranked_candidates] == [
        "flower-1",
        "flower-2",
    ]
    assert result.hard_constraint_report["passed"] is True
    assert result.hard_constraint_report["rejected_candidate_ids"] == ["flower-3"]
    assert result.score_breakdown["preference_match"] >= result.score_breakdown["price"]
    assert any(item["candidate_id"] == "flower-3" for item in result.why_not_others)
    assert "顺路" in result.explanation_text or "偏好" in result.explanation_text


def test_bundle_rank_filters_bundle_candidates_and_returns_tradeoffs() -> None:
    """bundle_rank 应先过滤不可行 bundle，再输出可审计的联合排序结果。"""

    request = BundleDecisionRequest(
        decision_type="bundle_rank",
        request_context={
            "session_id": "session-bundle-rank",
            "query": "帮我把酒店、咖啡和接送排成一个 bundle",
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
                    BundleMemberRef(domain="travel", candidate_id="ride-1", service_type="transfer"),
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
                evidence_refs=["bundle://1"],
            ),
            BundleCandidate(
                bundle_id="bundle-2",
                members=[
                    BundleMemberRef(domain="travel", candidate_id="travel-2", service_type="hotel"),
                    BundleMemberRef(domain="food", candidate_id="coffee-2", service_type="coffee"),
                    BundleMemberRef(domain="travel", candidate_id="ride-2", service_type="transfer"),
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
                evidence_refs=["bundle://2"],
            ),
            BundleCandidate(
                bundle_id="bundle-3",
                members=[
                    BundleMemberRef(domain="travel", candidate_id="travel-3", service_type="hotel"),
                    BundleMemberRef(domain="food", candidate_id="coffee-3", service_type="coffee"),
                ],
                sequence_steps=["coffee", "airport"],
                aggregates=BundleCandidateAggregates(
                    total_price=289,
                    total_eta_minutes=39,
                    detour_minutes=18,
                    time_slack_minutes=7,
                    preference_match=0.72,
                    experience_value=0.60,
                ),
                hard_constraint_report={
                    "passed": False,
                    "checks": ["绕路超限"],
                },
                evidence_refs=["bundle://3"],
            ),
        ],
        decision_weights={
            "price": 0.20,
            "eta": 0.30,
            "detour": 0.20,
            "preference_match": 0.15,
            "experience_value": 0.15,
        },
    )

    result = evaluate_bundle_decision(request)

    assert result.decision_type == "bundle_rank"
    assert result.selected_bundle_id == "bundle-1"
    assert [item.bundle_id for item in result.ranked_bundles] == [
        "bundle-1",
        "bundle-2",
    ]
    assert result.hard_constraint_report["passed"] is True
    assert result.hard_constraint_report["rejected_bundle_ids"] == ["bundle-3"]
    assert result.score_breakdown["eta"] >= result.score_breakdown["price"]
    assert any(item["bundle_id"] == "bundle-3" for item in result.why_not_others)
    assert any("时间余量" in tradeoff or "绕路" in tradeoff for tradeoff in result.tradeoffs)
    assert result.decision_trace_id.startswith("hotel-biztravel-")
