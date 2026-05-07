"""Velaris 原生能力签发服务。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timezone, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class CapabilityToken:
    """能力令牌。"""

    token_id: str
    scope: list[str]
    ttl_seconds: int
    issued_at: str


@dataclass(frozen=True)
class AuthorityPlan:
    """授权计划。"""

    approvals_required: bool
    required_capabilities: list[str]
    capability_tokens: list[CapabilityToken]

    def to_dict(self) -> dict[str, Any]:
        """把授权计划转换为 JSON 友好的字典。"""
        return asdict(self)


class AuthorityService:
    """能力签发服务。"""

    def __init__(
        self,
        default_token_ttl_seconds: int = 1800,
        approval_sensitive_capabilities: list[str] | None = None,
    ) -> None:
        """初始化授权服务。"""
        self.default_token_ttl_seconds = default_token_ttl_seconds
        self.approval_sensitive_capabilities = approval_sensitive_capabilities or [
            "write",
            "exec",
            "audit",
            "contract_form",
        ]

    def issue_plan(self, required_capabilities: list[str], governance: dict[str, Any]) -> AuthorityPlan:
        """生成授权计划。"""
        deduped_capabilities = list(dict.fromkeys(required_capabilities))
        approval_mode = str(governance.get("approval_mode", "default"))
        approvals_required = approval_mode == "strict" or any(
            capability in self.approval_sensitive_capabilities
            for capability in deduped_capabilities
        )
        tokens = self._create_tokens(deduped_capabilities)
        return AuthorityPlan(
            approvals_required=approvals_required,
            required_capabilities=deduped_capabilities,
            capability_tokens=tokens,
        )

    def _create_tokens(self, required_capabilities: list[str]) -> list[CapabilityToken]:
        """创建短时能力令牌。"""
        if not required_capabilities:
            return []
        return [
            CapabilityToken(
                token_id=f"cap-{uuid4().hex[:12]}",
                scope=required_capabilities,
                ttl_seconds=self.default_token_ttl_seconds,
                issued_at=datetime.now(timezone.utc).isoformat(),
            )
        ]
