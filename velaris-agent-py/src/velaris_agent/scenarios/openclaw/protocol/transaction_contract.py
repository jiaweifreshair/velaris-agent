"""Stage 3: 可审计交易合约 - 协议化成交。

成交不是黑箱匹配, 而是形成可审计契约: 价格组成、服务范围、数据权限、
等待规则、违约条款、附加服务分润、广告授权边界、评价与申诉机制。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from velaris_agent.scenarios.openclaw.protocol.service_proposal import PricingItem


class PriceComposition(BaseModel):
    """价格组成 (透明定价)。"""

    base: float = Field(ge=0, description="基础费用")
    surcharges: list[PricingItem] = Field(
        default_factory=list, description="附加费用明细"
    )
    add_ons: list[PricingItem] = Field(
        default_factory=list, description="附加服务费用明细"
    )
    total: float = Field(ge=0, description="总计")
    currency: str = Field(default="CNY", description="货币")


class DataPermissions(BaseModel):
    """数据权限。"""

    location_sharing: Literal["trip_only", "session", "none"] = Field(
        default="trip_only", description="位置共享范围"
    )
    ad_authorization: Literal["none", "non_intrusive", "full"] = Field(
        default="none", description="广告授权边界"
    )
    data_retention: str = Field(
        default="30_days", description="数据保留期"
    )


class WaitRules(BaseModel):
    """等待规则。"""

    free_wait_minutes: int = Field(default=5, ge=0, description="免费等待分钟数")
    charge_per_minute: float = Field(
        default=1.0, ge=0, description="超时每分钟收费"
    )


class BreachClause(BaseModel):
    """违约条款。"""

    party: Literal["user", "driver", "platform"] = Field(description="责任方")
    condition: str = Field(description="违约条件描述")
    penalty: str = Field(description="处罚描述")


class ProfitSharing(BaseModel):
    """附加服务分润。"""

    driver_percent: float = Field(ge=0, le=100, description="司机分成比例")
    platform_percent: float = Field(ge=0, le=100, description="平台分成比例")
    ecosystem_percent: float = Field(
        default=0, ge=0, le=100, description="生态商家分成比例"
    )


class ReviewMechanism(BaseModel):
    """评价与申诉机制。"""

    appeal_window: str = Field(default="24h", description="申诉窗口")
    arbitration_method: str = Field(
        default="platform", description="仲裁方式"
    )
    rating_mutual: bool = Field(default=True, description="双向评价")


class Signatures(BaseModel):
    """签名。"""

    user_signed_at: datetime | None = Field(default=None, description="用户签署时间")
    vehicle_signed_at: datetime | None = Field(default=None, description="车端签署时间")
    platform_witnessed_at: datetime | None = Field(
        default=None, description="平台见证时间"
    )


class ContractStatus(str, Enum):
    """合约状态。"""

    DRAFT = "draft"
    SIGNED = "signed"
    ACTIVE = "active"
    COMPLETED = "completed"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"


class TransactionContract(BaseModel):
    """可审计交易合约。

    极大改善 "信任问题": 价格透明、权限明确、违约有据、评价公正。
    """

    contract_id: str = Field(description="合约 ID")
    order_id: str = Field(description="订单 ID")
    proposal_id: str = Field(description="提案 ID")
    price_composition: PriceComposition = Field(description="价格组成")
    service_scope: list[str] = Field(description="服务范围")
    data_permissions: DataPermissions = Field(
        default_factory=DataPermissions, description="数据权限"
    )
    wait_rules: WaitRules = Field(
        default_factory=WaitRules, description="等待规则"
    )
    breach_clauses: list[BreachClause] = Field(
        default_factory=list, description="违约条款"
    )
    add_on_profit_sharing: ProfitSharing = Field(description="附加服务分润")
    review_mechanism: ReviewMechanism = Field(
        default_factory=ReviewMechanism, description="评价与申诉机制"
    )
    signatures: Signatures = Field(
        default_factory=Signatures, description="签名"
    )
    status: ContractStatus = Field(
        default=ContractStatus.DRAFT, description="合约状态"
    )
    created_at: datetime = Field(description="创建时间")
