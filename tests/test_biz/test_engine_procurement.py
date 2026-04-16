"""采购场景业务引擎测试。"""

from __future__ import annotations

from openharness.biz.engine import build_capability_plan, infer_scenario, run_scenario


def test_infer_scenario_recognizes_procurement_keywords() -> None:
    """应把采购、供应商与合规审计语义识别为 procurement。"""

    scenario = infer_scenario("帮我做企业采购供应商比价，并检查合规审计风险。")

    assert scenario == "procurement"


def test_build_capability_plan_for_procurement_query() -> None:
    """采购场景应返回独立能力规划，而不是落回 general。"""

    plan = build_capability_plan(
        query="请为新办公设备做供应商采购比价，并输出合规审计建议。",
        constraints={"budget_max": 150000},
    )

    assert plan["scenario"] == "procurement"
    assert "supplier_compare" in plan["capabilities"]
    assert "compliance_review" in plan["capabilities"]
    assert plan["governance"]["requires_audit"] is True
    assert plan["governance"]["approval_mode"] == "strict"
    assert plan["decision_weights"]["compliance"] > 0
    assert plan["recommended_tools"][0] == "biz_execute"


def test_run_procurement_scenario_returns_structured_recommendation() -> None:
    """采购场景应返回可审计的结构化推荐结果。"""

    result = run_scenario(
        scenario="procurement",
        payload={
            "query": "比较三家笔记本供应商，预算不超过 130000，必须通过合规审计。",
            "budget_max": 130000,
            "require_compliance": True,
            "max_delivery_days": 10,
            "options": [
                {
                    "id": "vendor-a",
                    "label": "供应商 A 标准方案",
                    "vendor": "供应商 A",
                    "price_cny": 118000,
                    "delivery_days": 9,
                    "quality_score": 0.90,
                    "compliance_score": 0.98,
                    "risk_score": 0.10,
                    "available": True,
                    "evidence_refs": ["quote://vendor-a", "policy://approved-vendors"],
                },
                {
                    "id": "vendor-b",
                    "label": "供应商 B 低价方案",
                    "vendor": "供应商 B",
                    "price_cny": 99000,
                    "delivery_days": 7,
                    "quality_score": 0.82,
                    "compliance_score": 0.76,
                    "risk_score": 0.22,
                    "available": True,
                    "evidence_refs": ["quote://vendor-b"],
                },
                {
                    "id": "vendor-c",
                    "label": "供应商 C 长交付方案",
                    "vendor": "供应商 C",
                    "price_cny": 124000,
                    "delivery_days": 15,
                    "quality_score": 0.94,
                    "compliance_score": 0.96,
                    "risk_score": 0.08,
                    "available": True,
                    "evidence_refs": ["quote://vendor-c"],
                },
            ],
        },
    )

    assert result["scenario"] == "procurement"
    assert result["intent"] == "procurement_compare"
    assert result["status"] == "proposal_ready"
    assert result["recommended"]["id"] == "vendor-a"
    assert result["accepted_option_ids"] == ["vendor-a"]
    assert result["audit_trace"]["recommended_option_id"] == "vendor-a"
    assert result["audit_trace"]["audit_event"]["operator_id"] == "explanation"
    assert [trace["operator_id"] for trace in result["operator_trace"]] == [
        "intent",
        "option_discovery",
        "normalization",
        "stakeholder",
        "feasibility",
        "optimization",
        "negotiation",
        "bias_audit",
        "explanation",
    ]
