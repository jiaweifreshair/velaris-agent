"""Biz engine operator graph integration tests."""

from __future__ import annotations

from openharness.biz.engine import run_scenario


def test_run_procurement_scenario_exposes_operator_trace_without_breaking_protocol() -> None:
    """采购场景应保留旧协议，同时暴露 Pareto 链的 operator trace。"""

    result = run_scenario(
        "procurement",
        {
            "query": "比较三家供应商，预算不超过 130000，必须通过合规审计。",
            "budget_max": 130000,
            "require_compliance": True,
            "options": [
                {
                    "id": "vendor-a",
                    "label": "供应商 A",
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
                    "label": "供应商 B",
                    "price_cny": 145000,
                    "delivery_days": 7,
                    "quality_score": 0.91,
                    "compliance_score": 0.99,
                    "risk_score": 0.08,
                    "available": True,
                    "evidence_refs": ["quote://vendor-b"],
                },
            ],
        },
    )

    assert result["recommended"]["id"] == "vendor-a"
    assert result["options"][0]["id"] == "vendor-a"
    assert result["accepted_option_ids"] == ["vendor-a"]
    assert result["audit_trace"]["audit_event"]["operator_id"] == "explanation"
    assert [trace["operator_id"] for trace in result["operator_trace"]] == [
        "intent",
        "option_discovery",
        "normalization",
        "stakeholder",
        "feasibility",
        "pareto_frontier",
        "operating_point_selector",
        "negotiation",
        "bias_audit",
        "explanation",
    ]
