"""调度引擎 + 评分器 + Agent 全流程测试。"""

from datetime import datetime, timezone

import pytest

from velaris_agent.scenarios.openclaw.agents.user_agent import UserAgent
from velaris_agent.scenarios.openclaw.agents.vehicle_agent import VehicleAgent, VehicleCapabilities
from velaris_agent.scenarios.openclaw.dispatch.dispatcher import DispatchEngine, VehicleRegistry
from velaris_agent.scenarios.openclaw.dispatch.scorer import ProposalScorer
from velaris_agent.scenarios.openclaw.protocol.intent_order import (
    Budget,
    IntentOrder,
    Location,
    ServicePreferences,
    TimeRequirements,
    TripConstraints,
)
from velaris_agent.scenarios.openclaw.protocol.service_proposal import (
    AddOnService,
    CommitmentBoundaries,
    DriverProfile,
    ETA,
    Pricing,
    ServiceProposal,
    VehicleProfile,
)
from velaris_agent.scenarios.openclaw.protocol.transaction_contract import ContractStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_order(
    max_price: float = 100.0,
    wheelchair: bool = False,
    additional_services: list[str] | None = None,
) -> IntentOrder:
    return IntentOrder(
        order_id="ord-test",
        user_id="user-test",
        origin=Location(lat=39.908, lng=116.397, name="天安门"),
        destination=Location(lat=39.992, lng=116.326, name="中关村"),
        time_requirements=TimeRequirements(earliest=_now()),
        budget=Budget(max_price=max_price),
        constraints=TripConstraints(wheelchair=wheelchair),
        additional_services=additional_services or [],
        created_at=_now(),
    )


def _make_proposal(
    vehicle_id: str = "v-001",
    price: float = 35.0,
    eta_min: float = 8.0,
    task_score: float = 0.85,
    fulfillment: float = 0.92,
    features: list[str] | None = None,
    add_ons: list[AddOnService] | None = None,
) -> ServiceProposal:
    return ServiceProposal(
        proposal_id=f"prop-{vehicle_id}",
        vehicle_id=vehicle_id,
        order_id="ord-test",
        eta=ETA(minutes=eta_min, confidence=0.85),
        pricing=Pricing(base_price=price, total_price=price),
        driver=DriverProfile(
            driver_id=f"d-{vehicle_id}", rating=4.5, completed_trips=500, style="quiet"
        ),
        vehicle=VehicleProfile(
            model="TestCar", year=2025, capacity=4, features=features or []
        ),
        add_on_services=add_ons or [],
        task_understanding_score=task_score,
        historical_fulfillment_score=fulfillment,
        commitment_boundaries=CommitmentBoundaries(
            max_wait_minutes=10, cancellation_policy="free_5min"
        ),
        created_at=_now(),
    )


def _make_vehicle_agent(
    vehicle_id: str = "v-001",
    lat: float = 39.91,
    lng: float = 116.40,
    price_per_km: float = 2.5,
    features: list[str] | None = None,
    rating: float = 4.5,
) -> VehicleAgent:
    return VehicleAgent(
        capabilities=VehicleCapabilities(
            vehicle_id=vehicle_id,
            vehicle_profile=VehicleProfile(
                model="TestCar", year=2025, capacity=4, features=features or ["ev"]
            ),
            driver_profile=DriverProfile(
                driver_id=f"d-{vehicle_id}",
                rating=rating,
                completed_trips=500,
                style="quiet",
            ),
            current_location=Location(lat=lat, lng=lng, name="测试位置"),
            price_per_km=price_per_km,
        )
    )


class TestProposalScorer:
    """评分器测试。"""

    def test_score_single(self) -> None:
        scorer = ProposalScorer()
        order = _make_order(max_price=100.0)
        proposal = _make_proposal(price=35.0, eta_min=8.0)
        scored = scorer.score(proposal, order)

        assert 0 < scored.score <= 1.0
        assert "price" in scored.score_breakdown
        assert "eta" in scored.score_breakdown
        assert scored.score_breakdown["price"] > 0.5  # 35/100 很便宜

    def test_score_batch_sorted(self) -> None:
        scorer = ProposalScorer()
        order = _make_order(max_price=100.0)
        proposals = [
            _make_proposal(vehicle_id="cheap", price=20.0, eta_min=10.0, fulfillment=0.9),
            _make_proposal(vehicle_id="expensive", price=90.0, eta_min=3.0, fulfillment=0.95),
            _make_proposal(vehicle_id="mid", price=50.0, eta_min=6.0, fulfillment=0.88),
        ]
        scored = scorer.score_batch(proposals, order)
        assert len(scored) == 3
        # 应按总分降序
        assert scored[0].score >= scored[1].score >= scored[2].score

    def test_over_budget_gets_zero_price_score(self) -> None:
        scorer = ProposalScorer()
        order = _make_order(max_price=30.0)
        proposal = _make_proposal(price=50.0)
        scored = scorer.score(proposal, order)
        assert scored.score_breakdown["price"] == 0.0

    def test_wheelchair_constraint(self) -> None:
        scorer = ProposalScorer()
        order = _make_order(wheelchair=True)
        # 无 accessible 特性
        proposal = _make_proposal(features=[])
        scored = scorer.score(proposal, order)
        assert scored.score_breakdown["task_fit"] == 0.0

    def test_add_on_matching(self) -> None:
        scorer = ProposalScorer()
        order = _make_order(additional_services=["wifi", "water"])
        proposal = _make_proposal(
            add_ons=[
                AddOnService(service_id="s1", name="wifi", price=5.0, description="WiFi"),
            ]
        )
        scored = scorer.score(proposal, order)
        assert scored.score_breakdown["add_on_value"] == 0.5  # 1/2 matched


