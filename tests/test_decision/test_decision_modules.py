"""共享决策内核拆分后的模块测试。"""

from __future__ import annotations

from velaris_agent.decision.basis import DecisionBasisBuilder
from velaris_agent.decision.bundle_planner import BundlePlanner
from velaris_agent.decision.contracts import (
    BundleCandidate,
    BundleCandidateAggregates,
    BundleDecisionRequest,
    BundleMemberRef,
    CapabilityCandidate,
    RankedBundle,
    RankedCandidate,
)
from velaris_agent.decision.feasibility import FeasibilityChecker


def test_feasibility_checker_filters_candidates_and_bundles() -> None:
    """可行性检查器应独立过滤同类候选与 bundle 候选。"""

    checker = FeasibilityChecker()

    feasible_candidates = [
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
        ),
        CapabilityCandidate(
            id="flower-2",
            domain="shopping",
            service_type="flower",
            title="已售罄花店",
            price=269,
            eta_minutes=24,
            detour_minutes=14,
            inventory_status="sold_out",
            available=False,
        ),
    ]
    selected_candidates, rejected_candidates = checker.filter_candidates(
        feasible_candidates,
        {"budget_max": 400, "max_detour_minutes": 20},
    )

    assert [item.candidate_id for item in selected_candidates] == ["flower-1"]
    assert "flower-2" in rejected_candidates
    assert "inventory_unavailable" in rejected_candidates["flower-2"]

    feasible_bundles = [
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
            ),
            hard_constraint_report={"passed": True, "checks": ["不误机"]},
        ),
        BundleCandidate(
            bundle_id="bundle-2",
            members=[
                BundleMemberRef(domain="travel", candidate_id="travel-2", service_type="hotel"),
                BundleMemberRef(domain="food", candidate_id="coffee-2", service_type="coffee"),
            ],
            sequence_steps=["coffee", "hotel", "airport"],
            aggregates=BundleCandidateAggregates(
                total_price=289,
                total_eta_minutes=39,
                detour_minutes=18,
                time_slack_minutes=7,
            ),
            hard_constraint_report={"passed": False, "checks": ["绕路超限"]},
        ),
    ]
    selected_bundles, rejected_bundles = checker.filter_bundles(
        feasible_bundles,
        {"budget_max": 360, "max_detour_minutes": 15},
    )

    assert [item.bundle_id for item in selected_bundles] == ["bundle-1"]
    assert "bundle-2" in rejected_bundles
    assert "detour_exceeded" in rejected_bundles["bundle-2"]


def test_decision_basis_builder_builds_candidate_and_bundle_basis() -> None:
    """决策依据构建器应把排序结果翻译成结构化解释。"""

    builder = DecisionBasisBuilder()

    candidate_basis = builder.build_candidate_basis(
        ranked_candidates=[
            RankedCandidate(
                candidate_id="flower-1",
                label="机场店花束 A",
                score=0.86,
                score_breakdown={
                    "price": 0.72,
                    "eta": 0.88,
                    "detour_cost": 0.94,
                    "preference_match": 0.91,
                    "experience_value": 0.84,
                },
                hard_constraint_report={"passed": True, "checks": ["预算满足"]},
                reason="价格 0.72，ETA 0.88，绕路 0.94，偏好 0.91",
            ),
            RankedCandidate(
                candidate_id="flower-2",
                label="社区花店 B",
                score=0.71,
                score_breakdown={
                    "price": 0.94,
                    "eta": 0.62,
                    "detour_cost": 0.51,
                    "preference_match": 0.76,
                    "experience_value": 0.71,
                },
                hard_constraint_report={"passed": True, "checks": ["预算满足"]},
                reason="价格 0.94，ETA 0.62，绕路 0.51，偏好 0.76",
            ),
        ],
        rejected_reasons={"flower-3": ["inventory_unavailable"]},
        hard_constraints={"budget_max": 400, "max_detour_minutes": 20},
    )

    assert candidate_basis["why_selected"]
    assert candidate_basis["why_not_others"]
    assert candidate_basis["tradeoffs"]
    assert "机场店花束 A" in candidate_basis["explanation_text"]

    bundle_basis = builder.build_bundle_basis(
        ranked_bundles=[
            RankedBundle(
                bundle_id="bundle-1",
                score=0.83,
                score_breakdown={
                    "price": 0.75,
                    "eta": 0.84,
                    "detour_cost": 0.86,
                    "preference_match": 0.88,
                    "experience_value": 0.79,
                },
                hard_constraint_report={"passed": True, "checks": ["不误机"]},
                reason="总价 0.75，总 ETA 0.84，绕路 0.86，体验 0.79",
            ),
            RankedBundle(
                bundle_id="bundle-2",
                score=0.61,
                score_breakdown={
                    "price": 0.88,
                    "eta": 0.60,
                    "detour_cost": 0.51,
                    "preference_match": 0.66,
                    "experience_value": 0.62,
                },
                hard_constraint_report={"passed": True, "checks": ["不误机"]},
                reason="总价 0.88，总 ETA 0.60，绕路 0.51，体验 0.62",
            ),
        ],
        rejected_reasons={"bundle-3": ["绕路超限"]},
        hard_constraints={"budget_max": 360, "max_detour_minutes": 15},
    )

    assert bundle_basis["why_selected"]
    assert bundle_basis["why_not_others"]
    assert bundle_basis["tradeoffs"]
    assert "bundle-1" in bundle_basis["explanation_text"]


def test_bundle_planner_evaluates_domain_rank_using_split_modules() -> None:
    """BundlePlanner 应把拆分后的模块重新编排成原有的决策结果。"""

    planner = BundlePlanner()
    request = BundleDecisionRequest(
        decision_type="domain_rank",
        candidate_set={
            "domain": "shopping",
            "service_type": "flower",
            "request_context": {
                "session_id": "session-module-planner",
                "query": "送机前买花",
            },
            "hard_constraints": {
                "budget_max": 400,
                "max_detour_minutes": 20,
            },
            "candidates": [
                {
                    "id": "flower-1",
                    "domain": "shopping",
                    "service_type": "flower",
                    "title": "机场店花束 A",
                    "price": 299,
                    "eta_minutes": 18,
                    "detour_minutes": 6,
                    "inventory_status": "in_stock",
                    "available": True,
                    "domain_features": {"style_match": 0.90},
                    "score_features": {
                        "preference_match": 0.92,
                        "experience_value": 0.84,
                    },
                },
                {
                    "id": "flower-2",
                    "domain": "shopping",
                    "service_type": "flower",
                    "title": "社区花店 B",
                    "price": 269,
                    "eta_minutes": 24,
                    "detour_minutes": 14,
                    "inventory_status": "in_stock",
                    "available": True,
                    "domain_features": {"style_match": 0.72},
                    "score_features": {
                        "preference_match": 0.76,
                        "experience_value": 0.71,
                    },
                },
            ],
        },
        decision_weights={
            "price": 0.20,
            "eta": 0.25,
            "detour": 0.20,
            "preference_match": 0.25,
            "experience_value": 0.10,
        },
    )

    result = planner.evaluate(request)

    assert result.decision_type == "domain_rank"
    assert result.selected_candidate_id == "flower-1"
    assert [item.candidate_id for item in result.ranked_candidates] == [
        "flower-1",
        "flower-2",
    ]
    assert result.hard_constraint_report["passed"] is True
    assert result.why_selected
    assert result.explanation_text
