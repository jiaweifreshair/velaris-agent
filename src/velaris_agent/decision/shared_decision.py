"""酒店 / 商旅共享决策门面。

对外只暴露契约与一个稳定的 evaluate 入口，
具体规划逻辑下沉到 `planner.py`。
"""

from __future__ import annotations

from velaris_agent.decision.contracts import (
    BundleCandidate,
    BundleCandidateAggregates,
    BundleDecisionRequest,
    BundleDecisionResponse,
    BundleMemberRef,
    CapabilityCandidate,
    CapabilityCandidateSet,
    RankedBundle,
    RankedCandidate,
    build_bundle_decision_request,
)
from velaris_agent.decision.planner import evaluate_bundle_decision

__all__ = [
    "BundleCandidate",
    "BundleCandidateAggregates",
    "BundleDecisionRequest",
    "BundleDecisionResponse",
    "BundleMemberRef",
    "CapabilityCandidate",
    "CapabilityCandidateSet",
    "RankedBundle",
    "RankedCandidate",
    "build_bundle_decision_request",
    "evaluate_bundle_decision",
]
