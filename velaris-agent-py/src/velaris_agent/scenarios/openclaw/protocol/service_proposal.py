"""Stage 2: 服务提案 - 车端 agent 返回的结构化投标。

每辆车不是简单抢单, 而是返回结构化提案: ETA、基础价格、司机服务画像、
车内能力、附加服务包、任务理解程度、历史履约分、可承诺边界等。
本质是: 从派单变成 "服务投标"。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ETA(BaseModel):
    """预计到达时间。"""

    minutes: float = Field(ge=0, description="预计到达分钟数")
    confidence: float = Field(ge=0, le=1, description="ETA 置信度")


class PricingItem(BaseModel):
    """价格明细项。"""

    type: str = Field(description="类型: base/distance/time/surge/addon")
    description: str = Field(description="描述")
    amount: float = Field(description="金额")


class Pricing(BaseModel):
    """定价信息。"""

    base_price: float = Field(ge=0, description="基础价格")
    surcharges: list[PricingItem] = Field(
        default_factory=list, description="附加费用"
    )
    total_price: float = Field(ge=0, description="总价")
    currency: str = Field(default="CNY", description="货币")


class DriverProfile(BaseModel):
    """司机画像。"""

    driver_id: str = Field(description="司机 ID")
    rating: float = Field(ge=0, le=5, description="评分")
    completed_trips: int = Field(ge=0, description="完成行程数")
    style: str = Field(description="服务风格: quiet/social/professional")
    languages: list[str] = Field(default_factory=lambda: ["zh"], description="语言")
    years_experience: int | None = Field(default=None, description="驾龄")


class VehicleProfile(BaseModel):
    """车辆画像。"""

    model: str = Field(description="车型, 如 'Tesla Model 3'")
    year: int = Field(description="年份")
    capacity: int = Field(ge=1, description="乘客容量")
    features: list[str] = Field(
        default_factory=list,
        description="特性, 如 ['ev', 'autopilot', 'wifi', 'air_purifier']",
    )
    license_plate: str | None = Field(default=None, description="车牌号")


class AddOnService(BaseModel):
    """附加服务。"""

    service_id: str = Field(description="服务 ID")
    name: str = Field(description="服务名称")
    price: float = Field(ge=0, description="价格")
    description: str = Field(description="描述")


class CommitmentBoundaries(BaseModel):
    """可承诺边界。"""

    max_wait_minutes: int = Field(ge=0, description="最大等待分钟数")
    cancellation_policy: str = Field(
        description="取消规则, 如 'free_5min', 'charge_after_3min'"
    )
    risk_notes: list[str] = Field(
        default_factory=list, description="风险说明"
    )


class ServiceProposal(BaseModel):
    """服务提案 - 车端 agent 返回的结构化投标。

    从 "抢单" 升级为 "服务投标"。
    """

    proposal_id: str = Field(description="提案 ID")
    vehicle_id: str = Field(description="车辆 ID")
    order_id: str = Field(description="关联订单 ID")
    eta: ETA = Field(description="预计到达")
    pricing: Pricing = Field(description="定价")
    driver: DriverProfile = Field(description="司机画像")
    vehicle: VehicleProfile = Field(description="车辆画像")
    add_on_services: list[AddOnService] = Field(
        default_factory=list, description="附加服务"
    )
    task_understanding_score: float = Field(
        ge=0, le=1, description="任务理解程度 0-1"
    )
    historical_fulfillment_score: float = Field(
        ge=0, le=1, description="历史履约分 0-1"
    )
    commitment_boundaries: CommitmentBoundaries = Field(description="可承诺边界")
    created_at: datetime = Field(description="创建时间")
