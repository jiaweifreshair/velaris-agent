"""三段式派单协议。

Stage 1: IntentOrder   - 用户 agent 发出意图订单
Stage 2: ServiceProposal - 车端 agent 返回服务提案
Stage 3: TransactionContract - 协议化成交 (可审计契约)
"""

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
    PricingItem,
    ServiceProposal,
    VehicleProfile,
)
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

__all__ = [
    "AddOnService",
    "BreachClause",
    "Budget",
    "CommitmentBoundaries",
    "ContractStatus",
    "DataPermissions",
    "DriverProfile",
    "ETA",
    "EnterpriseIdentity",
    "IntentOrder",
    "Location",
    "Pricing",
    "PricingItem",
    "PriceComposition",
    "PrivacyLevel",
    "ProfitSharing",
    "ReviewMechanism",
    "ServicePreferences",
    "ServiceProposal",
    "Signatures",
    "TimeFlexibility",
    "TimeRequirements",
    "TransactionContract",
    "TripConstraints",
    "VehicleProfile",
    "WaitRules",
    "Budget",
    "Location",
]
