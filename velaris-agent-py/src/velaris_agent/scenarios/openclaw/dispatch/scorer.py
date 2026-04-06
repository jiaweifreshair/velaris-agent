"""多维提案评分器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt

from velaris_agent.scenarios.openclaw.protocol.intent_order import IntentOrder
from velaris_agent.scenarios.openclaw.protocol.service_proposal import ServiceProposal


@dataclass(frozen=True)
class ScoredProposal:
    """带评分的提案。"""

    proposal: ServiceProposal
    score: float
    score_breakdown: dict[str, float] = field(default_factory=dict)


# 默认评分维度权重
DEFAULT_WEIGHTS: dict[str, float] = {
    "price": 0.25,
    "eta": 0.25,
    "task_fit": 0.20,
    "reliability": 0.15,
    "add_on_value": 0.15,
}

# 安全门槛
MIN_SAFETY_SCORE = 0.9
MIN_COMPLIANCE_SCORE = 0.9


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """简化距离计算 (平面近似, 适用于城市内短距离)。"""
    dlat = abs(lat2 - lat1)
    dlng = abs(lng2 - lng1)
    # 1 度纬度 ~ 111km, 1 度经度 ~ 111km * cos(lat)
    km_lat = dlat * 111.0
    km_lng = dlng * 111.0 * 0.85  # 中纬度近似
    return sqrt(km_lat ** 2 + km_lng ** 2)


class ProposalScorer:
    """多维提案评分器。

    评分维度: price(0.25) + eta(0.25) + task_fit(0.20) + reliability(0.15) + add_on_value(0.15)
    """

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        """初始化评分器。"""
        self.weights = weights or dict(DEFAULT_WEIGHTS)

    def score(self, proposal: ServiceProposal, order: IntentOrder) -> ScoredProposal:
        """对单个提案评分。"""
        breakdown = {
            "price": self._score_price(proposal, order),
            "eta": self._score_eta(proposal),
            "task_fit": self._score_task_fit(proposal, order),
            "reliability": self._score_reliability(proposal),
            "add_on_value": self._score_add_on_value(proposal, order),
        }

        total_weight = sum(self.weights.get(k, 0) for k in breakdown)
        if total_weight <= 0:
            total_weight = 1.0

        total_score = sum(
            breakdown[k] * self.weights.get(k, 0) / total_weight
            for k in breakdown
        )

        return ScoredProposal(
            proposal=proposal,
            score=round(total_score, 4),
            score_breakdown=breakdown,
        )

    def score_batch(
        self, proposals: list[ServiceProposal], order: IntentOrder
    ) -> list[ScoredProposal]:
        """批量评分并按总分降序排列。"""
        scored = [self.score(p, order) for p in proposals]
        return sorted(scored, key=lambda s: s.score, reverse=True)

    def _score_price(self, proposal: ServiceProposal, order: IntentOrder) -> float:
        """价格得分: 越接近预算下限越高, 超出预算为 0。"""
        max_price = order.budget.max_price
        if max_price <= 0:
            return 0.5
        total = proposal.pricing.total_price
        if total > max_price:
            return 0.0
        return _clamp(1.0 - total / max_price)

    def _score_eta(self, proposal: ServiceProposal) -> float:
        """ETA 得分: 5分钟内满分, 超过30分钟为0。"""
        minutes = proposal.eta.minutes
        if minutes <= 5:
            return 1.0
        if minutes >= 30:
            return 0.0
        return _clamp((30 - minutes) / 25)

    def _score_task_fit(self, proposal: ServiceProposal, order: IntentOrder) -> float:
        """任务匹配度: 基于 task_understanding_score + 约束满足。"""
        base = proposal.task_understanding_score

        # 轮椅需求但车辆不支持
        if order.constraints.wheelchair and "accessible" not in proposal.vehicle.features:
            return 0.0

        # 行李过多, 小车扣分
        if order.constraints.luggage > 2 and proposal.vehicle.capacity < 4:
            base *= 0.7

        # 儿童需求
        if order.constraints.children > 0 and "child_seat" not in proposal.vehicle.features:
            base *= 0.8

        # 司机风格匹配
        if (
            order.service_preferences.driver_style
            and proposal.driver.style != order.service_preferences.driver_style
        ):
            base *= 0.9

        return _clamp(base)

    def _score_reliability(self, proposal: ServiceProposal) -> float:
        """可靠性: 基于历史履约分。"""
        return _clamp(proposal.historical_fulfillment_score)

    def _score_add_on_value(self, proposal: ServiceProposal, order: IntentOrder) -> float:
        """附加服务价值: 匹配用户请求的附加服务。"""
        if not order.additional_services:
            return 0.5  # 无需求时给中间分
        available_names = {s.name for s in proposal.add_on_services}
        matched = sum(1 for s in order.additional_services if s in available_names)
        return _clamp(matched / len(order.additional_services))


def _clamp(v: float) -> float:
    """夹紧到 [0, 1]。"""
    return max(0.0, min(1.0, v))
