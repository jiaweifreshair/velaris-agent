"""DynamicRouter — token 成本 + SLA + 合规感知的动态路由器。

在 PolicyRouter 基础上增加四层动态调整：
1. Base：PolicyRouter 基础规则匹配（保留向后兼容）
2. Cost：token 成本优化（低预算时降级到 L0/L1 模型）
3. SLA：延迟感知（高延迟需求路由到快速模型）
4. Compliance：本地合规感知（AI Localism：数据不出境）

设计原则：
- 完全向后兼容：未提供 RoutingContext 时行为与 PolicyRouter 一致
- 渐进式增强：每层调整独立，可单独开启/关闭
- 可观测性：每层调整都记录 trace，便于审计
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from velaris_agent.velaris.router import PolicyRouter, RoutingDecision, SelectedRoute


# ── 模型等级 ────────────────────────────────────────────────

class ModelTier(str, Enum):
    """模型等级，对应不同成本和延迟。"""

    PREMIUM = "premium"    # 高成本、高质量（如 GPT-4o, Claude Opus）
    STANDARD = "standard"  # 标准成本（如 GPT-4o-mini, Claude Sonnet）
    ECONOMY = "economy"    # 低成本、快速（如 GPT-3.5, Claude Haiku）

    @property
    def relative_cost(self) -> float:
        """相对成本倍率。"""
        return {ModelTier.PREMIUM: 1.0, ModelTier.STANDARD: 0.3, ModelTier.ECONOMY: 0.05}[self]


class ComplianceRegion(str, Enum):
    """合规区域。"""

    GLOBAL = "global"          # 无限制
    EU_GDPR = "eu_gdpr"       # 欧盟 GDPR：数据不出境
    CN_PIPC = "cn_pipc"       # 中国个人信息保护法
    LOCAL_ONLY = "local_only"  # 仅本地推理


# ── RoutingContext ──────────────────────────────────────────

@dataclass(frozen=True)
class TokenBudget:
    """Token 预算上下文。"""

    remaining: float          # 剩余预算（token 数量）
    total: float              # 总预算
    cost_rate: float = 1.0    # 当前成本速率（token/请求）

    @property
    def utilization(self) -> float:
        """预算使用率 [0.0, 1.0]。"""
        if self.total <= 0:
            return 1.0
        return 1.0 - (self.remaining / self.total)

    @property
    def is_low(self) -> bool:
        """预算是否不足（使用率 > 80%）。"""
        return self.utilization > 0.8

    @property
    def is_critical(self) -> bool:
        """预算是否严重不足（使用率 > 95%）。"""
        return self.utilization > 0.95


@dataclass(frozen=True)
class SLARequirement:
    """SLA 需求。"""

    max_latency_ms: float | None = None   # 最大延迟要求
    min_quality_score: float | None = None  # 最低质量分要求

    @property
    def requires_low_latency(self) -> bool:
        """是否需要低延迟（< 2000ms）。"""
        return self.max_latency_ms is not None and self.max_latency_ms < 2000


@dataclass(frozen=True)
class ComplianceContext:
    """合规上下文。"""

    region: ComplianceRegion = ComplianceRegion.GLOBAL
    data_classification: str = "internal"   # public / internal / confidential / restricted
    allowed_model_tiers: tuple[ModelTier, ...] = (ModelTier.PREMIUM, ModelTier.STANDARD, ModelTier.ECONOMY)
    requires_local_inference: bool = False   # 是否要求本地推理

    @property
    def is_restricted(self) -> bool:
        """是否有合规限制。"""
        return (
            self.region != ComplianceRegion.GLOBAL
            or self.data_classification in ("confidential", "restricted")
            or self.requires_local_inference
        )


@dataclass(frozen=True)
class RoutingContext:
    """动态路由上下文：成本 + SLA + 合规。"""

    token_budget: TokenBudget | None = None
    sla: SLARequirement | None = None
    compliance: ComplianceContext | None = None
    scenario: str = "general"
    historical_cost_tokens: float = 0.0  # 历史平均 token 消耗


# ── 路由调整层 ──────────────────────────────────────────────

@dataclass(frozen=True)
class AdjustmentTrace:
    """单层路由调整记录。"""

    layer: str                      # 调整层名称
    adjusted: bool                  # 是否做了调整
    reason: str                     # 调整原因
    before: dict[str, Any] = field(default_factory=dict)  # 调整前
    after: dict[str, Any] = field(default_factory=dict)    # 调整后


@dataclass(frozen=True)
class DynamicRoutingDecision:
    """动态路由决策结果，包含原始决策 + 动态调整。"""

    base_decision: RoutingDecision          # PolicyRouter 原始决策
    final_route: SelectedRoute              # 最终路由（可能被调整）
    model_tier: ModelTier                   # 推荐模型等级
    adjustments: tuple[AdjustmentTrace, ...]  # 各层调整记录
    estimated_token_cost: float             # 预估 token 成本
    compliance_approved: bool               # 合规检查是否通过
    routing_context: RoutingContext | None   # 路由上下文快照

    def to_dict(self) -> dict[str, Any]:
        """转换为 JSON 友好的字典。"""
        return {
            "base_decision": self.base_decision.to_dict(),
            "final_route": asdict(self.final_route),
            "model_tier": self.model_tier.value,
            "adjustments": [asdict(a) for a in self.adjustments],
            "estimated_token_cost": self.estimated_token_cost,
            "compliance_approved": self.compliance_approved,
            "model_tier_cost_rate": self.model_tier.relative_cost,
        }


# ── DynamicRouter ───────────────────────────────────────────

class DynamicRouter:
    """token 成本 + SLA + 合规感知的动态路由器。

    使用方式：
    1. 直接替代 PolicyRouter：router = DynamicRouter(policy_path)
    2. 包装已有 PolicyRouter：router = DynamicRouter(base_router=existing_router)

    四层路由调整：
    - Base：PolicyRouter 基础规则匹配（保留向后兼容）
    - Cost：token 成本优化（低预算时降级模型）
    - SLA：延迟感知（低延迟需求路由到快速模型）
    - Compliance：本地合规感知（数据不出境限制）
    """

    def __init__(
        self,
        policy_path: str | None = None,
        base_router: PolicyRouter | None = None,
        scenario_registry: Any | None = None,
    ) -> None:
        if base_router is not None:
            self._base_router = base_router
        else:
            self._base_router = PolicyRouter(
                policy_path=policy_path,
                scenario_registry=scenario_registry,
            )

    def route(
        self,
        plan: dict[str, Any],
        query: str,
        context: RoutingContext | None = None,
    ) -> DynamicRoutingDecision:
        """执行四层动态路由。

        Args:
            plan: 能力规划字典
            query: 用户查询
            context: 动态路由上下文（None 时等价于 PolicyRouter）

        Returns:
            DynamicRoutingDecision 包含原始决策 + 动态调整
        """
        # Layer 1: Base — PolicyRouter 基础路由
        base_decision = self._base_router.route(plan, query)
        adjustments: list[AdjustmentTrace] = []

        # 无动态上下文时，直接返回原始决策
        if context is None:
            return DynamicRoutingDecision(
                base_decision=base_decision,
                final_route=base_decision.selected_route,
                model_tier=ModelTier.STANDARD,
                adjustments=(),
                estimated_token_cost=0.0,
                compliance_approved=True,
                routing_context=None,
            )

        # 初始状态
        current_route = base_decision.selected_route
        current_tier = self._infer_default_tier(base_decision)
        estimated_cost = self._estimate_token_cost(current_tier, context)

        # Layer 2: Cost — token 成本优化
        current_route, current_tier, estimated_cost, cost_adj = self._adjust_for_cost(
            current_route, current_tier, estimated_cost, context,
        )
        adjustments.append(cost_adj)

        # Layer 3: SLA — 延迟感知
        current_route, current_tier, estimated_cost, sla_adj = self._adjust_for_sla(
            current_route, current_tier, estimated_cost, context,
        )
        adjustments.append(sla_adj)

        # Layer 4: Compliance — 合规感知
        current_route, current_tier, compliance_ok, compliance_adj = self._adjust_for_compliance(
            current_route, current_tier, context,
        )
        adjustments.append(compliance_adj)

        return DynamicRoutingDecision(
            base_decision=base_decision,
            final_route=current_route,
            model_tier=current_tier,
            adjustments=tuple(adjustments),
            estimated_token_cost=estimated_cost,
            compliance_approved=compliance_ok,
            routing_context=context,
        )

    # ── Layer 2: Cost 调整 ──────────────────────────────────

    def _adjust_for_cost(
        self,
        route: SelectedRoute,
        tier: ModelTier,
        estimated_cost: float,
        context: RoutingContext,
    ) -> tuple[SelectedRoute, ModelTier, float, AdjustmentTrace]:
        """token 成本优化：低预算时降级模型。"""
        budget = context.token_budget
        if budget is None:
            return route, tier, estimated_cost, AdjustmentTrace(
                layer="cost", adjusted=False, reason="no_budget_info",
            )

        before = {"tier": tier.value, "estimated_cost": estimated_cost}
        new_tier = tier
        reason = "within_budget"

        if budget.is_critical:
            # 严重不足：强制降级到 Economy
            new_tier = ModelTier.ECONOMY
            reason = "budget_critical_force_economy"
        elif budget.is_low:
            # 预算紧张：降级到 Standard（如果当前是 Premium）
            if tier == ModelTier.PREMIUM:
                new_tier = ModelTier.STANDARD
                reason = "budget_low_downgrade_to_standard"
            # Standard 不再降级，避免过度节省影响质量
        else:
            # 预算充足：无调整
            pass

        new_cost = self._estimate_token_cost(new_tier, context)
        adjusted = new_tier != tier
        after = {"tier": new_tier.value, "estimated_cost": new_cost}

        return route, new_tier, new_cost, AdjustmentTrace(
            layer="cost",
            adjusted=adjusted,
            reason=reason,
            before=before,
            after=after,
        )

    # ── Layer 3: SLA 调整 ───────────────────────────────────

    def _adjust_for_sla(
        self,
        route: SelectedRoute,
        tier: ModelTier,
        estimated_cost: float,
        context: RoutingContext,
    ) -> tuple[SelectedRoute, ModelTier, float, AdjustmentTrace]:
        """SLA 感知：低延迟需求路由到快速模型。"""
        sla = context.sla
        if sla is None:
            return route, tier, estimated_cost, AdjustmentTrace(
                layer="sla", adjusted=False, reason="no_sla_info",
            )

        before = {"tier": tier.value}
        new_tier = tier
        reason = "sla_satisfied"

        if sla.requires_low_latency and tier == ModelTier.PREMIUM:
            # 低延迟 + Premium → Standard（Sonnet/Haiku 通常比 Opus 快）
            new_tier = ModelTier.STANDARD
            reason = "low_latency_downgrade_to_standard"
        elif sla.requires_low_latency and tier == ModelTier.STANDARD:
            # 已经 Standard，保持（Economy 可能质量不够）
            reason = "low_latency_standard_sufficient"

        adjusted = new_tier != tier
        after = {"tier": new_tier.value}
        new_cost = self._estimate_token_cost(new_tier, context)

        return route, new_tier, new_cost, AdjustmentTrace(
            layer="sla",
            adjusted=adjusted,
            reason=reason,
            before=before,
            after=after,
        )

    # ── Layer 4: Compliance 调整 ─────────────────────────────

    def _adjust_for_compliance(
        self,
        route: SelectedRoute,
        tier: ModelTier,
        context: RoutingContext,
    ) -> tuple[SelectedRoute, ModelTier, bool, AdjustmentTrace]:
        """合规感知：检查模型等级是否在允许范围内。"""
        compliance = context.compliance
        if compliance is None:
            return route, tier, True, AdjustmentTrace(
                layer="compliance", adjusted=False, reason="no_compliance_info",
            )

        before = {"tier": tier.value, "compliance_approved": True}
        new_tier = tier
        compliance_ok = True
        reason = "compliance_satisfied"

        if compliance.is_restricted:
            if tier not in compliance.allowed_model_tiers:
                # 降级到最高允许的等级
                for allowed_tier in [ModelTier.PREMIUM, ModelTier.STANDARD, ModelTier.ECONOMY]:
                    if allowed_tier in compliance.allowed_model_tiers:
                        new_tier = allowed_tier
                        break
                else:
                    # 没有任何允许的等级
                    compliance_ok = False
                    new_tier = ModelTier.ECONOMY
                    reason = "no_allowed_tier_compliance_blocked"
                if compliance_ok:
                    reason = f"compliance_downgrade_to_{new_tier.value}"

            # 本地推理要求：不允许 delegated 模式
            if compliance.requires_local_inference and route.mode == "delegated":
                # 强制切换到本地模式
                new_route = SelectedRoute(
                    mode="local",
                    runtime=route.runtime,
                    autonomy=route.autonomy,
                    score=route.score,
                )
                reason = "local_inference_force_local_mode"
                adjusted = True
                after = {"tier": new_tier.value, "compliance_approved": compliance_ok}
                return new_route, new_tier, compliance_ok, AdjustmentTrace(
                    layer="compliance",
                    adjusted=adjusted,
                    reason=reason,
                    before=before,
                    after=after,
                )

        adjusted = new_tier != tier
        after = {"tier": new_tier.value, "compliance_approved": compliance_ok}

        return route, new_tier, compliance_ok, AdjustmentTrace(
            layer="compliance",
            adjusted=adjusted,
            reason=reason,
            before=before,
            after=after,
        )

    # ── 辅助方法 ─────────────────────────────────────────────

    def _infer_default_tier(self, decision: RoutingDecision) -> ModelTier:
        """从路由决策推断默认模型等级。"""
        strategy = decision.selected_strategy
        # 高自主权/审计场景使用 Premium
        if "audit" in strategy or decision.selected_route.autonomy == "supervised":
            return ModelTier.PREMIUM
        # 简单本地闭环使用 Economy
        if strategy == "local_closed_loop" and decision.selected_route.autonomy == "auto":
            return ModelTier.ECONOMY
        # 其他场景使用 Standard
        return ModelTier.STANDARD

    def _estimate_token_cost(self, tier: ModelTier, context: RoutingContext) -> float:
        """根据模型等级和场景估算 token 消耗。"""
        base_cost = context.historical_cost_tokens if context.historical_cost_tokens > 0 else 1000.0
        return base_cost * tier.relative_cost

    @property
    def base_router(self) -> PolicyRouter:
        """获取底层 PolicyRouter，便于向后兼容访问。"""
        return self._base_router
