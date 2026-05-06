"""CostOptimizer — Token 成本优化器。

提供三个核心能力：
1. optimize_loading_tier(): 根据预算决定加载层级 L0/L1/L2
2. recommend_model(): 根据场景复杂度推荐模型等级
3. token_budget_gate(): Token 预算门控（类似 Codex /goal 的 Ralph Loop）

与 DynamicRouter 的关系：
- DynamicRouter 做路由决策时调用 CostOptimizer；
- CostOptimizer 提供静态规则 + 动态预算感知；
- 两者协同实现"预算充足用 L2+Premium，预算紧张降 L0+Economy"。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from velaris_agent.velaris.cost_tracker import DecisionCostTracker


# ── 加载层级 ────────────────────────────────────────────────

class LoadingTier(str, Enum):
    """OpenViking 三层加载策略。"""

    L0_SUMMARY = "L0"    # 快速摘要 < 100tok，用于路由决策
    L1_CONTEXT = "L1"    # 上下文摘要 < 2ktok，用于规划
    L2_FULL = "L2"        # 完整数据，用于执行

    @property
    def estimated_tokens(self) -> float:
        """预估 token 消耗。"""
        return {LoadingTier.L0_SUMMARY: 100.0, LoadingTier.L1_CONTEXT: 2000.0, LoadingTier.L2_FULL: 8000.0}[self]


class ComplexityLevel(str, Enum):
    """场景复杂度等级。"""

    SIMPLE = "simple"          # 简单：单步决策，无合规
    MODERATE = "moderate"      # 中等：多步决策，简单合规
    COMPLEX = "complex"        # 复杂：多步+合规+审计
    CRITICAL = "critical"      # 关键：高风险决策，全量审计


# ── 优化建议 ────────────────────────────────────────────────

@dataclass(frozen=True)
class OptimizationSuggestion:
    """优化建议。"""

    current_tier: str
    recommended_tier: str
    current_model: str
    recommended_model: str
    estimated_savings_pct: float
    quality_impact: str  # "none" / "minimal" / "moderate" / "significant"
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_tier": self.current_tier,
            "recommended_tier": self.recommended_tier,
            "current_model": self.current_model,
            "recommended_model": self.recommended_model,
            "estimated_savings_pct": self.estimated_savings_pct,
            "quality_impact": self.quality_impact,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BudgetGateResult:
    """预算门控结果。"""

    allowed: bool
    remaining_budget: float
    estimated_cost: float
    suggested_tier: str
    suggested_model: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "remaining_budget": self.remaining_budget,
            "estimated_cost": self.estimated_cost,
            "suggested_tier": self.suggested_tier,
            "suggested_model": self.suggested_model,
            "reason": self.reason,
        }


# ── CostOptimizer ──────────────────────────────────────────────

class CostOptimizer:
    """Token 成本优化器。

    使用方式：
    1. 创建优化器：optimizer = CostOptimizer(total_budget=1000000)
    2. 加载层级决策：tier = optimizer.optimize_loading_tier("travel", remaining=5000)
    3. 模型推荐：model = optimizer.recommend_model("travel", "moderate")
    4. 预算门控：gate = optimizer.token_budget_gate(remaining=1000, estimated=2000)
    5. 综合建议：suggestion = optimizer.suggest("travel", "moderate", remaining=5000)

    设计原则：
    - 预算充足时优先保证质量（L2 + premium）
    - 预算紧张时渐进降级（L1 → L0, premium → standard → economy）
    - 关键场景不因预算降级（quality_impact = "significant" 时阻止降级）
    """

    # 场景复杂度映射（可被 ScenarioRegistry 的 SKILL.md 覆盖）
    DEFAULT_COMPLEXITY: dict[str, ComplexityLevel] = {
        "lifegoal": ComplexityLevel.CRITICAL,
        "travel": ComplexityLevel.MODERATE,
        "hotel_biztravel": ComplexityLevel.MODERATE,
        "tokencost": ComplexityLevel.SIMPLE,
        "robotclaw": ComplexityLevel.COMPLEX,
        "procurement": ComplexityLevel.COMPLEX,
        "general": ComplexityLevel.MODERATE,
    }

    # 模型等级 → 成本倍率
    TIER_COST_RATE: dict[str, float] = {
        "premium": 1.0,
        "standard": 0.3,
        "economy": 0.05,
    }

    def __init__(
        self,
        total_budget: float = 0.0,
        cost_tracker: DecisionCostTracker | None = None,
    ) -> None:
        """初始化成本优化器。

        Args:
            total_budget: 总 token 预算（0 表示不限制）
            cost_tracker: 决策成本追踪器（可选，用于历史数据分析）
        """
        self._total_budget = total_budget
        self._cost_tracker = cost_tracker

    # ── 加载层级优化 ─────────────────────────────────────────

    def optimize_loading_tier(
        self,
        scenario: str,
        remaining_budget: float | None = None,
        complexity: ComplexityLevel | None = None,
    ) -> LoadingTier:
        """根据预算和复杂度决定加载层级。

        决策逻辑：
        - 预算 > 50%：根据复杂度选择（simple→L0, moderate→L1, complex/critical→L2）
        - 预算 20%~50%：降一级（L2→L1, L1→L0, L0保持）
        - 预算 < 20%：强制 L0（关键场景除外）
        - 预算 < 5%：强制 L0（即使关键场景也降级，但标记质量影响）

        Args:
            scenario: 场景名
            remaining_budget: 剩余预算
            complexity: 场景复杂度（None 自动推断）

        Returns:
            推荐的加载层级
        """
        if complexity is None:
            complexity = self.DEFAULT_COMPLEXITY.get(scenario, ComplexityLevel.MODERATE)

        # 确定预算比率
        budget_ratio = self._compute_budget_ratio(remaining_budget)

        # 基于复杂度的默认层级
        base_tier = self._complexity_to_tier(complexity)

        # 预算感知降级
        if budget_ratio > 0.5:
            return base_tier
        elif budget_ratio > 0.2:
            return self._downgrade_tier(base_tier, steps=1)
        elif budget_ratio > 0.05:
            # 关键/复杂场景保持 L1
            if complexity in (ComplexityLevel.CRITICAL, ComplexityLevel.COMPLEX):
                return LoadingTier.L1_CONTEXT
            return LoadingTier.L0_SUMMARY
        else:
            # 预算严重不足：关键场景最低保持 L0（但标记降级到 L0 是极限）
            # 非关键场景强制 L0
            return LoadingTier.L0_SUMMARY

    # ── 模型推荐 ─────────────────────────────────────────────

    def recommend_model(
        self,
        scenario: str,
        complexity: ComplexityLevel | str | None = None,
        remaining_budget: float | None = None,
    ) -> str:
        """根据场景复杂度和预算推荐模型等级。

        决策逻辑：
        - critical → premium（预算 > 10%）
        - complex → premium（预算 > 30%）/ standard（预算 10%~30%）
        - moderate → standard（默认）/ economy（预算 < 15%）
        - simple → economy（默认）/ standard（预算充足且需要更好质量）

        Args:
            scenario: 场景名
            complexity: 复杂度（None 自动推断）
            remaining_budget: 剩余预算

        Returns:
            推荐的模型等级名称
        """
        if isinstance(complexity, str):
            complexity = ComplexityLevel(complexity)
        if complexity is None:
            complexity = self.DEFAULT_COMPLEXITY.get(scenario, ComplexityLevel.MODERATE)

        budget_ratio = self._compute_budget_ratio(remaining_budget)

        # 关键场景
        if complexity == ComplexityLevel.CRITICAL:
            if budget_ratio > 0.1:
                return "premium"
            return "standard"  # 最低保障

        # 复杂场景
        if complexity == ComplexityLevel.COMPLEX:
            if budget_ratio > 0.3:
                return "premium"
            if budget_ratio > 0.1:
                return "standard"
            return "economy"

        # 中等场景
        if complexity == ComplexityLevel.MODERATE:
            if budget_ratio > 0.15:
                return "standard"
            return "economy"

        # 简单场景
        if budget_ratio > 0.5:
            return "standard"  # 预算充足时用标准
        return "economy"

    # ── 预算门控 ─────────────────────────────────────────────

    def token_budget_gate(
        self,
        remaining_budget: float,
        estimated_cost: float,
        scenario: str = "general",
        complexity: ComplexityLevel | None = None,
    ) -> BudgetGateResult:
        """Token 预算门控：决定是否允许执行。

        门控规则：
        1. estimated_cost > remaining_budget → 拒绝
        2. estimated_cost > remaining_budget * 0.5 → 允许但建议降级
        3. estimated_cost <= remaining_budget * 0.5 → 允许

        类似 Codex /goal 的 Ralph Loop 机制：
        - 每次执行前检查剩余预算
        - 预算不足时建议降级方案而非直接拒绝
        - 关键场景给予预算宽限（允许超支至 remaining * 1.2）

        Args:
            remaining_budget: 剩余预算
            estimated_cost: 预估成本
            scenario: 场景名
            complexity: 复杂度

        Returns:
            BudgetGateResult 门控结果
        """
        if complexity is None:
            complexity = self.DEFAULT_COMPLEXITY.get(scenario, ComplexityLevel.MODERATE)

        # 关键场景给予预算宽限
        budget_cap = remaining_budget
        if complexity == ComplexityLevel.CRITICAL:
            budget_cap = remaining_budget * 1.2

        # 完全超预算 → 拒绝
        if estimated_cost > budget_cap:
            suggested_tier = self.optimize_loading_tier(scenario, remaining_budget, complexity)
            suggested_model = self.recommend_model(scenario, complexity, remaining_budget)
            return BudgetGateResult(
                allowed=False,
                remaining_budget=remaining_budget,
                estimated_cost=estimated_cost,
                suggested_tier=suggested_tier.value,
                suggested_model=suggested_model,
                reason="estimated_cost_exceeds_remaining_budget",
            )

        # 接近预算上限 → 允许但建议降级
        if estimated_cost > remaining_budget * 0.5:
            suggested_tier = self.optimize_loading_tier(scenario, remaining_budget * 0.5, complexity)
            suggested_model = self.recommend_model(scenario, complexity, remaining_budget * 0.5)
            return BudgetGateResult(
                allowed=True,
                remaining_budget=remaining_budget,
                estimated_cost=estimated_cost,
                suggested_tier=suggested_tier.value,
                suggested_model=suggested_model,
                reason="cost_approaching_budget_limit_suggest_downgrade",
            )

        # 预算充足
        return BudgetGateResult(
            allowed=True,
            remaining_budget=remaining_budget,
            estimated_cost=estimated_cost,
            suggested_tier=self.optimize_loading_tier(scenario, remaining_budget, complexity).value,
            suggested_model=self.recommend_model(scenario, complexity, remaining_budget),
            reason="within_budget",
        )

    # ── 综合建议 ─────────────────────────────────────────────

    def suggest(
        self,
        scenario: str,
        complexity: ComplexityLevel | str | None = None,
        remaining_budget: float | None = None,
        current_tier: str = "L2",
        current_model: str = "standard",
    ) -> OptimizationSuggestion:
        """综合建议：加载层级 + 模型等级。

        Args:
            scenario: 场景名
            complexity: 复杂度
            remaining_budget: 剩余预算
            current_tier: 当前加载层级
            current_model: 当前模型等级

        Returns:
            OptimizationSuggestion 优化建议
        """
        if isinstance(complexity, str):
            complexity = ComplexityLevel(complexity)
        if complexity is None:
            complexity = self.DEFAULT_COMPLEXITY.get(scenario, ComplexityLevel.MODERATE)

        rec_tier = self.optimize_loading_tier(scenario, remaining_budget, complexity)
        rec_model = self.recommend_model(scenario, complexity, remaining_budget)

        # 计算预估节省
        current_cost = LoadingTier(current_tier).estimated_tokens * self.TIER_COST_RATE.get(current_model, 0.3)
        new_cost = rec_tier.estimated_tokens * self.TIER_COST_RATE.get(rec_model, 0.3)
        savings_pct = ((current_cost - new_cost) / current_cost * 100) if current_cost > 0 else 0.0

        # 质量影响评估
        quality_impact = self._assess_quality_impact(current_tier, rec_tier.value, current_model, rec_model)

        # 原因说明
        budget_ratio = self._compute_budget_ratio(remaining_budget)
        if budget_ratio > 0.5:
            reason = "预算充足，按复杂度选择最优配置"
        elif budget_ratio > 0.2:
            reason = "预算偏紧，建议适当降级以延长使用"
        else:
            reason = "预算不足，建议使用经济模式"

        return OptimizationSuggestion(
            current_tier=current_tier,
            recommended_tier=rec_tier.value,
            current_model=current_model,
            recommended_model=rec_model,
            estimated_savings_pct=round(max(0.0, savings_pct), 1),
            quality_impact=quality_impact,
            reason=reason,
        )

    # ── Token Economics 报告 ─────────────────────────────────

    def generate_economics_report(self, scenario: str | None = None) -> dict[str, Any]:
        """生成 Token Economics 报告。

        报告包含：
        - 当前预算状况
        - 各场景成本分布
        - 优化建议
        - ROI 分析

        Args:
            scenario: 场景名（None 全场景）

        Returns:
            报告字典
        """
        report: dict[str, Any] = {
            "generated_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
            "total_budget": self._total_budget,
        }

        if self._cost_tracker is not None:
            # 预算状态
            report["budget_status"] = self._cost_tracker.budget_status().to_dict()

            # 场景成本
            report["cost_by_scenario"] = self._cost_tracker.cost_by_scenario()

            # ROI
            report["roi"] = self._cost_tracker.roi(scenario=scenario).to_dict()

            # 优化建议（每个场景）
            suggestions: list[dict[str, Any]] = []
            for sc_name in (self._cost_tracker.cost_by_scenario() if scenario is None else {scenario: {}}):
                s = self.suggest(sc_name)
                suggestions.append(s.to_dict())
            report["optimization_suggestions"] = suggestions
        else:
            report["budget_status"] = {"total_budget": self._total_budget, "note": "no_cost_tracker"}

        return report

    # ── 辅助方法 ─────────────────────────────────────────────

    def _compute_budget_ratio(self, remaining_budget: float | None) -> float:
        """计算预算比率。"""
        if remaining_budget is not None and self._total_budget > 0:
            return max(0.0, remaining_budget / self._total_budget)
        if remaining_budget is not None and self._total_budget == 0:
            # 显式传入 remaining 但 total 为 0：remaining=0 表示预算耗尽
            return 0.0 if remaining_budget <= 0 else 1.0
        if self._total_budget > 0 and self._cost_tracker is not None:
            status = self._cost_tracker.budget_status()
            return max(0.0, 1.0 - status.utilization)
        # 无预算信息时默认"充足"
        return 1.0

    def _complexity_to_tier(self, complexity: ComplexityLevel) -> LoadingTier:
        """复杂度 → 默认加载层级。"""
        mapping = {
            ComplexityLevel.SIMPLE: LoadingTier.L0_SUMMARY,
            ComplexityLevel.MODERATE: LoadingTier.L1_CONTEXT,
            ComplexityLevel.COMPLEX: LoadingTier.L2_FULL,
            ComplexityLevel.CRITICAL: LoadingTier.L2_FULL,
        }
        return mapping.get(complexity, LoadingTier.L1_CONTEXT)

    def _downgrade_tier(self, tier: LoadingTier, steps: int = 1) -> LoadingTier:
        """降级加载层级。"""
        order = [LoadingTier.L2_FULL, LoadingTier.L1_CONTEXT, LoadingTier.L0_SUMMARY]
        try:
            idx = order.index(tier)
        except ValueError:
            return LoadingTier.L0_SUMMARY
        new_idx = min(idx + steps, len(order) - 1)
        return order[new_idx]

    def _assess_quality_impact(
        self,
        current_tier: str,
        recommended_tier: str,
        current_model: str,
        recommended_model: str,
    ) -> str:
        """评估降级对质量的影响。"""
        tier_order = {"L0": 0, "L1": 1, "L2": 2}
        model_order = {"economy": 0, "standard": 1, "premium": 2}

        tier_delta = tier_order.get(current_tier, 1) - tier_order.get(recommended_tier, 1)
        model_delta = model_order.get(current_model, 1) - model_order.get(recommended_model, 1)
        total_delta = tier_delta + model_delta

        if total_delta <= 0:
            return "none"
        if total_delta == 1:
            return "minimal"
        if total_delta == 2:
            return "moderate"
        return "significant"
