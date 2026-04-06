"""用户智能体 - 构造 IntentOrder, 审查 proposals, 批准 contract。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from velaris_agent.scenarios.openclaw.dispatch.scorer import ScoredProposal
from velaris_agent.scenarios.openclaw.protocol.intent_order import (
    Budget,
    IntentOrder,
    Location,
    ServicePreferences,
    TimeFlexibility,
    TimeRequirements,
    TripConstraints,
)
from velaris_agent.scenarios.openclaw.protocol.service_proposal import ServiceProposal
from velaris_agent.scenarios.openclaw.protocol.transaction_contract import (
    ContractStatus,
    TransactionContract,
)


class UserAgent:
    """用户智能体。

    - 构造 IntentOrder (从自然语言或结构化输入)
    - 审查 proposals
    - 批准/拒绝 contract
    """

    def __init__(self, user_id: str) -> None:
        """初始化用户 agent。"""
        self.user_id = user_id

    def create_intent(
        self,
        origin: Location,
        destination: Location,
        earliest: datetime,
        max_price: float,
        *,
        currency: str = "CNY",
        flexibility: TimeFlexibility = TimeFlexibility.FLEXIBLE_15M,
        preferences: ServicePreferences | None = None,
        constraints: TripConstraints | None = None,
        additional_services: list[str] | None = None,
    ) -> IntentOrder:
        """构造意图订单。"""
        return IntentOrder(
            order_id=f"ord-{uuid.uuid4().hex[:12]}",
            user_id=self.user_id,
            origin=origin,
            destination=destination,
            time_requirements=TimeRequirements(
                earliest=earliest,
                flexibility=flexibility,
            ),
            service_preferences=preferences or ServicePreferences(),
            budget=Budget(max_price=max_price, currency=currency),
            constraints=constraints or TripConstraints(),
            additional_services=additional_services or [],
            created_at=datetime.now(timezone.utc),
        )

    def review_proposals(
        self,
        scored: list[ScoredProposal],
        *,
        min_score: float = 0.0,
        max_results: int = 5,
    ) -> list[ScoredProposal]:
        """审查提案, 按分数过滤并截取。"""
        filtered = [s for s in scored if s.score >= min_score]
        return filtered[:max_results]

    def select_proposal(self, scored: list[ScoredProposal]) -> ServiceProposal | None:
        """选择最优提案。"""
        if not scored:
            return None
        return scored[0].proposal

    def approve_contract(self, contract: TransactionContract) -> TransactionContract:
        """批准合约 (用户签署)。"""
        now = datetime.now(timezone.utc)
        return contract.model_copy(
            update={
                "signatures": contract.signatures.model_copy(
                    update={"user_signed_at": now}
                ),
                "status": ContractStatus.SIGNED,
            }
        )

    def reject_contract(self, contract: TransactionContract) -> TransactionContract:
        """拒绝合约。"""
        return contract.model_copy(
            update={"status": ContractStatus.CANCELLED}
        )
