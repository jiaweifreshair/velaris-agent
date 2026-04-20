"""酒店 / 商旅共享决策场景的引擎测试。"""

from __future__ import annotations

from openharness.biz.engine import build_capability_plan, infer_scenario, run_scenario


def test_infer_scenario_recognizes_hotel_biztravel_bundle_keywords() -> None:
    """带有礼宾 bundle 信号的酒店/商旅请求应进入共享决策场景。"""

    scenario = infer_scenario(
        "帮我把商旅酒店、咖啡、接送和鲜花排成一个 bundle 推荐。"
    )

    assert scenario == "hotel_biztravel"


def test_build_capability_plan_for_hotel_biztravel_query() -> None:
    """共享决策场景应暴露候选标准化与联合排序能力。"""

    plan = build_capability_plan(
        query="帮我把商旅酒店、咖啡、接送和鲜花排成一个 bundle 推荐。",
        constraints={"budget_max": 360, "requires_audit": True},
    )

    assert plan["scenario"] == "hotel_biztravel"
    assert "candidate_normalize" in plan["capabilities"]
    assert "bundle_planning" in plan["capabilities"]
    assert "joint_ranking" in plan["capabilities"]
    assert plan["governance"]["requires_audit"] is True
    assert plan["decision_weights"]["price"] > 0


def test_run_hotel_biztravel_domain_rank_returns_structured_decision() -> None:
    """共享决策场景的 domain_rank 应返回结构化候选排序结果。"""

    result = run_scenario(
        scenario="hotel_biztravel",
        payload={
            "decision_type": "domain_rank",
            "candidate_set": {
                "domain": "shopping",
                "service_type": "flower",
                "request_context": {
                    "session_id": "session-hotel-domain",
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
            "decision_weights": {
                "price": 0.20,
                "eta": 0.25,
                "detour": 0.20,
                "preference_match": 0.25,
                "experience_value": 0.10,
            },
        },
    )

    assert result["decision_type"] == "domain_rank"
    assert result["selected_candidate_id"] == "flower-1"
    assert [item["candidate_id"] for item in result["ranked_candidates"]] == [
        "flower-1",
        "flower-2",
    ]
    assert result["hard_constraint_report"]["passed"] is True
    assert result["why_selected"]
    assert result["explanation_text"]


def test_run_hotel_biztravel_bundle_rank_returns_structured_decision() -> None:
    """共享决策场景的 bundle_rank 应返回结构化联合排序结果。"""

    result = run_scenario(
        scenario="hotel_biztravel",
        payload={
            "decision_type": "bundle_rank",
            "request_context": {
                "session_id": "session-hotel-bundle",
                "query": "帮我把酒店、咖啡和接送排成一个 bundle",
            },
            "hard_constraints": {
                "budget_max": 360,
                "max_detour_minutes": 15,
            },
            "bundle_candidates": [
                {
                    "bundle_id": "bundle-1",
                    "members": [
                        {
                            "domain": "travel",
                            "candidate_id": "travel-1",
                            "service_type": "hotel",
                        },
                        {
                            "domain": "food",
                            "candidate_id": "coffee-1",
                            "service_type": "coffee",
                        },
                    ],
                    "sequence_steps": ["hotel", "coffee", "airport"],
                    "aggregates": {
                        "total_price": 331,
                        "total_eta_minutes": 42,
                        "detour_minutes": 11,
                        "time_slack_minutes": 28,
                        "preference_match": 0.88,
                        "experience_value": 0.79,
                    },
                    "hard_constraint_report": {
                        "passed": True,
                        "checks": ["不误机", "都在营业时间内"],
                    },
                },
                {
                    "bundle_id": "bundle-2",
                    "members": [
                        {
                            "domain": "travel",
                            "candidate_id": "travel-2",
                            "service_type": "hotel",
                        },
                        {
                            "domain": "food",
                            "candidate_id": "coffee-2",
                            "service_type": "coffee",
                        },
                    ],
                    "sequence_steps": ["coffee", "hotel", "airport"],
                    "aggregates": {
                        "total_price": 305,
                        "total_eta_minutes": 52,
                        "detour_minutes": 14,
                        "time_slack_minutes": 14,
                        "preference_match": 0.66,
                        "experience_value": 0.62,
                    },
                    "hard_constraint_report": {
                        "passed": True,
                        "checks": ["不误机"],
                    },
                },
                {
                    "bundle_id": "bundle-3",
                    "members": [
                        {
                            "domain": "travel",
                            "candidate_id": "travel-3",
                            "service_type": "hotel",
                        },
                        {
                            "domain": "food",
                            "candidate_id": "coffee-3",
                            "service_type": "coffee",
                        },
                    ],
                    "sequence_steps": ["coffee", "airport"],
                    "aggregates": {
                        "total_price": 289,
                        "total_eta_minutes": 39,
                        "detour_minutes": 18,
                        "time_slack_minutes": 7,
                        "preference_match": 0.72,
                        "experience_value": 0.60,
                    },
                    "hard_constraint_report": {
                        "passed": False,
                        "checks": ["绕路超限"],
                    },
                },
            ],
            "decision_weights": {
                "price": 0.20,
                "eta": 0.30,
                "detour": 0.20,
                "preference_match": 0.15,
                "experience_value": 0.15,
            },
        },
    )

    assert result["decision_type"] == "bundle_rank"
    assert result["selected_bundle_id"] == "bundle-1"
    assert [item["bundle_id"] for item in result["ranked_bundles"]] == [
        "bundle-1",
        "bundle-2",
    ]
    assert result["hard_constraint_report"]["passed"] is True
    assert result["hard_constraint_report"]["rejected_bundle_ids"] == ["bundle-3"]
    assert result["why_selected"]
    assert result["tradeoffs"]
    assert result["decision_trace_id"].startswith("hotel-biztravel-")
