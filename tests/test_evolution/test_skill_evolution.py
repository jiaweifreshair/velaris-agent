"""SkillEvolutionLoop 测试 — Skill 自进化4步循环：反馈→学习→验证→部署。"""

from __future__ import annotations

from pathlib import Path


from velaris_agent.evolution.skill_evolution import (
    EvolutionCycleResult,
    SkillEvolutionLoop,
    SkillFeedback,
    SkillMutation,
)
from velaris_agent.velaris.cost_tracker import DecisionCostTracker


# ── 1. SkillFeedback 测试 ──────────────────────────────────────

class TestSkillFeedback:
    """SkillFeedback 数据模型测试。"""

    def test_create_feedback(self):
        fb = SkillFeedback(
            execution_id="exec-001",
            scenario="travel",
            quality_score=0.85,
        )
        assert fb.execution_id == "exec-001"
        assert fb.scenario == "travel"
        assert fb.quality_score == 0.85
        assert fb.feedback_id  # 自动生成
        assert fb.timestamp  # 自动生成

    def test_quality_score_clamped(self):
        """超出范围的 quality_score 会被 clamp 到 [0,1]。"""
        loop = SkillEvolutionLoop()
        fb = loop.collect_feedback(execution_id="exec-002", scenario="general", quality_score=1.5)
        assert fb.quality_score == 1.0  # clamped to max

    def test_quality_score_clamped_zero(self):
        """负数的 quality_score 会被 clamp 到 0。"""
        loop = SkillEvolutionLoop()
        fb = loop.collect_feedback(execution_id="exec-003", scenario="general", quality_score=-0.5)
        assert fb.quality_score == 0.0  # clamped to min

    def test_optional_fields(self):
        fb = SkillFeedback(
            execution_id="exec-004",
            scenario="travel",
            quality_score=0.7,
            user_satisfaction=4.2,
            token_cost=0.45,
            latency_ms=1500.0,
        )
        assert fb.user_satisfaction == 4.2
        assert fb.token_cost == 0.45
        assert fb.latency_ms == 1500.0


# ── 2. SkillMutation 测试 ──────────────────────────────────────

class TestSkillMutation:
    """SkillMutation 数据模型测试。"""

    def test_create_mutation(self):
        m = SkillMutation(
            scenario="travel",
            mutation_type="tier_change",
            description="建议升级模型",
            before={"model_tier": "economy"},
            after={"model_tier": "standard"},
            confidence=0.7,
        )
        assert m.scenario == "travel"
        assert m.mutation_type == "tier_change"
        assert m.confidence == 0.7
        assert not m.validated
        assert not m.deployed

    def test_default_values(self):
        m = SkillMutation(
            scenario="general",
            mutation_type="weight_adjust",
            description="调整权重",
        )
        assert m.confidence == 0.5
        assert m.source_feedback_ids == []
        assert m.mutation_id  # 自动生成


# ── 3. collect_feedback 测试 ──────────────────────────────────

class TestCollectFeedback:
    """反馈收集测试。"""

    def test_collect_basic_feedback(self):
        loop = SkillEvolutionLoop()
        fb = loop.collect_feedback(
            execution_id="exec-001",
            scenario="travel",
            quality_score=0.8,
        )
        assert fb.execution_id == "exec-001"
        assert fb.quality_score == 0.8
        assert len(loop.get_feedbacks()) == 1

    def test_collect_multiple_feedbacks(self):
        loop = SkillEvolutionLoop()
        for i in range(5):
            loop.collect_feedback(
                execution_id=f"exec-{i:03d}",
                scenario="travel",
                quality_score=0.7,
            )
        assert len(loop.get_feedbacks()) == 5

    def test_collect_from_cost_record(self):
        tracker = DecisionCostTracker()
        tracker.track("exec-001", "travel", token_input=1000, token_output=500, model_tier="standard")
        record = tracker.get_records()[0]

        loop = SkillEvolutionLoop()
        fb = loop.collect_from_cost_record(record, quality_score=0.75)
        assert fb.execution_id == "exec-001"
        assert fb.model_tier == "standard"
        assert fb.token_cost == record.cost_estimate

    def test_persistence(self, tmp_path: Path):
        loop = SkillEvolutionLoop(persistence_dir=tmp_path)
        loop.collect_feedback(execution_id="exec-001", scenario="travel", quality_score=0.8)
        fb_files = list((tmp_path / "feedbacks").glob("*.json"))
        assert len(fb_files) == 1

    def test_no_persistence_by_default(self, tmp_path: Path):
        loop = SkillEvolutionLoop()
        loop.collect_feedback(execution_id="exec-001", scenario="travel", quality_score=0.8)
        assert not (tmp_path / "feedbacks").exists()


# ── 4. learn 测试 ──────────────────────────────────────────────

