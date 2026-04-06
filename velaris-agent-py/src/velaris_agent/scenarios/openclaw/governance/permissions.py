"""车端权限边界管理。

管控: 数据访问权限、广告展示边界、附加服务授权、收益结算审计。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal


class PermissionScope(str, Enum):
    """权限范围。"""

    LOCATION_TRIP = "location_trip"           # 仅行程期间共享位置
    LOCATION_SESSION = "location_session"     # 会话期间共享位置
    AD_NONE = "ad_none"                       # 不展示广告
    AD_NON_INTRUSIVE = "ad_non_intrusive"     # 非侵入式广告
    AD_FULL = "ad_full"                       # 完整广告授权
    ADDON_BASIC = "addon_basic"              # 基础附加服务
    ADDON_PREMIUM = "addon_premium"          # 高级附加服务
    SETTLEMENT_VIEW = "settlement_view"      # 查看结算
    SETTLEMENT_AUDIT = "settlement_audit"    # 审计结算


@dataclass(frozen=True)
class PermissionGrant:
    """权限授予记录。"""

    scope: PermissionScope
    granted_to: str                           # vehicle_id 或 driver_id
    granted_by: str                           # user_id 或 platform
    contract_id: str
    expires_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class AuditEntry:
    """审计条目。"""

    action: str                               # "grant", "revoke", "access", "settle"
    actor: str
    target: str
    contract_id: str
    details: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class VehiclePermissionManager:
    """车端权限管理器。"""

    def __init__(self) -> None:
        """初始化。"""
        self._grants: list[PermissionGrant] = []
        self._audit_log: list[AuditEntry] = []

    def grant(
        self,
        scope: PermissionScope,
        granted_to: str,
        granted_by: str,
        contract_id: str,
        expires_at: datetime | None = None,
    ) -> PermissionGrant:
        """授予权限。"""
        g = PermissionGrant(
            scope=scope,
            granted_to=granted_to,
            granted_by=granted_by,
            contract_id=contract_id,
            expires_at=expires_at,
        )
        self._grants.append(g)
        self._audit_log.append(
            AuditEntry(
                action="grant",
                actor=granted_by,
                target=granted_to,
                contract_id=contract_id,
                details=f"scope={scope.value}",
            )
        )
        return g

    def revoke(self, contract_id: str, revoked_by: str) -> int:
        """撤销合约相关的所有权限, 返回撤销数量。"""
        before = len(self._grants)
        self._grants = [g for g in self._grants if g.contract_id != contract_id]
        revoked = before - len(self._grants)
        if revoked > 0:
            self._audit_log.append(
                AuditEntry(
                    action="revoke",
                    actor=revoked_by,
                    target=contract_id,
                    contract_id=contract_id,
                    details=f"revoked={revoked}",
                )
            )
        return revoked

    def check(self, scope: PermissionScope, vehicle_id: str, contract_id: str) -> bool:
        """检查权限是否存在且未过期。"""
        now = datetime.now(timezone.utc)
        for g in self._grants:
            if (
                g.scope == scope
                and g.granted_to == vehicle_id
                and g.contract_id == contract_id
            ):
                if g.expires_at is None or g.expires_at > now:
                    return True
        return False

    @property
    def audit_log(self) -> list[AuditEntry]:
        """返回审计日志。"""
        return list(self._audit_log)

    def grants_for_contract(self, contract_id: str) -> list[PermissionGrant]:
        """返回合约相关的所有权限。"""
        return [g for g in self._grants if g.contract_id == contract_id]
