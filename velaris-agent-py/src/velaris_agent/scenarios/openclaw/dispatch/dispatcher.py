"""三段式派单调度引擎。

完整流程:
1. submit_intent: 广播意图订单到匹配车辆
2. collect_proposals: 收集车端 agent 服务提案
3. evaluate_proposals: 评分排序
4. form_contract: 生成可审计合约
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from velaris_agent.scenarios.openclaw.dispatch.scorer import (
    MIN_COMPLIANCE_SCORE,
    MIN_SAFETY_SCORE,
    ProposalScorer,
    ScoredProposal,
)
from velaris_agent.scenarios.openclaw.protocol.intent_order import IntentOrder
from velaris_agent.scenarios.openclaw.protocol.service_proposal import ServiceProposal
from velaris_agent.scenarios.openclaw.protocol.transaction_contract import (
    BreachClause,
    ContractStatus,
    DataPermissions,
    PriceComposition,
    ProfitSharing,
    ReviewMechanism,
    Signatures,
    TransactionContract,
    WaitRules,
)


@dataclass(frozen=True)
class DispatchResult:
    """调度结果。"""

    order: IntentOrder
    proposals_received: int
    scored_proposals: list[ScoredProposal]
    winning_proposal: ScoredProposal | None
    contract: TransactionContract | None
    dispatch_duration_ms: int


class VehicleRegistry:
    """车辆注册表 (用于管理可用 VehicleAgent)。"""

    def __init__(self) -> None:
        """初始化注册表。"""
        from velaris_agent.scenarios.openclaw.agents.vehicle_agent import VehicleAgent

        self._agents: dict[str, VehicleAgent] = {}

    def register(self, agent: object) -> None:
        """注册车端 agent。"""
        from velaris_agent.scenarios.openclaw.agents.vehicle_agent import VehicleAgent

        if not isinstance(agent, VehicleAgent):
            raise TypeError(f"Expected VehicleAgent, got {type(agent).__name__}")
        self._agents[agent.vehicle_id] = agent

    def unregister(self, vehicle_id: str) -> None:
        """注销车端 agent。"""
        self._agents.pop(vehicle_id, None)

    @property
    def agents(self) -> list[object]:
        """返回所有已注册 agent。"""
        return list(self._agents.values())

    def __len__(self) -> int:
        return len(self._agents)


class DispatchEngine:
    """三段式派单调度引擎。"""

    def __init__(
        self,
        vehicle_registry: VehicleRegistry | None = None,
        scorer: ProposalScorer | None = None,
    ) -> None:
        """初始化调度引擎。"""
        self.registry = vehicle_registry or VehicleRegistry()
        self.scorer = scorer or ProposalScorer()
        self._pending_proposals: dict[str, list[ServiceProposal]] = {}

    async def submit_intent(self, order: IntentOrder) -> str:
        """Stage 1: 广播意图订单到所有匹配车辆, 返回 order_id。"""
        from velaris_agent.scenarios.openclaw.agents.vehicle_agent import VehicleAgent

        self._pending_proposals[order.order_id] = []

        # 并发请求所有车端 agent 评估订单
        tasks = []
        for agent in self.registry.agents:
            if isinstance(agent, VehicleAgent):
                tasks.append(agent.evaluate_order(order))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, ServiceProposal):
                self._pending_proposals[order.order_id].append(result)
            # 忽略 None (拒单) 和异常

        return order.order_id

    async def collect_proposals(
        self, order_id: str, timeout: float = 30.0
    ) -> list[ServiceProposal]:
        """Stage 2: 收集车端 agent 的服务提案。

        当前实现中 submit_intent 已同步收集, 此方法直接返回。
        未来可改为真正的异步等待 + 超时机制。
        """
        return self._pending_proposals.get(order_id, [])

    async def evaluate_proposals(
        self, proposals: list[ServiceProposal], order: IntentOrder
    ) -> list[ScoredProposal]:
        """评分排序, 安全/合规不达标的排到最后。"""
        scored = self.scorer.score_batch(proposals, order)

        # 优先展示通过安全门槛的提案
        compliant = [
            s for s in scored
            if s.proposal.historical_fulfillment_score >= MIN_SAFETY_SCORE
        ]
        non_compliant = [s for s in scored if s not in compliant]

        return compliant + non_compliant

    async def form_contract(
        self, order: IntentOrder, proposal: ServiceProposal
    ) -> TransactionContract:
        """Stage 3: 生成可审计合约。"""
        now = datetime.now(timezone.utc)

        # 从提案构建价格组成
        price_composition = PriceComposition(
            base=proposal.pricing.base_price,
            surcharges=[
                item for item in proposal.pricing.surcharges
            ] if proposal.pricing.surcharges else [],
            add_ons=[],
            total=proposal.pricing.total_price,
            currency=proposal.pricing.currency,
        )

        # 默认违约条款
        breach_clauses = [
            BreachClause(
                party="user",
                condition="超过免费等待时间后取消",
                penalty="收取等待费用",
            ),
            BreachClause(
                party="driver",
                condition="未在承诺时间内到达",
                penalty="免单或折扣补偿",
            ),
            BreachClause(
                party="driver",
                condition="行程中途拒载",
                penalty="全额退款 + 信用扣分",
            ),
        ]

        # 默认分润
        profit_sharing = ProfitSharing(
            driver_percent=75.0,
            platform_percent=20.0,
            ecosystem_percent=5.0,
        )

        # 服务范围
        service_scope = ["point_to_point_transport"]
        for addon in proposal.add_on_services:
            service_scope.append(addon.name)

        return TransactionContract(
            contract_id=f"ctr-{uuid.uuid4().hex[:12]}",
            order_id=order.order_id,
            proposal_id=proposal.proposal_id,
            price_composition=price_composition,
            service_scope=service_scope,
            data_permissions=DataPermissions(
                location_sharing="trip_only",
                ad_authorization="none" if order.privacy_level.value != "standard" else "non_intrusive",
                data_retention="30_days",
            ),
            wait_rules=WaitRules(
                free_wait_minutes=proposal.commitment_boundaries.max_wait_minutes,
                charge_per_minute=1.0,
            ),
            breach_clauses=breach_clauses,
            add_on_profit_sharing=profit_sharing,
            review_mechanism=ReviewMechanism(),
            signatures=Signatures(),
            status=ContractStatus.DRAFT,
            created_at=now,
        )

    async def full_dispatch(self, order: IntentOrder) -> DispatchResult:
        """完整三段式调度流程。"""
        import time

        start = time.monotonic()

        # Stage 1 + 2
        await self.submit_intent(order)
        proposals = await self.collect_proposals(order.order_id)

        if not proposals:
            elapsed = int((time.monotonic() - start) * 1000)
            return DispatchResult(
                order=order,
                proposals_received=0,
                scored_proposals=[],
                winning_proposal=None,
                contract=None,
                dispatch_duration_ms=elapsed,
            )

        # 评分
        scored = await self.evaluate_proposals(proposals, order)

        # Stage 3: 生成合约
        winner = scored[0]
        contract = await self.form_contract(order, winner.proposal)

        elapsed = int((time.monotonic() - start) * 1000)
        return DispatchResult(
            order=order,
            proposals_received=len(proposals),
            scored_proposals=scored,
            winning_proposal=winner,
            contract=contract,
            dispatch_duration_ms=elapsed,
        )