class TestLearn:
    """学习变更建议测试。"""

    def test_learn_low_quality_triggers_tier_change(self):
        loop = SkillEvolutionLoop(min_feedback_count=3)
        for i in range(4):
            loop.collect_feedback(
                execution_id=f"exec-{i:03d}",
                scenario="travel",
                quality_score=0.3,
                model_tier="economy",
            )
        mutations = loop.learn()
        assert len(mutations) > 0
        tier_mutations = [m for m in mutations if m.mutation_type == "tier_change"]
        assert len(tier_mutations) > 0

    def test_learn_high_cost_triggers_downgrade(self):
        loop = SkillEvolutionLoop(min_feedback_count=3)
        for i in range(4):
            loop.collect_feedback(
                execution_id=f"exec-{i:03d}",
                scenario="travel",
                quality_score=0.7,
                token_cost=3.0,
                model_tier="standard",
            )
        mutations = loop.learn()
        cost_mutations = [m for m in mutations if "成本" in m.description or "cost" in m.description.lower()]
        assert len(cost_mutations) > 0

    def test_learn_high_latency_triggers_param_tune(self):
        loop = SkillEvolutionLoop(min_feedback_count=3)
        for i in range(4):
            loop.collect_feedback(
                execution_id=f"exec-{i:03d}",
                scenario="travel",
                quality_score=0.7,
                latency_ms=8000.0,
            )
        mutations = loop.learn()
        latency_mutations = [m for m in mutations if "延迟" in m.description or "latency" in m.description.lower()]
        assert len(latency_mutations) > 0

    def test_learn_filter_by_scenario(self):
        loop = SkillEvolutionLoop(min_feedback_count=3)
        for i in range(4):
            loop.collect_feedback(
                execution_id=f"exec-t-{i:03d}",
                scenario="travel",
                quality_score=0.3,
            )
            loop.collect_feedback(
                execution_id=f"exec-g-{i:03d}",
                scenario="general",
                quality_score=0.8,
            )
        mutations = loop.learn(scenario="travel")
        assert all(m.scenario == "travel" for m in mutations)

    def test_learn_insufficient_feedbacks(self):
        loop = SkillEvolutionLoop(min_feedback_count=5)
        for i in range(3):
            loop.collect_feedback(
                execution_id=f"exec-{i:03d}",
                scenario="travel",
                quality_score=0.3,
            )
        mutations = loop.learn()
        assert len(mutations) == 0  # 不足 min_feedback_count


# ── 5. validate 测试 ──────────────────────────────────────────

class TestValidate:
    """变更验证测试。"""

    def test_validate_high_confidence(self):
        loop = SkillEvolutionLoop(validation_threshold=0.6)
        mutation = SkillMutation(
            scenario="travel",
            mutation_type="tier_change",
            description="升级模型",
            before={"model_tier": "economy"},
            after={"model_tier": "standard"},
            confidence=0.8,
        )
        assert loop.validate(mutation) is True
        assert mutation.validated is True

    def test_validate_low_confidence(self):
        loop = SkillEvolutionLoop(validation_threshold=0.6)
        mutation = SkillMutation(
            scenario="travel",
            mutation_type="weight_adjust",
            description="调整权重",
            before={"x": 0.5},
            after={"x": 0.6},
            confidence=0.3,
        )
        assert loop.validate(mutation) is False
        assert mutation.validated is False

    def test_validate_no_empty_change(self):
        loop = SkillEvolutionLoop(validation_threshold=0.3)
        mutation = SkillMutation(
            scenario="travel",
            mutation_type="weight_adjust",
            description="无变化",
            before={"x": 0.5},
            after={"x": 0.5},
            confidence=0.9,
        )
        assert loop.validate(mutation) is False

    def test_validate_no_premium_to_economy(self):
        """不允许从 premium 直降 economy。"""
        loop = SkillEvolutionLoop(validation_threshold=0.3)
        mutation = SkillMutation(
            scenario="travel",
            mutation_type="tier_change",
            description="跨级降级",
            before={"model_tier": "premium"},
            after={"model_tier": "economy"},
            confidence=0.9,
        )
        assert loop.validate(mutation) is False

    def test_validate_tool_remove_requires_high_confidence(self):
        """工具删除需要高置信度。"""
        loop = SkillEvolutionLoop(validation_threshold=0.3)
        mutation = SkillMutation(
            scenario="travel",
            mutation_type="tool_remove",
            description="删除工具",
            before={"tool": "biz_score"},
            after={},
            confidence=0.5,  # 低于 0.8
        )
        assert loop.validate(mutation) is False


# ── 6. deploy 测试 ──────────────────────────────────────────────

