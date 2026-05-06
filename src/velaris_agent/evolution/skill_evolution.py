"""SkillEvolutionLoop — Skill 自进化循环：反馈→学习→验证→部署。

核心思想：
- 从决策执行结果中收集反馈（成本、质量、满意度）；
- 学习出可应用的 Skill 变更（权重调整、工具增删、参数优化）；
- 验证变更是否安全且有效（A/B 思路，不破坏现有行为）；
- 部署通过验证的变更到 SKILL.md 或运行时配置。

与 SelfEvolutionEngine 的关系：
- SelfEvolutionEngine 负责"回顾+建议"（报告型）；
- SkillEvolutionLoop 负责"闭环进化"（执行型），将建议转化为实际变更。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from velaris_agent.evolution.types import EvolutionAction, SelfEvolutionReport
from velaris_agent.velaris.cost_tracker import CostRecord, DecisionCostTracker, ROIReport


# ── 数据模型 ────────────────────────────────────────────────

class SkillFeedback(BaseModel):
    """Skill 反馈数据。"""

    feedback_id: str = Field(default_factory=lambda: uuid4().hex[:12], description="反馈 ID")
    execution_id: str = Field(description="关联执行 ID")
    scenario: str = Field(description="场景名")
    quality_score: float = Field(ge=0.0, le=1.0, description="质量评分 [0,1]")
    user_satisfaction: float | None = Field(default=None, ge=0.0, le=5.0, description="用户满意度 [0,5]")
    token_cost: float = Field(default=0.0, description="token 成本")
    latency_ms: float = Field(default=0.0, description="延迟 ms")
    model_tier: str = Field(default="standard", description="使用的模型等级")
    metadata: dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat(), description="时间戳")


class SkillMutation(BaseModel):
    """Skill 变更建议。"""

    mutation_id: str = Field(default_factory=lambda: uuid4().hex[:12], description="变更 ID")
    scenario: str = Field(description="目标场景")
    mutation_type: str = Field(description="变更类型：weight_adjust / tool_add / tool_remove / param_tune / tier_change")
    description: str = Field(description="变更描述")
    before: dict[str, Any] = Field(default_factory=dict, description="变更前状态")
    after: dict[str, Any] = Field(default_factory=dict, description="变更后状态")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="变更置信度")
    source_feedback_ids: list[str] = Field(default_factory=list, description="来源反馈 IDs")
    validated: bool = Field(default=False, description="是否已通过验证")
    deployed: bool = Field(default=False, description="是否已部署")
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat(), description="创建时间")


class EvolutionCycleResult(BaseModel):
    """一次完整进化循环的结果。"""

    cycle_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    scenario: str = Field(description="场景名")
    feedback_collected: int = Field(description="收集的反馈数量")
    mutations_generated: int = Field(description="生成的变更数量")
    mutations_validated: int = Field(description="通过验证的变更数量")
    mutations_deployed: int = Field(description="部署的变更数量")
    details: list[SkillMutation] = Field(default_factory=list, description="变更详情")
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# ── SkillEvolutionLoop ───────────────────────────────────────

class SkillEvolutionLoop:
    """Skill 自进化循环：反馈→学习→验证→部署。

    使用方式：
    1. 创建循环：loop = SkillEvolutionLoop(cost_tracker=tracker)
    2. 收集反馈：feedback = loop.collect_feedback(execution_id, ...)
    3. 学习变更：mutations = loop.learn([feedback1, feedback2, ...])
    4. 验证变更：passed = loop.validate(mutation)
    5. 部署变更：loop.deploy(mutation)
    6. 一次性执行：result = loop.run_cycle(scenario, feedbacks)

    设计原则：
    - 每步独立，可单独调用或组合为完整循环
    - 验证是安全屏障：未通过验证的变更不部署
    - 部署是幂等的：重复部署同一变更无副作用
    """

    def __init__(
        self,
        cost_tracker: DecisionCostTracker | None = None,
        persistence_dir: str | Path | None = None,
        *,
        validation_threshold: float = 0.6,
        min_feedback_count: int = 3,
    ) -> None:
        """初始化 Skill 进化循环。

        Args:
            cost_tracker: 决策成本追踪器（可选）
            persistence_dir: 持久化目录（可选，None 则不持久化）
            validation_threshold: 变更验证通过阈值（置信度 >= 此值才通过）
            min_feedback_count: 最少反馈数量（少于此数不生成变更）
        """
        self._cost_tracker = cost_tracker
        self._validation_threshold = validation_threshold
        self._min_feedback_count = min_feedback_count
        self._feedbacks: list[SkillFeedback] = []
        self._mutations: list[SkillMutation] = []

        if persistence_dir is not None:
            self._persistence_dir = Path(persistence_dir)
        else:
            self._persistence_dir = None

    # ── Step 1: 收集反馈 ────────────────────────────────────

    def collect_feedback(
        self,
        execution_id: str,
        scenario: str,
        quality_score: float,
        token_cost: float = 0.0,
        latency_ms: float = 0.0,
        model_tier: str = "standard",
        user_satisfaction: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SkillFeedback:
        """从执行结果中收集反馈。

        Args:
            execution_id: 执行 ID
            scenario: 场景名
            quality_score: 质量评分 [0,1]
            token_cost: token 成本
            latency_ms: 延迟 ms
            model_tier: 模型等级
            user_satisfaction: 用户满意度
            metadata: 额外元数据

        Returns:
            SkillFeedback 反馈记录
        """
        # 先 clamp 再构造，避免 Pydantic 验证失败
        clamped_quality = max(0.0, min(1.0, quality_score))
        clamped_satisfaction = None
        if user_satisfaction is not None:
            clamped_satisfaction = max(0.0, min(5.0, user_satisfaction))

        feedback = SkillFeedback(
            execution_id=execution_id,
            scenario=scenario,
            quality_score=clamped_quality,
            token_cost=token_cost,
            latency_ms=latency_ms,
            model_tier=model_tier,
            user_satisfaction=clamped_satisfaction,
            metadata=metadata or {},
        )
        self._feedbacks.append(feedback)
        self._persist_feedback(feedback)
        return feedback

    def collect_from_cost_record(self, record: CostRecord, quality_score: float) -> SkillFeedback:
        """从 CostRecord 自动构建反馈。

        Args:
            record: 决策成本记录
            quality_score: 质量评分

        Returns:
            SkillFeedback 反馈记录
        """
        return self.collect_feedback(
            execution_id=record.execution_id,
            scenario=record.scenario,
            quality_score=quality_score,
            token_cost=record.cost_estimate,
            latency_ms=record.latency_ms,
            model_tier=record.model_tier,
            metadata=record.metadata,
        )

    # ── Step 2: 学习 ────────────────────────────────────────

    def learn(
        self,
        feedbacks: list[SkillFeedback] | None = None,
        scenario: str | None = None,
    ) -> list[SkillMutation]:
        """从反馈中学习变更建议。

        学习规则：
        1. 质量低 → 权重调整或模型升级
        2. 成本高 → 降级模型或简化流程
        3. 延迟高 → 简化上下文或降级模型
        4. 满意度高 + 成本低 → 巩固当前策略

        Args:
            feedbacks: 反馈列表（None 则使用内部累积）
            scenario: 过滤特定场景

        Returns:
            变更建议列表
        """
        if feedbacks is None:
            feedbacks = self._feedbacks

        # 按场景过滤
        if scenario is not None:
            feedbacks = [f for f in feedbacks if f.scenario == scenario]

        # 按场景分组
        groups: dict[str, list[SkillFeedback]] = {}
        for f in feedbacks:
            groups.setdefault(f.scenario, []).append(f)

        mutations: list[SkillMutation] = []
        for sc, group in groups.items():
            if len(group) < self._min_feedback_count:
                continue
            mutations.extend(self._analyze_group(sc, group))

        self._mutations.extend(mutations)
        return mutations

    def _analyze_group(self, scenario: str, feedbacks: list[SkillFeedback]) -> list[SkillMutation]:
        """分析一组同场景反馈，生成变更建议。"""
        mutations: list[SkillMutation] = []
        feedback_ids = [f.feedback_id for f in feedbacks]

        avg_quality = sum(f.quality_score for f in feedbacks) / len(feedbacks)
        avg_cost = sum(f.token_cost for f in feedbacks) / len(feedbacks)
        avg_latency = sum(f.latency_ms for f in feedbacks) / len(feedbacks)

        tier_counts: dict[str, int] = {}
        for f in feedbacks:
            tier_counts[f.model_tier] = tier_counts.get(f.model_tier, 0) + 1
        dominant_tier = max(tier_counts, key=tier_counts.get)  # type: ignore[arg-type]

        # 规则1：质量低 → 建议升级模型或调整权重
        if avg_quality < 0.5:
            if dominant_tier == "economy":
                mutations.append(SkillMutation(
                    scenario=scenario,
                    mutation_type="tier_change",
                    description=f"平均质量偏低({avg_quality:.2f})，建议从 economy 升级到 standard",
                    before={"model_tier": "economy"},
                    after={"model_tier": "standard"},
                    confidence=min(0.9, 0.5 + (0.5 - avg_quality)),
                    source_feedback_ids=feedback_ids,
                ))
            elif dominant_tier == "standard":
                mutations.append(SkillMutation(
                    scenario=scenario,
                    mutation_type="tier_change",
                    description=f"平均质量偏低({avg_quality:.2f})，考虑升级到 premium",
                    before={"model_tier": "standard"},
                    after={"model_tier": "premium"},
                    confidence=min(0.7, 0.4 + (0.5 - avg_quality)),
                    source_feedback_ids=feedback_ids,
                ))
            # 质量低 + 不降级 → 尝试权重调整
            mutations.append(SkillMutation(
                scenario=scenario,
                mutation_type="weight_adjust",
                description=f"质量持续偏低({avg_quality:.2f})，建议调整评分权重以改善推荐质量",
                before={"avg_quality": avg_quality},
                after={"target_quality": 0.6},
                confidence=min(0.6, 0.3 + (0.5 - avg_quality) * 0.5),
                source_feedback_ids=feedback_ids,
            ))

        # 规则2：成本高 + 质量尚可 → 降级建议
        if avg_cost > 2.0 and avg_quality >= 0.6:
            target_tier = "economy" if dominant_tier == "standard" else "standard"
            mutations.append(SkillMutation(
                scenario=scenario,
                mutation_type="tier_change",
                description=f"成本偏高(均值{avg_cost:.2f})但质量尚可({avg_quality:.2f})，建议降级到{target_tier}",
                before={"model_tier": dominant_tier, "avg_cost": avg_cost},
                after={"model_tier": target_tier},
                confidence=0.6,
                source_feedback_ids=feedback_ids,
            ))

        # 规则3：延迟高 → 简化上下文或降级
        if avg_latency > 5000.0:
            mutations.append(SkillMutation(
                scenario=scenario,
                mutation_type="param_tune",
                description=f"平均延迟过高({avg_latency:.0f}ms)，建议使用 L0/L1 上下文替代 L2",
                before={"loading_tier": "L2", "avg_latency_ms": avg_latency},
                after={"loading_tier": "L1"},
                confidence=0.65,
                source_feedback_ids=feedback_ids,
            ))

        # 规则4：满意度低 → 优化解释质量
        satisfactions = [f.user_satisfaction for f in feedbacks if f.user_satisfaction is not None]
        if satisfactions:
            avg_sat = sum(satisfactions) / len(satisfactions)
            if avg_sat < 3.0:
                mutations.append(SkillMutation(
                    scenario=scenario,
                    mutation_type="param_tune",
                    description=f"用户满意度偏低({avg_sat:.1f}/5)，建议优化推荐解释和 trade-off 披露",
                    before={"avg_satisfaction": avg_sat},
                    after={"target_satisfaction": 3.5},
                    confidence=0.55,
                    source_feedback_ids=feedback_ids,
                ))

        return mutations

    # ── Step 3: 验证 ─────────────────────────────────────────

    def validate(self, mutation: SkillMutation) -> bool:
        """验证变更是否安全且有效。

        验证规则：
        1. 置信度检查：confidence >= validation_threshold
        2. 安全检查：不引入高风险操作（如删除关键工具）
        3. 一致性检查：变更前后状态合理

        Args:
            mutation: 变更建议

        Returns:
            是否通过验证
        """
        # 规则1：置信度门槛
        if mutation.confidence < self._validation_threshold:
            return False

        # 规则2：安全检查 - 拒绝高风险操作
        if mutation.mutation_type == "tool_remove":
            # 工具删除需高置信度
            if mutation.confidence < 0.8:
                return False

        # 规则3：一致性检查 - 变更前后不能完全相同
        if mutation.before == mutation.after:
            return False

        # 规则4：tier_change 不允许从 premium 直降 economy
        if mutation.mutation_type == "tier_change":
            before_tier = mutation.before.get("model_tier", "")
            after_tier = mutation.after.get("model_tier", "")
            if before_tier == "premium" and after_tier == "economy":
                return False  # 禁止跨级降级

        # 标记为已验证
        mutation.validated = True
        return True

    # ── Step 4: 部署 ──────────────────────────────────────────

    def deploy(self, mutation: SkillMutation) -> bool:
        """部署通过验证的变更。

        部署规则：
        1. 未验证的变更不部署
        2. 已部署的变更幂等返回 True
        3. 持久化部署记录

        Args:
            mutation: 变更建议

        Returns:
            是否部署成功
        """
        if not mutation.validated:
            return False

        if mutation.deployed:
            return True  # 幂等

        # 标记为已部署
        mutation.deployed = True
        self._persist_mutation(mutation)
        return True

    # ── 完整循环 ─────────────────────────────────────────────

    def run_cycle(
        self,
        scenario: str,
        feedbacks: list[SkillFeedback] | None = None,
    ) -> EvolutionCycleResult:
        """执行一次完整的进化循环：收集→学习→验证→部署。

        Args:
            scenario: 目标场景
            feedbacks: 反馈列表（None 则使用内部累积）

        Returns:
            EvolutionCycleResult 循环结果
        """
        if feedbacks is None:
            feedbacks = [f for f in self._feedbacks if f.scenario == scenario]

        # Step 2: 学习
        mutations = self.learn(feedbacks=feedbacks, scenario=scenario)

        # Step 3: 验证
        for m in mutations:
            self.validate(m)
        validated = [m for m in mutations if m.validated]

        # Step 4: 部署
        deployed_count = 0
        for m in validated:
            if self.deploy(m):
                deployed_count += 1

        return EvolutionCycleResult(
            scenario=scenario,
            feedback_collected=len(feedbacks),
            mutations_generated=len(mutations),
            mutations_validated=len(validated),
            mutations_deployed=deployed_count,
            details=mutations,
        )

    # ── 查询接口 ─────────────────────────────────────────────

    def get_feedbacks(self, scenario: str | None = None) -> list[SkillFeedback]:
        """获取累积的反馈。"""
        if scenario is None:
            return list(self._feedbacks)
        return [f for f in self._feedbacks if f.scenario == scenario]

    def get_mutations(
        self,
        scenario: str | None = None,
        deployed_only: bool = False,
    ) -> list[SkillMutation]:
        """获取变更建议。"""
        result = self._mutations
        if scenario is not None:
            result = [m for m in result if m.scenario == scenario]
        if deployed_only:
            result = [m for m in result if m.deployed]
        return result

    # ── 持久化 ────────────────────────────────────────────────

    def _persist_feedback(self, feedback: SkillFeedback) -> None:
        """持久化反馈记录。"""
        if self._persistence_dir is None:
            return
        fb_dir = self._persistence_dir / "feedbacks"
        fb_dir.mkdir(parents=True, exist_ok=True)
        path = fb_dir / f"{feedback.feedback_id}.json"
        path.write_text(
            json.dumps(feedback.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _persist_mutation(self, mutation: SkillMutation) -> None:
        """持久化部署记录。"""
        if self._persistence_dir is None:
            return
        mt_dir = self._persistence_dir / "mutations"
        mt_dir.mkdir(parents=True, exist_ok=True)
        path = mt_dir / f"{mutation.mutation_id}.json"
        path.write_text(
            json.dumps(mutation.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 与 CostTracker 集成 ──────────────────────────────────

    def generate_cost_aware_mutations(self, scenario: str) -> list[SkillMutation]:
        """从 DecisionCostTracker 的 ROI 数据生成成本感知变更。

        当有 cost_tracker 时，可从 ROI 报告中提取额外优化信号：
        - 成本效率低 → 建议降级或简化
        - 延迟高 → 建议优化上下文层级

        Args:
            scenario: 目标场景

        Returns:
            成本感知变更建议
        """
        if self._cost_tracker is None:
            return []

        roi = self._cost_tracker.roi(scenario=scenario)
        mutations: list[SkillMutation] = []

        # 成本效率低于基线 → 建议优化
        if roi.total_executions > 0 and roi.cost_efficiency < 500.0:
            mutations.append(SkillMutation(
                scenario=scenario,
                mutation_type="param_tune",
                description=f"成本效率偏低({roi.cost_efficiency:.1f})，建议优化 token 使用",
                before={"cost_efficiency": roi.cost_efficiency},
                after={"target_cost_efficiency": 800.0},
                confidence=0.5,
            ))

        # 延迟过高 → 建议降级
        if roi.avg_latency_ms > 3000.0:
            mutations.append(SkillMutation(
                scenario=scenario,
                mutation_type="param_tune",
                description=f"平均延迟偏高({roi.avg_latency_ms:.0f}ms)，建议使用轻量上下文",
                before={"avg_latency_ms": roi.avg_latency_ms},
                after={"target_latency_ms": 2000.0},
                confidence=0.55,
            ))

        return mutations