class TestVehicleAgent:
    """车端 agent 测试。"""

    @pytest.mark.asyncio
    async def test_evaluate_order_accepts(self) -> None:
        agent = _make_vehicle_agent()
        order = _make_order(max_price=100.0)
        proposal = await agent.evaluate_order(order)
        assert proposal is not None
        assert proposal.vehicle_id == "v-001"
        assert proposal.pricing.total_price > 0

    @pytest.mark.asyncio
    async def test_evaluate_order_rejects_over_budget(self) -> None:
        agent = _make_vehicle_agent(price_per_km=100.0)  # 非常贵
        order = _make_order(max_price=10.0)
        proposal = await agent.evaluate_order(order)
        assert proposal is None

    @pytest.mark.asyncio
    async def test_evaluate_order_rejects_wheelchair_no_feature(self) -> None:
        agent = _make_vehicle_agent(features=["ev"])
        order = _make_order(wheelchair=True)
        proposal = await agent.evaluate_order(order)
        assert proposal is None

    @pytest.mark.asyncio
    async def test_evaluate_order_accepts_wheelchair_with_feature(self) -> None:
        agent = _make_vehicle_agent(features=["ev", "accessible"])
        order = _make_order(wheelchair=True)
        proposal = await agent.evaluate_order(order)
        assert proposal is not None


class TestUserAgent:
    """用户 agent 测试。"""

    def test_create_intent(self) -> None:
        user = UserAgent(user_id="u-001")
        order = user.create_intent(
            origin=Location(lat=39.9, lng=116.4, name="A"),
            destination=Location(lat=40.0, lng=116.5, name="B"),
            earliest=_now(),
            max_price=200.0,
        )
        assert order.user_id == "u-001"
        assert order.budget.max_price == 200.0
        assert order.order_id.startswith("ord-")

    def test_approve_contract(self) -> None:
        from velaris_agent.scenarios.openclaw.protocol.transaction_contract import (
            PriceComposition,
            ProfitSharing,
            TransactionContract,
        )

        user = UserAgent(user_id="u-001")
        contract = TransactionContract(
            contract_id="ctr-001",
            order_id="ord-001",
            proposal_id="prop-001",
            price_composition=PriceComposition(base=30.0, total=35.0),
            service_scope=["transport"],
            add_on_profit_sharing=ProfitSharing(driver_percent=75.0, platform_percent=25.0),
            created_at=_now(),
        )
        signed = user.approve_contract(contract)
        assert signed.status == ContractStatus.SIGNED
        assert signed.signatures.user_signed_at is not None

    def test_reject_contract(self) -> None:
        from velaris_agent.scenarios.openclaw.protocol.transaction_contract import (
            PriceComposition,
            ProfitSharing,
            TransactionContract,
        )

        user = UserAgent(user_id="u-001")
        contract = TransactionContract(
            contract_id="ctr-002",
            order_id="ord-001",
            proposal_id="prop-001",
            price_composition=PriceComposition(base=30.0, total=35.0),
            service_scope=["transport"],
            add_on_profit_sharing=ProfitSharing(driver_percent=75.0, platform_percent=25.0),
            created_at=_now(),
        )
        cancelled = user.reject_contract(contract)
        assert cancelled.status == ContractStatus.CANCELLED


class TestDispatchEngine:
    """调度引擎全流程测试。"""

    @pytest.mark.asyncio
    async def test_full_dispatch_with_vehicles(self) -> None:
        registry = VehicleRegistry()
        registry.register(_make_vehicle_agent("v-001", lat=39.91, lng=116.40, rating=4.8))
        registry.register(_make_vehicle_agent("v-002", lat=39.92, lng=116.41, rating=4.2))
        registry.register(_make_vehicle_agent("v-003", lat=39.90, lng=116.39, rating=4.6))

        engine = DispatchEngine(vehicle_registry=registry)
        order = _make_order(max_price=100.0)
        result = await engine.full_dispatch(order)

        assert result.proposals_received >= 2
        assert result.winning_proposal is not None
        assert result.contract is not None
        assert result.contract.status == ContractStatus.DRAFT
        assert result.contract.order_id == "ord-test"
        assert result.dispatch_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_full_dispatch_no_vehicles(self) -> None:
        engine = DispatchEngine()
        order = _make_order(max_price=100.0)
        result = await engine.full_dispatch(order)

        assert result.proposals_received == 0
        assert result.winning_proposal is None
        assert result.contract is None

    @pytest.mark.asyncio
    async def test_full_dispatch_all_reject(self) -> None:
        """所有车辆拒单 (价格太低)。"""
        registry = VehicleRegistry()
        registry.register(_make_vehicle_agent("v-001", price_per_km=50.0))

        engine = DispatchEngine(vehicle_registry=registry)
        order = _make_order(max_price=5.0)
        result = await engine.full_dispatch(order)

        assert result.proposals_received == 0
        assert result.winning_proposal is None

    @pytest.mark.asyncio
    async def test_contract_has_breach_clauses(self) -> None:
        registry = VehicleRegistry()
        registry.register(_make_vehicle_agent("v-001"))

        engine = DispatchEngine(vehicle_registry=registry)
        order = _make_order()
        result = await engine.full_dispatch(order)

        assert result.contract is not None
        assert len(result.contract.breach_clauses) >= 2
        assert result.contract.add_on_profit_sharing.driver_percent == 75.0
