"""Decision operator registry tests."""

from __future__ import annotations

import pytest

from velaris_agent.decision.operators.registry import build_default_operator_registry


def test_operator_registry_returns_default_procurement_graph() -> None:
    """默认 registry 应在过渡态先接入 feasibility，再复用既有 optimization。"""

    registry = build_default_operator_registry()
    graph = registry.get_graph("procurement")

    assert [spec.operator_id for spec in graph] == [
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


def test_operator_registry_keeps_non_procurement_scenarios_on_legacy_path() -> None:
    """Phase 2 中非 procurement 场景不应接入 operator graph。"""

    registry = build_default_operator_registry()

    with pytest.raises(KeyError):
        registry.get_graph("travel")
