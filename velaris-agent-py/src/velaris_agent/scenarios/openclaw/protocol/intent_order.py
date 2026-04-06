"""Stage 1: 意图订单 - 用户 agent 发出的结构化任务请求。

订单从"路线请求"升级为"任务请求": 包含出发地/目的地、时间要求、服务偏好、
预算、隐私等级、附加服务、企业报销身份、行李/儿童/老人约束等。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Location(BaseModel):
    """地理位置。"""

    lat: float = Field(description="纬度")
    lng: float = Field(description="经度")
    name: str = Field(description="地点名称")


class TimeFlexibility(str, Enum):
    """时间弹性。"""

    EXACT = "exact"
    FLEXIBLE_15M = "flexible_15m"
    FLEXIBLE_30M = "flexible_30m"
    FLEXIBLE_1H = "flexible_1h"


class TimeRequirements(BaseModel):
    """时间要求。"""

    earliest: datetime = Field(description="最早出发时间")
    latest: datetime | None = Field(default=None, description="最晚出发时间")
    flexibility: TimeFlexibility = Field(
        default=TimeFlexibility.FLEXIBLE_15M,
        description="时间弹性",
    )


class ServicePreferences(BaseModel):
    """服务偏好。"""

    vehicle_type: Literal["economy", "comfort", "premium", "accessible"] | None = Field(
        default=None, description="车型偏好"
    )
    driver_style: Literal["quiet", "social", "professional"] | None = Field(
        default=None, description="司机风格偏好"
    )
    carpool_willing: bool = Field(default=False, description="是否接受拼车")
    environment: list[str] = Field(
        default_factory=list,
        description="车内环境偏好, 如 ['quiet', 'music_ok', 'smoke_free']",
    )


class Budget(BaseModel):
    """预算。"""

    max_price: float = Field(description="预算上限")
    currency: str = Field(default="CNY", description="货币")
    surge_acceptable: bool = Field(default=False, description="是否接受溢价")


class PrivacyLevel(str, Enum):
    """隐私等级。"""

    STANDARD = "standard"
    ENHANCED = "enhanced"
    MAXIMUM = "maximum"


class TripConstraints(BaseModel):
    """行程约束。"""

    luggage: int = Field(default=0, ge=0, description="行李件数")
    children: int = Field(default=0, ge=0, description="儿童人数")
    elderly: int = Field(default=0, ge=0, description="老人人数")
    wheelchair: bool = Field(default=False, description="轮椅需求")
    pets: bool = Field(default=False, description="宠物")


class EnterpriseIdentity(BaseModel):
    """企业报销/差旅身份。"""

    company_id: str | None = Field(default=None, description="企业 ID")
    reimbursement_code: str | None = Field(default=None, description="报销编码")
    cost_center: str | None = Field(default=None, description="成本中心")
    travel_policy: str | None = Field(default=None, description="差旅政策等级")


class IntentOrder(BaseModel):
    """意图订单 - 用户 agent 发出的结构化任务请求。

    不是 "我要一辆车", 而是包含完整上下文的任务请求。
    """

    order_id: str = Field(description="订单 ID")
    user_id: str = Field(description="用户 ID")
    origin: Location = Field(description="出发地")
    destination: Location = Field(description="目的地")
    time_requirements: TimeRequirements = Field(description="时间要求")
    service_preferences: ServicePreferences = Field(
        default_factory=ServicePreferences, description="服务偏好"
    )
    budget: Budget = Field(description="预算")
    privacy_level: PrivacyLevel = Field(
        default=PrivacyLevel.STANDARD, description="隐私等级"
    )
    constraints: TripConstraints = Field(
        default_factory=TripConstraints, description="行程约束"
    )
    enterprise_identity: EnterpriseIdentity | None = Field(
        default=None, description="企业差旅身份"
    )
    additional_services: list[str] = Field(
        default_factory=list,
        description="附加服务需求, 如 ['wifi', 'charger', 'water']",
    )
    created_at: datetime = Field(description="创建时间")
