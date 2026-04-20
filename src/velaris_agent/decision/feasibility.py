"""酒店 / 商旅共享决策的可行性检查器。

这一层只负责硬约束过滤、约束摘要和可行性报告，
不负责排序，也不负责解释文案。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from velaris_agent.decision.contracts import BundleCandidate, CapabilityCandidate

_UNAVAILABLE_STATUSES = {"sold_out", "unavailable", "out_of_stock", "closed"}

__all__ = ["FeasibilityChecker"]


class FeasibilityChecker:
    """酒店 / 商旅共享决策的硬约束可行性检查器。

    这一层把预算、绕路、库存和时间窗等硬约束统一收口，
    让排序器只面对已经可行的候选集。
    """

    def __init__(self, unavailable_statuses: set[str] | None = None) -> None:
        """初始化检查器的不可用状态集合。"""

        self._unavailable_statuses = set(unavailable_statuses or _UNAVAILABLE_STATUSES)

    def filter_candidates(
        self,
        candidates: Sequence[CapabilityCandidate],
        hard_constraints: dict[str, Any],
    ) -> tuple[list[CapabilityCandidate], dict[str, list[str]]]:
        """过滤同类候选并返回拒绝原因。"""

        feasible: list[CapabilityCandidate] = []
        rejected: dict[str, list[str]] = {}
        for candidate in candidates:
            reasons = self.candidate_rejection_reasons(candidate, hard_constraints)
            if reasons:
                rejected[candidate.candidate_id] = reasons
                continue
            feasible.append(candidate)
        return feasible, rejected

    def filter_bundles(
        self,
        bundles: Sequence[BundleCandidate],
        hard_constraints: dict[str, Any],
    ) -> tuple[list[BundleCandidate], dict[str, list[str]]]:
        """过滤 bundle 候选并返回拒绝原因。"""

        feasible: list[BundleCandidate] = []
        rejected: dict[str, list[str]] = {}
        for bundle in bundles:
            reasons = self.bundle_rejection_reasons(bundle, hard_constraints)
            if reasons:
                rejected[bundle.bundle_id] = reasons
                continue
            feasible.append(bundle)
        return feasible, rejected

    def candidate_rejection_reasons(
        self,
        candidate: CapabilityCandidate,
        hard_constraints: dict[str, Any],
    ) -> list[str]:
        """生成同类候选的硬约束拒绝原因。"""

        reasons: list[str] = []
        if not candidate.available or candidate.inventory_status in self._unavailable_statuses:
            reasons.append("inventory_unavailable")

        budget_max = _coerce_float(hard_constraints.get("budget_max"))
        if budget_max is not None and candidate.price is not None and candidate.price > budget_max:
            reasons.append("budget_exceeded")

        max_detour_minutes = _coerce_float(hard_constraints.get("max_detour_minutes"))
        if (
            max_detour_minutes is not None
            and candidate.detour_minutes is not None
            and candidate.detour_minutes > max_detour_minutes
        ):
            reasons.append("detour_exceeded")

        required_status = hard_constraints.get("required_inventory_status")
        if required_status and candidate.inventory_status != required_status:
            reasons.append("inventory_status_mismatch")

        candidate_report = candidate.metadata.get("hard_constraint_report", {})
        if isinstance(candidate_report, dict) and candidate_report.get("passed") is False:
            reasons.extend(str(item) for item in candidate_report.get("checks", []))
        return list(dict.fromkeys(reasons))

    def bundle_rejection_reasons(
        self,
        bundle: BundleCandidate,
        hard_constraints: dict[str, Any],
    ) -> list[str]:
        """生成 bundle 的硬约束拒绝原因。"""

        reasons: list[str] = []
        bundle_report = bundle.hard_constraint_report
        if isinstance(bundle_report, dict) and bundle_report.get("passed") is False:
            reasons.extend(str(item) for item in bundle_report.get("checks", []))

        budget_max = _coerce_float(hard_constraints.get("budget_max"))
        if (
            budget_max is not None
            and bundle.aggregates.total_price is not None
            and bundle.aggregates.total_price > budget_max
        ):
            reasons.append("budget_exceeded")

        max_detour_minutes = _coerce_float(hard_constraints.get("max_detour_minutes"))
        if (
            max_detour_minutes is not None
            and bundle.aggregates.detour_minutes is not None
            and bundle.aggregates.detour_minutes > max_detour_minutes
        ):
            reasons.append("detour_exceeded")

        if (
            bundle.aggregates.time_slack_minutes is not None
            and bundle.aggregates.time_slack_minutes <= 0
        ):
            reasons.append("time_slack_exhausted")

        return list(dict.fromkeys(reasons))

    def candidate_checks(
        self,
        candidate: CapabilityCandidate,
        hard_constraints: dict[str, Any],
    ) -> list[str]:
        """生成候选项通过硬约束后的检查摘要。"""

        checks: list[str] = []
        budget_max = _coerce_float(hard_constraints.get("budget_max"))
        if budget_max is not None and candidate.price is not None and candidate.price <= budget_max:
            checks.append("预算满足")
        if candidate.available and candidate.inventory_status not in self._unavailable_statuses:
            checks.append("可用")
        max_detour_minutes = _coerce_float(hard_constraints.get("max_detour_minutes"))
        if (
            max_detour_minutes is not None
            and candidate.detour_minutes is not None
            and candidate.detour_minutes <= max_detour_minutes
        ):
            checks.append("绕路满足")
        return checks

    def summarize_hard_constraints(self, hard_constraints: dict[str, Any]) -> list[str]:
        """把硬约束整理成短摘要，方便前端直接展示。"""

        summary: list[str] = []
        if hard_constraints.get("budget_max") is not None:
            summary.append("预算满足")
        if hard_constraints.get("max_detour_minutes") is not None:
            summary.append("绕路上限满足")
        if hard_constraints.get("required_inventory_status") is not None:
            summary.append("库存状态受限")
        if hard_constraints.get("must_finish_before") is not None:
            summary.append("完成时间受限")
        return summary

    def build_candidate_report(
        self,
        *,
        feasible_candidates: Sequence[Any],
        rejected_reasons: dict[str, list[str]],
        hard_constraints: dict[str, Any],
    ) -> dict[str, Any]:
        """构建同类候选的整体硬约束报告。"""

        return {
            "passed": True,
            "checks": self.summarize_hard_constraints(hard_constraints),
            "feasible_candidate_ids": [item.candidate_id for item in feasible_candidates],
            "rejected_candidate_ids": list(rejected_reasons),
        }

    def build_bundle_report(
        self,
        *,
        feasible_bundles: Sequence[BundleCandidate],
        selected_bundle: BundleCandidate,
        rejected_reasons: dict[str, list[str]],
        hard_constraints: dict[str, Any],
    ) -> dict[str, Any]:
        """构建 bundle 的整体硬约束报告。"""

        return {
            "passed": True,
            "checks": self.summarize_hard_constraints(hard_constraints),
            "feasible_bundle_ids": [item.bundle_id for item in feasible_bundles],
            "rejected_bundle_ids": list(rejected_reasons),
            "time_slack_minutes": selected_bundle.aggregates.time_slack_minutes,
        }

    def build_uncertainty_flags(
        self,
        *,
        hard_constraints: dict[str, Any],
        feasible_count: int,
    ) -> list[str]:
        """生成需要向用户或审计层提示的不确定性标记。"""

        flags: list[str] = []
        if feasible_count <= 1:
            flags.append("small_feasible_set")
        if hard_constraints.get("must_finish_before") is not None:
            flags.append("time_deadline_sensitive")
        return flags


def _coerce_float(value: Any) -> float | None:
    """尽量把任意输入转成浮点数。"""

    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
