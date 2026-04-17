"""Tests for Velaris business capability engine."""

from __future__ import annotations

from openharness.biz.engine import build_capability_plan, run_scenario, score_options


def test_build_capability_plan_for_travel_query():
    plan = build_capability_plan(
        query="下周去上海出差，帮我做机票酒店组合推荐，预算 3000",
        constraints={"budget_max": 3000, "direct_only": True},
    )

    assert plan["scenario"] == "travel"
    assert "intent_parse" in plan["capabilities"]
    assert plan["governance"]["requires_audit"] is False
    assert plan["decision_weights"]["price"] > 0


def test_score_options_returns_ranked_results():
    ranked = score_options(
        options=[
            {
                "id": "balanced",
                "label": "Balanced",
                "scores": {"quality": 0.8, "cost": 0.7, "speed": 0.6},
            },
            {
                "id": "cheap",
                "label": "Cheap",
                "scores": {"quality": 0.5, "cost": 0.95, "speed": 0.7},
            },
        ],
        weights={"quality": 0.35, "cost": 0.5, "speed": 0.15},
    )

    assert ranked[0]["id"] == "cheap"
    assert ranked[0]["total_score"] >= ranked[1]["total_score"]


def test_run_travel_scenario_returns_confirmable_protocol():
    result = run_scenario(
        scenario="travel",
        payload={
            "query": "下周三从北京到上海出差，预算 2000 以内，只看直飞",
            "user_id": "u-travel",
            "session_id": "session-travel-demo",
            "options": [
                {
                    "id": "travel-a",
                    "label": "北京-上海 08:30 直飞",
                    "price": 1680,
                    "duration_minutes": 140,
                    "comfort": 0.83,
                    "direct": True,
                    "supplier": "东方航空",
                },
                {
                    "id": "travel-b",
                    "label": "北京-上海 07:10 转机",
                    "price": 1200,
                    "duration_minutes": 320,
                    "comfort": 0.51,
                    "direct": False,
                    "supplier": "某 OTA",
                },
            ],
        },
    )

    assert result["scenario"] == "travel"
    assert result["intent"] == "travel_compare"
    assert result["status"] == "requires_confirmation"
    assert result["intent_slots"]["origin"] == "北京"
    assert result["intent_slots"]["destination"] == "上海"
    assert result["intent_slots"]["budget_max"] == 2000
    assert result["intent_slots"]["direct_only"] is True
    assert result["recommended"]["id"] == "travel-a"
    assert result["requires_confirmation"] is True
    assert result["next_actions"][0]["action"] == "confirm_travel_option"


def test_run_travel_scenario_can_complete_after_confirmation():
    result = run_scenario(
        scenario="travel",
        payload={
            "query": "帮我订北京到上海的商务出差机票",
            "user_id": "u-travel",
            "session_id": "session-travel-confirm",
            "confirm": True,
            "selected_option_id": "travel-a",
            "proposal_id": "travel-proposal-demo",
            "options": [
                {
                    "id": "travel-a",
                    "label": "北京-上海 08:30 直飞",
                    "price": 1680,
                    "duration_minutes": 140,
                    "comfort": 0.83,
                    "direct": True,
                },
                {
                    "id": "travel-b",
                    "label": "北京-上海 07:10 转机",
                    "price": 1200,
                    "duration_minutes": 320,
                    "comfort": 0.51,
                    "direct": False,
                },
            ],
        },
    )

    assert result["status"] == "completed"
    assert result["execution_status"] == "completed"
    assert result["recommended"]["id"] == "travel-a"
    assert result["external_ref"].startswith("TRAVEL-")
    assert result["audit_trace"]["proposal_id"] == "travel-proposal-demo"
    assert result["audit_trace"]["selected_option_id"] == "travel-a"


def test_run_travel_scenario_extracts_clean_route_from_business_query():
    result = run_scenario(
        scenario="travel",
        payload={
            "query": "帮我规划一次上海到北京的商务出行，同时给客户准备鲜花、餐厅和咖啡安排。",
            "options": [
                {
                    "id": "travel-sha-pek-direct",
                    "label": "上海-北京 09:00 直飞",
                    "price": 1760,
                    "duration_minutes": 135,
                    "comfort": 0.86,
                    "direct": True,
                    "origin": "上海",
                    "destination": "北京",
                },
                {
                    "id": "travel-pek-sha-direct",
                    "label": "北京-上海 08:30 直飞",
                    "price": 1680,
                    "duration_minutes": 140,
                    "comfort": 0.83,
                    "direct": True,
                    "origin": "北京",
                    "destination": "上海",
                },
            ],
        },
    )

    assert result["intent_slots"]["origin"] == "上海"
    assert result["intent_slots"]["destination"] == "北京"
    assert result["recommended"]["id"] == "travel-sha-pek-direct"
    assert result["recommended"]["label"].startswith("上海-北京")


def test_run_travel_scenario_aligns_demo_route_label_with_query():
    result = run_scenario(
        scenario="travel",
        payload={
            "query": "帮我规划一次上海到北京的商务出行。",
            "options": [
                {
                    "id": "travel-demo-a",
                    "label": "北京-上海 08:30 直飞",
                    "price": 1680,
                    "duration_minutes": 140,
                    "comfort": 0.83,
                    "direct": True,
                    "origin": "北京",
                    "destination": "上海",
                },
                {
                    "id": "travel-demo-b",
                    "label": "北京-上海 12:10 直飞",
                    "price": 1920,
                    "duration_minutes": 145,
                    "comfort": 0.88,
                    "direct": True,
                    "origin": "北京",
                    "destination": "上海",
                },
            ],
        },
    )

    assert result["intent_slots"]["origin"] == "上海"
    assert result["intent_slots"]["destination"] == "北京"
    assert result["recommended"]["label"].startswith("上海-北京")
    assert result["recommended"]["metadata"]["origin"] == "上海"
    assert result["recommended"]["metadata"]["destination"] == "北京"


def test_run_tokencost_scenario_returns_projected_cost():
    result = run_scenario(
        scenario="tokencost",
        payload={
            "current_monthly_cost": 2000,
            "target_monthly_cost": 800,
            "suggestions": [
                {
                    "id": "switch-mini",
                    "title": "切换到 mini 模型",
                    "estimated_saving": 700,
                    "quality_retention": 0.9,
                    "execution_speed": 0.9,
                    "effort": "low",
                },
                {
                    "id": "prompt-compress",
                    "title": "压缩 Prompt",
                    "estimated_saving": 300,
                    "quality_retention": 0.95,
                    "execution_speed": 0.8,
                    "effort": "low",
                },
            ],
        },
    )

    assert result["scenario"] == "tokencost"
    assert result["projected_monthly_cost"] == 1000
    assert result["feasible"] is False
    assert result["recommendations"][0]["id"] == "switch-mini"


def test_run_robotclaw_scenario_prefers_safe_compliant_option():
    result = run_scenario(
        scenario="robotclaw",
        payload={
            "max_budget_cny": 200000,
            "proposals": [
                {
                    "id": "proposal-a",
                    "price_cny": 160000,
                    "eta_minutes": 28,
                    "safety_score": 0.92,
                    "compliance_score": 0.96,
                    "available": True,
                },
                {
                    "id": "proposal-b",
                    "price_cny": 120000,
                    "eta_minutes": 24,
                    "safety_score": 0.7,
                    "compliance_score": 0.8,
                    "available": True,
                },
            ],
        },
    )

    assert result["scenario"] == "robotclaw"
    assert result["recommended"]["id"] == "proposal-a"
    assert result["contract_ready"] is True
