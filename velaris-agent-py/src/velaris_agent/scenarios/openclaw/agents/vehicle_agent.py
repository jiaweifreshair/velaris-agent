"""车端智能体 - 接收 IntentOrder, 评估能力, 生成 ServiceProposal。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from math import sqrt

from pydantic import BaseModel, Field

from velaris_agent.scenarios.openclaw.protocol.intent_order import IntentOrder, Location
from velaris_agent.scenarios.openclaw.protocol.service_proposal import (
    AddOnService,
    CommitmentBoundaries,
    DriverProfile,
    ETA,
    Pricing,
    ServiceProposal,
    VehicleProfile,
)


class VehicleCapabilities(BaseModel):
    """车辆能力描述。"""

    vehicle_id: str = Field(description="车辆 ID")
    vehicle_profile: VehicleProfile = Field(description="车辆画像")
    driver_profile: DriverProfile = Field(description="司机画像")
    current_location: Location = Field(description="当前位置")
    available: bool = Field(default=True, description="是否可用")
    add_on_services: list[AddOnService] = Field(
        default_factory=list, description="可提供的附加服务"
    )
    operating_area: list[str] = Field(
        default_factory=list, description="运营区域"
    )
    # 简化定价: 每公里单价
    price_per_km: float = Field(default=2.5, description="每公里单价 (CNY)")
    # 简化速度: km/min
    speed_km_per_min: float = Field(default=0.5, description="平均速度 (km/min)")


def _flat_distance_km(a: Location, b: Location) -> float:
    """平面近似距离 (城市内短距离)。"""
    dlat = abs(b.lat - a.lat) * 111.0
    dlng = abs(b.lng - a.lng) * 111.0 * 0.85
    return sqrt(dlat ** 2 + dlng ** 2)


class VehicleAgent:
    """车端智能体。

    接收意图订单, 评估自身能力, 决定是否接单, 生成服务提案。
    """

    def __init__(self, capabilities: VehicleCapabilities) -> None:
        """初始化车端 agent。"""
        self._cap = capabilities

    @property
    def vehicle_id(self) -> str:
        """车辆 ID。"""
        return self._cap.vehicle_id

    async def evaluate_order(self, order: IntentOrder) -> ServiceProposal | None:
        """评估是否能接单, 生成服务提案。返回 None 表示拒单。"""
        if not self._cap.available:
            return None

        # 检查硬约束: 轮椅
        if (
            order.constraints.wheelchair
            and "accessible" not in self._cap.vehicle_profile.features
        ):
            return None

        # 检查容量
        total_passengers = 1 + order.constraints.children + order.constraints.elderly
        if total_passengers > self._cap.vehicle_profile.capacity:
            return None

        # 计算 ETA
        pickup_distance = _flat_distance_km(self._cap.current_location, order.origin)
        eta_minutes = pickup_distance / max(self._cap.speed_km_per_min, 0.1)

        # 超过 30 分钟不接单
        if eta_minutes > 30:
            return None

        # 计算价格
        trip_distance = _flat_distance_km(order.origin, order.destination)
        base_price = round(trip_distance * self._cap.price_per_km, 2)

        # 超出预算不接单
        if base_price > order.budget.max_price:
            return None

        # 计算任务理解度
        task_score = self._assess_task_understanding(order)

        # 匹配附加服务
        matched_add_ons = self._match_add_ons(order)

        return ServiceProposal(
            proposal_id=f"prop-{uuid.uuid4().hex[:12]}",
            vehicle_id=self._cap.vehicle_id,
            order_id=order.order_id,
            eta=ETA(
                minutes=round(eta_minutes, 1),
                confidence=0.85 if eta_minutes < 15 else 0.7,
            ),
            pricing=Pricing(
                base_price=base_price,
                total_price=base_price,
                currency=order.budget.currency,
            ),
            driver=self._cap.driver_profile,
            vehicle=self._cap.vehicle_profile,
            add_on_services=matched_add_ons,
            task_understanding_score=task_score,
            historical_fulfillment_score=min(
                self._cap.driver_profile.rating / 5.0, 1.0
            ),
            commitment_boundaries=CommitmentBoundaries(
                max_wait_minutes=10,
                cancellation_policy="free_5min",
                risk_notes=[],
            ),
            created_at=datetime.now(timezone.utc),
        )

    def _assess_task_understanding(self, order: IntentOrder) -> float:
        """评估任务理解度 0-1。"""
        score = 0.6  # 基础分

        # 车型匹配
        pref = order.service_preferences.vehicle_type
        features = self._cap.vehicle_profile.features
        if pref == "economy":
            score += 0.1
        elif pref == "premium" and "premium" in features:
            score += 0.15
        elif pref == "accessible" and "accessible" in features:
            score += 0.2

        # 司机风格匹配
        if (
            order.service_preferences.driver_style
            and self._cap.driver_profile.style == order.service_preferences.driver_style
        ):
            score += 0.15

        # 附加服务满足
        if order.additional_services:
            available = {s.name for s in self._cap.add_on_services}
            matched = sum(1 for s in order.additional_services if s in available)
            score += 0.1 * (matched / len(order.additional_services))

        return min(score, 1.0)

    def _match_add_ons(self, order: IntentOrder) -> list[AddOnService]:
        """匹配附加服务。"""
        if not order.additional_services:
            return []
        requested = set(order.additional_services)
        return [s for s in self._cap.add_on_services if s.name in requested]
