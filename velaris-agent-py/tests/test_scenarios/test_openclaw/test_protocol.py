"""三段式协议 Pydantic 模型验证测试。"""

from datetime import datetime, timezone

import pytest

from velaris_agent.scenarios.openclaw.protocol.intent_order import (
    Budget,
    EnterpriseIdentity,
    IntentOrder,
    Location,
    PrivacyLevel,
    ServicePreferences,
    TimeFlexibility,
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
from velaris_agent.scenarios.openclaw.protocol.transaction_contract import (
    BreachClause,
    ContractStatus,
    DataPermissions,
    PriceComposition,
    ProfitSharing,
    TransactionContract,
)


def _make_location(name: str = "test") -> Location:
    return Location(lat=39.9, lng=116.4, name=name)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TestIntentOrder:
    """IntentOrder 模型测试。"""

    def test_minimal_creation(self) -> None:
        order = IntentOrder(
            order_id="ord-001",
            user_id="user-001",
            origin=_make_location("北京"),
            destination=_make_location("上海"),
            time_requirements=TimeRequirements(earliest=_now()),
            budget=Budget(max_price=100.0),
            created_at=_now(),
        )
        assert order.order_id == "ord-001"
        assert order.privacy_level == PrivacyLevel.STANDARD
        assert order.constraints.luggage == 0
        assert order.constraints.wheelchair is False
        assert order.additional_services == []

    def test_full_creation(self) -> None:
        order = IntentOrder(
            order_id="ord-002",
            user_id="user-002",
            origin=_make_location("朝阳"),
            destination=_make_location("浦东"),
            time_requirements=TimeRequirements(
                earliest=_now(),
                flexibility=TimeFlexibility.FLEXIBLE_1H,
            ),
            service_preferences=ServicePreferences(
                vehicle_type="premium",
                driver_style="quiet",
                carpool_willing=False,
            ),
            budget=Budget(max_price=500.0, surge_acceptable=True),
            privacy_level=PrivacyLevel.ENHANCED,
            constraints=TripConstraints(luggage=2, children=1, wheelchair=True),
            enterprise_identity=EnterpriseIdentity(
                company_id="corp-001",
                reimbursement_code="RC-2026",
            ),
            additional_services=["wifi", "water"],
            created_at=_now(),
        )
        assert order.constraints.wheelchair is True
        assert order.enterprise_identity is not None
        assert order.enterprise_identity.company_id == "corp-001"
        assert len(order.additional_services) == 2

    def test_budget_currency_default(self) -> None:
        b = Budget(max_price=50.0)
        assert b.currency == "CNY"


class TestServiceProposal:
    """ServiceProposal 模型测试。"""

    def test_creation(self) -> None:
        proposal = ServiceProposal(
            proposal_id="prop-001",
            vehicle_id="v-001",
            order_id="ord-001",
            eta=ETA(minutes=8.5, confidence=0.85),
            pricing=Pricing(base_price=30.0, total_price=35.0),
            driver=DriverProfile(
                driver_id="d-001", rating=4.8, completed_trips=1200, style="quiet"
            ),
            vehicle=VehicleProfile(model="Tesla Model 3", year=2025, capacity=4),
            task_understanding_score=0.85,
            historical_fulfillment_score=0.92,
            commitment_boundaries=CommitmentBoundaries(
                max_wait_minutes=10, cancellation_policy="free_5min"
            ),
            created_at=_now(),
        )
        assert proposal.eta.confidence == 0.85
        assert proposal.driver.rating == 4.8
        assert proposal.add_on_services == []

    def test_with_add_on_services(self) -> None:
        proposal = ServiceProposal(
            proposal_id="prop-002",
            vehicle_id="v-002",
            order_id="ord-001",
            eta=ETA(minutes=5.0, confidence=0.9),
            pricing=Pricing(base_price=40.0, total_price=48.0),
            driver=DriverProfile(
                driver_id="d-002", rating=4.5, completed_trips=800, style="social"
            ),
            vehicle=VehicleProfile(
                model="BYD Han", year=2025, capacity=5, features=["ev", "wifi"]
            ),
            add_on_services=[
                AddOnService(service_id="s1", name="wifi", price=5.0, description="车载WiFi"),
                AddOnService(service_id="s2", name="water", price=3.0, description="矿泉水"),
            ],
            task_understanding_score=0.75,
            historical_fulfillment_score=0.88,
            commitment_boundaries=CommitmentBoundaries(
                max_wait_minutes=8, cancellation_policy="charge_after_3min"
            ),
            created_at=_now(),
        )
        assert len(proposal.add_on_services) == 2

    def test_score_bounds(self) -> None:
        with pytest.raises(Exception):
            ETA(minutes=-1, confidence=0.5)
        with pytest.raises(Exception):
            ETA(minutes=5, confidence=1.5)


class TestTransactionContract:
    """TransactionContract 模型测试。"""

    def test_creation(self) -> None:
        contract = TransactionContract(
            contract_id="ctr-001",
            order_id="ord-001",
            proposal_id="prop-001",
            price_composition=PriceComposition(base=30.0, total=35.0),
            service_scope=["point_to_point_transport"],
            add_on_profit_sharing=ProfitSharing(
                driver_percent=75.0, platform_percent=20.0, ecosystem_percent=5.0
            ),
            created_at=_now(),
        )
        assert contract.status == ContractStatus.DRAFT
        assert contract.data_permissions.location_sharing == "trip_only"
        assert contract.wait_rules.free_wait_minutes == 5

    def test_with_breach_clauses(self) -> None:
        contract = TransactionContract(
            contract_id="ctr-002",
            order_id="ord-001",
            proposal_id="prop-001",
            price_composition=PriceComposition(base=50.0, total=60.0),
            service_scope=["transport", "wifi"],
            data_permissions=DataPermissions(
                location_sharing="session", ad_authorization="non_intrusive"
            ),
            breach_clauses=[
                BreachClause(party="user", condition="超时取消", penalty="收取等待费"),
                BreachClause(party="driver", condition="拒载", penalty="全额退款"),
            ],
            add_on_profit_sharing=ProfitSharing(
                driver_percent=70.0, platform_percent=25.0
            ),
            created_at=_now(),
        )
        assert len(contract.breach_clauses) == 2
        assert contract.data_permissions.ad_authorization == "non_intrusive"

    def test_status_enum(self) -> None:
        assert ContractStatus.DRAFT.value == "draft"
        assert ContractStatus.SIGNED.value == "signed"
        assert ContractStatus.DISPUTED.value == "disputed"