class TestDeploy:
    """变更部署测试。"""

    def test_deploy_validated_mutation(self):
        loop = SkillEvolutionLoop()
        mutation = SkillMutation(
            scenario="travel",
            mutation_type="tier_change",
            description="升级模型",
            before={"model_tier": "economy"},
            after={"model_tier": "standard"},
            confidence=0.8,
            validated=True,
        )
        assert loop.deploy(mutation) is True
        assert mutation.deployed is True

    def test_deploy_unvalidated_mutation_fails(self):
        loop = SkillEvolutionLoop()
        mutation = SkillMutation(
            scenario="travel",
            mutation_type="tier_change",
            description="升级模型",
            before={"model_tier": "economy"},
            after={"model_tier": "standard"},
            confidence=0.8,
            validated=False,
        )
        assert loop.deploy(mutation) is False

    def test_deploy_idempotent(self):
        loop = SkillEvolutionLoop()
        mutation = SkillMutation(
            scenario="travel",
            mutation_type="tier_change",
            description="升级模型",
            before={"model_tier": "economy"},
            after={"model_tier": "standard"},
            confidence=0.8,
            validated=True,
        )
        assert loop.deploy(mutation) is True
        assert loop.deploy(mutation) is True  # 幂等

    def test_deploy_persists(self, tmp_path: Path):
        loop = SkillEvolutionLoop(persistence_dir=tmp_path)
        mutation = SkillMutation(
            scenario="travel",
            mutation_type="tier_change",
            description="升级模型",
            before={"model_tier": "economy"},
            after={"model_tier": "standard"},
            confidence=0.8,
            validated=True,
        )
        loop.deploy(mutation)
        mt_files = list((tmp_path / "mutations").glob("*.json"))
        assert len(mt_files) == 1


# ── 7. run_cycle 完整循环测试 ──────────────────────────────────

class TestRunCycle:
    """完整进化循环测试。"""

    def test_run_cycle_with_low_quality(self):
        loop = SkillEvolutionLoop(min_feedback_count=3, validation_threshold=0.4)
        for i in range(5):
            loop.collect_feedback(
                execution_id=f"exec-{i:03d}",
                scenario="travel",
                quality_score=0.3,
                model_tier="economy",
            )
        result = loop.run_cycle(scenario="travel")
        assert isinstance(result, EvolutionCycleResult)
        assert result.feedback_collected == 5
        assert result.mutations_generated > 0
        assert result.mutations_validated > 0  # 至少有 tier_change 通过验证

    def test_run_cycle_insufficient_data(self):
        loop = SkillEvolutionLoop(min_feedback_count=10)
        loop.collect_feedback(execution_id="exec-001", scenario="travel", quality_score=0.5)
        result = loop.run_cycle(scenario="travel")
        assert result.mutations_generated == 0

    def test_run_cycle_external_feedbacks(self):
        loop = SkillEvolutionLoop(min_feedback_count=3)
        feedbacks = [
            SkillFeedback(execution_id=f"exec-{i:03d}", scenario="travel", quality_score=0.3, model_tier="economy")
            for i in range(4)
        ]
        result = loop.run_cycle(scenario="travel", feedbacks=feedbacks)
        assert result.feedback_collected == 4


# ── 8. CostTracker 集成测试 ──────────────────────────────────

class TestCostTrackerIntegration:
    """与 DecisionCostTracker 的集成测试。"""

    def test_generate_cost_aware_mutations(self):
        tracker = DecisionCostTracker()
        for i in range(5):
            tracker.track(f"exec-{i:03d}", "travel", token_input=5000, token_output=500, model_tier="premium")

        loop = SkillEvolutionLoop(cost_tracker=tracker)
        mutations = loop.generate_cost_aware_mutations("travel")
        assert len(mutations) > 0

    def test_generate_cost_aware_mutations_no_tracker(self):
        loop = SkillEvolutionLoop()
        mutations = loop.generate_cost_aware_mutations("travel")
        assert len(mutations) == 0

    def test_get_mutations_filter(self):
        loop = SkillEvolutionLoop(min_feedback_count=3)
        for i in range(4):
            loop.collect_feedback(
                execution_id=f"exec-{i:03d}",
                scenario="travel",
                quality_score=0.3,
                model_tier="economy",
            )
        loop.learn()
        all_mutations = loop.get_mutations()
        travel_mutations = loop.get_mutations(scenario="travel")
        assert len(travel_mutations) <= len(all_mutations)


# ── 9. 满意度维度测试 ──────────────────────────────────────────

class TestSatisfactionDimension:
    """满意度维度的变更建议测试。"""

    def test_low_satisfaction_triggers_improvement(self):
        loop = SkillEvolutionLoop(min_feedback_count=3)
        for i in range(4):
            loop.collect_feedback(
                execution_id=f"exec-{i:03d}",
                scenario="travel",
                quality_score=0.7,
                user_satisfaction=2.0,
            )
        mutations = loop.learn()
        sat_mutations = [m for m in mutations if "满意度" in m.description]
        assert len(sat_mutations) > 0

    def test_high_satisfaction_no_action(self):
        loop = SkillEvolutionLoop(min_feedback_count=3)
        for i in range(4):
            loop.collect_feedback(
                execution_id=f"exec-{i:03d}",
                scenario="travel",
                quality_score=0.9,
                user_satisfaction=4.5,
                token_cost=0.2,
                latency_ms=500.0,
            )
        mutations = loop.learn()
        # 高质量+高满意度+低成本 → 不应有变更
        assert len(mutations) == 0
