"""Orchestrator + DynamicRouter + CostTracker 集成测试。"""

from __future__ import annotations


from velaris_agent.velaris.cost_tracker import DecisionCostTracker
from velaris_agent.velaris.dynamic_router import DynamicRouter
from velaris_agent.velaris.orchestrator import VelarisBizOrchestrator


# ── 1. Orchestrator 构造测试 ────────────────────────────────

class TestOrchestratorConstruction:
    """编排器新增 dynamic_router 和 cost_tracker 参数。"""

    def test_default_no_dynamic_router(self):
        """默认构造不包含 DynamicRouter。"""
        orch = VelarisBizOrchestrator()
        assert orch.dynamic_router is None

    def test_default_no_cost_tracker(self):
        """默认构造不包含 CostTracker。"""
        orch = VelarisBizOrchestrator()
        assert orch.cost_tracker is None

    def test_with_dynamic_router(self):
        """注入 DynamicRouter。"""
        router = DynamicRouter()
        orch = VelarisBizOrchestrator(dynamic_router=router)
        assert orch.dynamic_router is router

    def test_with_cost_tracker(self):
        """注入 CostTracker。"""
        tracker = DecisionCostTracker(total_budget=1000.0)
        orch = VelarisBizOrchestrator(cost_tracker=tracker)
        assert orch.cost_tracker is tracker
        assert orch.cost_tracker.total_consumed == 0.0

    def test_with_both(self):
        """同时注入 DynamicRouter + CostTracker。"""
        router = DynamicRouter()
        tracker = DecisionCostTracker(total_budget=1000.0)
        orch = VelarisBizOrchestrator(dynamic_router=router, cost_tracker=tracker)
        assert orch.dynamic_router is router
        assert orch.cost_tracker is tracker


# ── 2. 执行成本追踪测试 ────────────────────────────────────

class TestExecutionCostTracking:
    """编排器执行后自动记录成本。"""

    def test_execute_tracks_cost_with_tracker(self):
        """配置了 CostTracker 时，执行后自动记录。"""
        tracker = DecisionCostTracker(total_budget=10000.0)
        orch = VelarisBizOrchestrator(cost_tracker=tracker)
        orch.execute(
            query="帮我选机票",
            payload={},
            scenario="travel",
        )
        # 执行完成后应该有成本记录
        assert tracker.record_count >= 1
        record = tracker.get_records(scenario="travel")[0]
        assert record.execution_id.startswith("exec-")
        assert record.scenario == "travel"

    def test_execute_without_tracker_no_error(self):
        """没有 CostTracker 时也不会报错。"""
        orch = VelarisBizOrchestrator()
        result = orch.execute(
            query="帮我选机票",
            payload={},
            scenario="travel",
        )
        assert result is not None

    def test_execute_with_dynamic_router_no_context(self):
        """配置了 DynamicRouter 但无 RoutingContext 时也能执行。"""
        router = DynamicRouter()
        tracker = DecisionCostTracker()
        orch = VelarisBizOrchestrator(dynamic_router=router, cost_tracker=tracker)
        orch.execute(
            query="帮我选机票",
            payload={},
            scenario="travel",
        )
        # 应该正常执行，cost 记录 model_tier="standard"（因为无 context）
        assert tracker.record_count >= 1
        record = tracker.get_records()[0]
        assert record.model_tier == "standard"

    def test_cost_tracker_tracks_model_tier(self):
        """CostTracker 记录 DynamicRouter 的模型等级。"""
        router = DynamicRouter()
        tracker = DecisionCostTracker()
        orch = VelarisBizOrchestrator(dynamic_router=router, cost_tracker=tracker)
        orch.execute(
            query="帮我选机票",
            payload={},
            scenario="travel",
        )
        # 无 RoutingContext 时 model_tier="standard"
        records = tracker.get_records()
        assert len(records) >= 1
        assert records[0].model_tier == "standard"


# ── 3. DynamicRouter 向后兼容测试 ──────────────────────────

class TestDynamicRouterBackwardCompat:
    """DynamicRouter 不影响已有的 PolicyRouter 行为。"""

    def test_existing_router_tests_still_pass(self):
        """原有 router 测试应该仍然通过。"""
        from velaris_agent.velaris.router import PolicyRouter
        router = PolicyRouter()
        plan = {
            "scenario": "general",
            "capabilities": ["read", "reason"],
            "governance": {},
            "constraints": {},
        }
        decision = router.route(plan, "测试查询")
        assert decision.selected_strategy is not None
        assert decision.selected_route is not None

    def test_orchestrator_with_old_router(self):
        """使用旧 PolicyRouter 的编排器仍然正常。"""
        from velaris_agent.velaris.router import PolicyRouter
        router = PolicyRouter()
        orch = VelarisBizOrchestrator(router=router)
        result = orch.execute(
            query="帮我选机票",
            payload={},
            scenario="travel",
        )
        assert result is not None


# ── 4. CostTracker 与 DynamicRouter 协同 ────────────────────

class TestCostTrackerWithDynamicRouter:
    """CostTracker 和 DynamicRouter 的协同场景。"""

    def test_roi_after_multiple_executions(self):
        """多次执行后 ROI 报告可用。"""
        tracker = DecisionCostTracker(total_budget=10000.0)
        orch = VelarisBizOrchestrator(cost_tracker=tracker)

        for _ in range(3):
            orch.execute(
                query="帮我选机票",
                payload={},
                scenario="travel",
            )

        report = tracker.roi("travel")
        assert report.total_executions == 3
        assert report.total_token_input >= 0

    def test_budget_status_after_execution(self):
        """执行后预算状态更新。"""
        tracker = DecisionCostTracker(total_budget=100.0)
        orch = VelarisBizOrchestrator(cost_tracker=tracker)
        orch.execute(query="帮我选机票", payload={}, scenario="travel")

        status = tracker.budget_status()
        assert status.total_budget == 100.0
        # 消耗可能为 0（因为 token_input=0 默认）
        assert status.consumed >= 0

    def test_cost_by_scenario_aggregation(self):
        """按场景聚合成本统计。"""
        tracker = DecisionCostTracker()
        orch = VelarisBizOrchestrator(cost_tracker=tracker)

        orch.execute(query="选机票", payload={}, scenario="travel")
        orch.execute(query="分析成本", payload={}, scenario="tokencost")

        by_scenario = tracker.cost_by_scenario()
        assert "travel" in by_scenario
        assert "tokencost" in by_scenario
