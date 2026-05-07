"""Velaris 业务编排闭环测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from openharness.velaris.orchestrator import VelarisBizOrchestrator
from velaris_agent.biz.engine import build_capability_plan
from velaris_agent.memory.types import (
    InterestDimension,
    PreferenceDirection,
    Stakeholder,
    StakeholderMapModel,
    StakeholderRole,
)


def _make_procurement_stakeholder_map() -> StakeholderMapModel:
    """构造一个会产生高严重度 cost 冲突的采购 stakeholder map。"""

    return StakeholderMapModel(
        map_id="procurement-map-test",
        scenario="procurement",
        stakeholders=[
            Stakeholder(
                stakeholder_id="finance",
                role=StakeholderRole.ORG,
                display_name="财务",
                scenario="procurement",
                interest_dimensions=[
                    InterestDimension(
                        dimension="cost",
                        direction=PreferenceDirection.LOWER_IS_BETTER,
                        weight=0.9,
                    )
                ],
                influence_weights={"cost": 0.95},
            ),
            Stakeholder(
                stakeholder_id="delivery-owner",
                role=StakeholderRole.USER,
                display_name="交付负责人",
                scenario="procurement",
                interest_dimensions=[
                    InterestDimension(
                        dimension="cost",
                        direction=PreferenceDirection.HIGHER_IS_BETTER,
                        weight=0.8,
                    )
                ],
                influence_weights={"cost": 0.90},
            ),
        ],
        alignment_matrix=[],
        conflicts=[],
        timestamp=datetime.now(timezone.utc),
    )


def _make_quality_focused_procurement_stakeholder_map() -> StakeholderMapModel:
    """构造一个会把采购权重明显拉向 quality 的 stakeholder map。"""

    return StakeholderMapModel(
        map_id="procurement-quality-map-test",
        scenario="procurement",
        stakeholders=[
            Stakeholder(
                stakeholder_id="cto",
                role=StakeholderRole.ORG,
                display_name="技术负责人",
                scenario="procurement",
                interest_dimensions=[
                    InterestDimension(
                        dimension="quality",
                        direction=PreferenceDirection.HIGHER_IS_BETTER,
                        weight=0.95,
                    ),
                    InterestDimension(
                        dimension="cost",
                        direction=PreferenceDirection.LOWER_IS_BETTER,
                        weight=0.20,
                    ),
                ],
                influence_weights={"quality": 1.0, "cost": 0.0},
            ),
            Stakeholder(
                stakeholder_id="ops",
                role=StakeholderRole.USER,
                display_name="运维负责人",
                scenario="procurement",
                interest_dimensions=[
                    InterestDimension(
                        dimension="quality",
                        direction=PreferenceDirection.HIGHER_IS_BETTER,
                        weight=0.90,
                    ),
                    InterestDimension(
                        dimension="cost",
                        direction=PreferenceDirection.LOWER_IS_BETTER,
                        weight=0.25,
                    ),
                ],
                influence_weights={"quality": 1.0, "cost": 0.0},
            ),
        ],
        alignment_matrix=[],
        conflicts=[],
        timestamp=datetime.now(timezone.utc),
    )


def test_orchestrator_executes_tokencost_flow_with_runtime_controls(tmp_path: Path) -> None:
    orchestrator = VelarisBizOrchestrator(cwd=tmp_path)

    result = orchestrator.execute(
        query="我每月 OpenAI 成本 2000 美元，想降到 800",
        constraints={"target_monthly_cost": 800},
        payload={
            "current_monthly_cost": 2000,
            "target_monthly_cost": 800,
            "suggestions": [
                {
                    "id": "switch-tier",
                    "title": "分层路由",
                    "estimated_saving": 900,
                    "quality_retention": 0.88,
                    "execution_speed": 0.9,
                    "effort": "medium",
                },
                {
                    "id": "cache-enable",
                    "title": "缓存命中",
                    "estimated_saving": 250,
                    "quality_retention": 0.97,
                    "execution_speed": 0.75,
                    "effort": "low",
                },
            ],
        },
        session_id="session-token",
    )

    assert result["envelope"]["plan"]["scenario"] == "tokencost"
    assert result["envelope"]["routing"]["selected_strategy"] == "local_closed_loop"
    assert result["envelope"]["authority"]["approvals_required"] is False
    assert result["envelope"]["execution"]["gate_status"] == "allowed"
    assert result["envelope"]["execution"]["audit_status"] == "not_required"
    assert result["envelope"]["tasks"][0]["status"] == "completed"
    assert result["result"]["projected_monthly_cost"] == 850
    assert result["outcome"]["success"] is True
    assert result["audit_event_count"] == 2
    assert len(orchestrator.task_ledger.list_by_session("session-token")) == 1
    assert len(orchestrator.outcome_store.list_by_session("session-token")) == 1
    execution_id = result["envelope"]["execution"]["execution_id"]
    stored_execution = orchestrator.execution_repository.get(execution_id)
    assert stored_execution is not None
    assert stored_execution.resume_cursor == {"stage": "completed"}


def test_orchestrator_persists_session_snapshot_with_correct_cwd_for_resume(tmp_path: Path) -> None:
    """session snapshot 必须写入正确 cwd，避免 /resume 无法按工作区检索。"""

    orchestrator = VelarisBizOrchestrator(cwd=tmp_path)
    session_id = "session-cwd-snapshot"

    orchestrator.execute(
        query="我每月 OpenAI 成本 2000 美元，想降到 800",
        constraints={"target_monthly_cost": 800},
        payload={
            "current_monthly_cost": 2000,
            "target_monthly_cost": 800,
            "suggestions": [
                {
                    "id": "switch-tier",
                    "title": "分层路由",
                    "estimated_saving": 900,
                    "quality_retention": 0.88,
                    "execution_speed": 0.9,
                    "effort": "medium",
                }
            ],
        },
        session_id=session_id,
    )

    repository = orchestrator.session_repository
    assert repository is not None
    stored = repository.get(session_id)
    assert stored is not None
    assert stored.snapshot_json["cwd"] == str(tmp_path.resolve())
    assert repository.latest_by_cwd(str(tmp_path.resolve())).session_id == session_id


def test_orchestrator_executes_robotclaw_flow_with_strict_governance():
    class InMemoryAuditStore:
        """用于严格治理场景的最小审计仓储。"""

        def __init__(self) -> None:
            self.events: list[dict[str, object]] = []

        def append_event(
            self,
            session_id: str,
            step_name: str,
            operator_id: str,
            payload: dict[str, object] | None = None,
        ) -> None:
            self.events.append(
                {
                    "session_id": session_id,
                    "step_name": step_name,
                    "operator_id": operator_id,
                    "payload": dict(payload or {}),
                }
            )

    audit_store = InMemoryAuditStore()
    orchestrator = VelarisBizOrchestrator(audit_store=audit_store)

    result = orchestrator.execute(
        query="为 robotaxi 派单生成服务提案并形成交易合约",
        constraints={"requires_audit": True},
        payload={
            "max_budget_cny": 200000,
            "proposals": [
                {
                    "id": "dispatch-a",
                    "price_cny": 180000,
                    "eta_minutes": 22,
                    "safety_score": 0.95,
                    "compliance_score": 0.95,
                    "available": True,
                },
                {
                    "id": "dispatch-b",
                    "price_cny": 100000,
                    "eta_minutes": 18,
                    "safety_score": 0.68,
                    "compliance_score": 0.82,
                    "available": True,
                },
            ],
        },
        session_id="session-robotclaw",
    )

    assert result["envelope"]["plan"]["scenario"] == "robotclaw"
    assert result["envelope"]["routing"]["selected_strategy"] == "delegated_robotclaw"
    assert result["envelope"]["authority"]["approvals_required"] is True
    assert "audit" in result["envelope"]["authority"]["required_capabilities"]
    assert result["envelope"]["execution"]["execution_status"] == "blocked"
    assert result["envelope"]["execution"]["gate_status"] == "denied"
    assert result["result"] == {}
    assert result["outcome"]["success"] is False
    assert result["audit_event_count"] == 1
    assert len(audit_store.events) == 1


def test_orchestrator_wires_stakeholder_context_into_procurement_graph():
    """采购编排链路应把 stakeholder_map 产出的 context 接到 operator graph。"""

    class InMemoryAuditStore:
        """为采购编排测试提供最小审计仓储。"""

        def __init__(self) -> None:
            self.events: list[dict[str, object]] = []

        def append_event(
            self,
            session_id: str,
            step_name: str,
            operator_id: str,
            payload: dict[str, object] | None = None,
        ) -> None:
            self.events.append(
                {
                    "session_id": session_id,
                    "step_name": step_name,
                    "operator_id": operator_id,
                    "payload": dict(payload or {}),
                }
            )

    audit_store = InMemoryAuditStore()
    orchestrator = VelarisBizOrchestrator(audit_store=audit_store)

    result = orchestrator.execute(
        query="比较两家供应商，预算不超过 200000，必须通过合规审计。",
        scenario="procurement",
        payload={
            "budget_max": 200000,
            "require_compliance": True,
            "stakeholder_map": _make_procurement_stakeholder_map().model_dump(mode="json"),
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
                },
                {
                    "id": "vendor-b",
                    "label": "供应商 B",
                    "price_cny": 125000,
                    "delivery_days": 7,
                    "quality_score": 0.88,
                    "compliance_score": 0.96,
                    "risk_score": 0.12,
                    "available": True,
                },
            ],
        },
        session_id="session-procurement-stakeholder",
    )

    stakeholder_trace = next(
        item
        for item in result["result"]["operator_trace"]
        if item["operator_id"] == "stakeholder"
    )

    assert "stakeholder_context" in result["envelope"]["plan"]
    assert result["envelope"]["plan"]["stakeholder_context"]["conflicts"]
    assert result["envelope"]["plan"]["stakeholder_context"]["negotiation_proposals"]
    assert result["envelope"]["execution"]["gate_status"] == "degraded"
    assert stakeholder_trace["warnings"] == result["envelope"]["plan"]["stakeholder_context"]["warnings"]


def test_orchestrator_passes_plan_decision_weights_into_procurement_ranking():
    """编排器生成的 decision_weights 必须真正影响采购排序。"""

    class InMemoryAuditStore:
        """为权重透传测试提供最小审计仓储。"""

        def append_event(
            self,
            session_id: str,
            step_name: str,
            operator_id: str,
            payload: dict[str, object] | None = None,
        ) -> None:
            del session_id, step_name, operator_id, payload

    orchestrator = VelarisBizOrchestrator(audit_store=InMemoryAuditStore())

    result = orchestrator.execute(
        query="比较两家供应商，质量优先，但仍需满足合规。",
        scenario="procurement",
        payload={
            "budget_max": 250000,
            "require_compliance": True,
            "stakeholder_map": _make_quality_focused_procurement_stakeholder_map().model_dump(mode="json"),
            "options": [
                {
                    "id": "budget-choice",
                    "label": "低价方案",
                    "price_cny": 100000,
                    "delivery_days": 7,
                    "quality_score": 0.70,
                    "compliance_score": 0.95,
                    "risk_score": 0.10,
                    "available": True,
                },
                {
                    "id": "premium-choice",
                    "label": "高质量方案",
                    "price_cny": 170000,
                    "delivery_days": 7,
                    "quality_score": 0.95,
                    "compliance_score": 0.95,
                    "risk_score": 0.10,
                    "available": True,
                },
            ],
        },
        session_id="session-procurement-weighted",
    )

    assert result["envelope"]["plan"]["decision_weights"]["quality"] > result["envelope"]["plan"]["decision_weights"]["cost"]
    assert result["envelope"]["execution"]["gate_status"] == "degraded"
    assert result["result"]["recommended"]["id"] == "premium-choice"


def test_orchestrator_uses_scenario_profile_as_effective_risk_truth_source() -> None:
    """effective risk 应由 scenario profile 修正，而不是直接复用 routing 原始风险。"""

    class InMemoryAuditStore:
        """为 effective risk 断言提供最小审计仓储。"""

        def append_event(
            self,
            session_id: str,
            step_name: str,
            operator_id: str,
            payload: dict[str, object] | None = None,
        ) -> None:
            del session_id, step_name, operator_id, payload

    orchestrator = VelarisBizOrchestrator(audit_store=InMemoryAuditStore())
    plan = build_capability_plan(
        query="比较两家供应商，预算不超过 200000，必须通过合规审计。",
        scenario="procurement",
    )
    routing = orchestrator.router.route(plan=plan, query=plan["query"])
    authority = orchestrator.authority_service.issue_plan(
        required_capabilities=routing.required_capabilities,
        governance=plan["governance"],
    )

    gate_decision = orchestrator._build_gate_decision(
        plan=plan,
        routing=routing.to_dict(),
        authority=authority.to_dict(),
    )

    assert routing.trace["routing_context"]["risk"]["level"] == "high"
    assert gate_decision.effective_risk_level == "medium"
    assert gate_decision.gate_status == "degraded"


def test_orchestrator_persists_audit_trace(tmp_path: Path) -> None:
    """编排器在接入 SQLite 审计仓储时应写入最小审计轨迹。"""

    from velaris_agent.persistence.schema import bootstrap_sqlite_schema
    from velaris_agent.persistence.sqlite_helpers import get_project_database_path
    from velaris_agent.persistence.sqlite_runtime import (
        SqliteAuditEventStore,
        SqliteOutcomeStore,
        SqliteTaskLedger,
    )

    session_id = f"session-audit-{uuid4().hex[:12]}"

    database_path = get_project_database_path(tmp_path)
    bootstrap_sqlite_schema(database_path)
    audit_store = SqliteAuditEventStore(str(database_path))
    orchestrator = VelarisBizOrchestrator(
        task_ledger=SqliteTaskLedger(str(database_path)),
        outcome_store=SqliteOutcomeStore(str(database_path)),
        audit_store=audit_store,
        cwd=tmp_path,
        sqlite_database_path=database_path,
    )

    result = orchestrator.execute(
        query="我每月 OpenAI 成本 2000 美元，想降到 800",
        constraints={"target_monthly_cost": 800},
        payload={
            "current_monthly_cost": 2000,
            "target_monthly_cost": 800,
            "suggestions": [
                {
                    "id": "switch-tier",
                    "title": "分层路由",
                    "estimated_saving": 900,
                    "quality_retention": 0.88,
                    "execution_speed": 0.9,
                    "effort": "medium",
                }
            ],
        },
        session_id=session_id,
    )

    events = audit_store.list_by_session(session_id)

    assert result["envelope"]["tasks"][0]["status"] == "completed"
    assert result["envelope"]["execution"]["audit_status"] == "not_required"
    assert result["audit_event_count"] == 2
    assert len(events) == 2
    assert {event.step_name for event in events} == {
        "orchestrator.routed",
        "orchestrator.completed",
    }


def test_orchestrator_ignores_audit_store_failures_on_success():
    """审计仓储写入失败时不应把成功流程改写为失败。"""

    class BrokenAuditStore:
        """用于模拟审计仓储不可用的最小假对象。"""

        def append_event(
            self,
            session_id: str,
            step_name: str,
            operator_id: str,
            payload: dict[str, object] | None = None,
        ) -> None:
            raise RuntimeError(f"audit down: {step_name}")

    orchestrator = VelarisBizOrchestrator(audit_store=BrokenAuditStore())

    result = orchestrator.execute(
        query="我每月 OpenAI 成本 2000 美元，想降到 800",
        constraints={"target_monthly_cost": 800},
        payload={
            "current_monthly_cost": 2000,
            "target_monthly_cost": 800,
            "suggestions": [
                {
                    "id": "switch-tier",
                    "title": "分层路由",
                    "estimated_saving": 900,
                    "quality_retention": 0.88,
                    "execution_speed": 0.9,
                    "effort": "medium",
                }
            ],
        },
        session_id="session-audit-fallback",
    )

    assert result["envelope"]["tasks"][0]["status"] == "completed"
    assert result["outcome"]["success"] is True
    assert result["audit_event_count"] == 0


def test_orchestrator_requires_audit_trail_for_strict_governance():
    """高风险审计场景在审计链路不可用时必须失败，而不是静默降级。"""

    class BrokenAuditStore:
        """用于模拟审计仓储不可用的最小假对象。"""

        def append_event(
            self,
            session_id: str,
            step_name: str,
            operator_id: str,
            payload: dict[str, object] | None = None,
        ) -> None:
            raise RuntimeError(f"audit down: {step_name}")

    orchestrator = VelarisBizOrchestrator(audit_store=BrokenAuditStore())

    with pytest.raises(RuntimeError) as exc_info:
        orchestrator.execute(
            query="为 robotaxi 派单生成服务提案并形成交易合约",
            constraints={"requires_audit": True},
            payload={
                "max_budget_cny": 200000,
                "proposals": [
                    {
                        "id": "dispatch-a",
                        "price_cny": 180000,
                        "eta_minutes": 22,
                        "safety_score": 0.95,
                        "compliance_score": 0.95,
                        "available": True,
                    }
                ],
            },
            session_id="session-required-audit",
        )

    error_payload = exc_info.value.args[0]
    assert error_payload["envelope"]["execution"]["execution_status"] == "blocked"
    assert error_payload["envelope"]["execution"]["gate_status"] == "denied"
    assert error_payload["outcome"]["success"] is False
    assert "audit trail required" in error_payload["outcome"]["summary"]
    assert error_payload["audit_event_count"] == 0


def test_orchestrator_preserves_original_business_failure_when_audit_store_breaks():
    """业务执行失败时，审计异常不应覆盖原始失败上下文。"""

    class BrokenAuditStore:
        """用于模拟审计仓储不可用的最小假对象。"""

        def append_event(
            self,
            session_id: str,
            step_name: str,
            operator_id: str,
            payload: dict[str, object] | None = None,
        ) -> None:
            raise RuntimeError(f"audit down: {step_name}")

    orchestrator = VelarisBizOrchestrator(audit_store=BrokenAuditStore())
    original_error = ValueError("biz exploded")

    def fake_run_scenario(scenario: str, payload: dict[str, object]) -> dict[str, object]:
        raise original_error

    with pytest.raises(RuntimeError) as exc_info:
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr("velaris_agent.velaris.orchestrator.run_scenario", fake_run_scenario)
            orchestrator.execute(
                query="我每月 OpenAI 成本 2000 美元，想降到 800",
                constraints={"target_monthly_cost": 800},
                payload={
                    "current_monthly_cost": 2000,
                    "target_monthly_cost": 800,
                    "suggestions": [],
                },
                session_id="session-audit-error",
            )

    error_payload = exc_info.value.args[0]
    assert error_payload["envelope"]["execution"]["execution_status"] == "failed"
    assert error_payload["outcome"]["success"] is False
    assert error_payload["outcome"]["summary"] == "biz exploded"
    assert error_payload["audit_event_count"] == 0


def test_orchestrator_appends_operator_trace_summary_into_audit_payload() -> None:
    """编排器应把 procurement operator trace 摘要写进完成审计事件。"""

    class InMemoryAuditStore:
        """用于捕获编排器审计 payload 的最小仓储。"""

        def __init__(self) -> None:
            self.events: list[dict[str, object]] = []

        def append_event(
            self,
            session_id: str,
            step_name: str,
            operator_id: str,
            payload: dict[str, object] | None = None,
        ) -> None:
            self.events.append(
                {
                    "session_id": session_id,
                    "step_name": step_name,
                    "operator_id": operator_id,
                    "payload": dict(payload or {}),
                }
            )

    audit_store = InMemoryAuditStore()
    orchestrator = VelarisBizOrchestrator(audit_store=audit_store)

    result = orchestrator.execute(
        query="比较三家供应商，预算不超过 130000，必须通过合规审计。",
        scenario="procurement",
        payload={
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
                }
            ],
        },
        constraints={"risk_level": "medium"},
        session_id="session-procurement-phase2",
    )

    assert result["audit_event_count"] == 2
    assert result["result"]["operator_trace"][0]["operator_id"] == "intent"
    assert result["result"]["audit_trace"]["audit_event"]["operator_id"] == "explanation"
    assert result["envelope"]["execution"]["gate_status"] == "degraded"
    completed_payload = audit_store.events[1]["payload"]
    assert completed_payload["operator_trace_summary"][0]["operator_id"] == "intent"
