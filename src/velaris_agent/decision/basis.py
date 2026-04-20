"""酒店 / 商旅共享决策的决策依据构建器。

这一层把排序结果翻译成可读、可审计的解释，
不负责过滤，也不负责分数计算。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, cast

from velaris_agent.decision.contracts import RankedBundle, RankedCandidate

__all__ = ["DecisionBasisBuilder"]


class DecisionBasisBuilder:
    """把排序结果转成结构化决策依据。"""

    def build_candidate_basis(
        self,
        *,
        ranked_candidates: Sequence[RankedCandidate],
        rejected_reasons: dict[str, list[str]],
        hard_constraints: dict[str, Any],
    ) -> dict[str, Any]:
        """构建同类候选的解释依据。"""

        return self._build_basis(
            ranked_items=list(ranked_candidates),
            rejected_reasons=rejected_reasons,
            hard_constraints=hard_constraints,
            kind="candidate",
        )

    def build_bundle_basis(
        self,
        *,
        ranked_bundles: Sequence[RankedBundle],
        rejected_reasons: dict[str, list[str]],
        hard_constraints: dict[str, Any],
    ) -> dict[str, Any]:
        """构建 bundle 的解释依据。"""

        return self._build_basis(
            ranked_items=list(ranked_bundles),
            rejected_reasons=rejected_reasons,
            hard_constraints=hard_constraints,
            kind="bundle",
        )

    def build_reason_from_scores(
        self,
        scores: dict[str, float],
        *,
        kind: Literal["candidate", "bundle"],
    ) -> str:
        """把评分拆解翻译成简短的排序原因。"""

        if kind == "bundle":
            return (
                f"总价 {scores.get('price', 0.0):.2f}，"
                f"总 ETA {scores.get('eta', 0.0):.2f}，"
                f"绕路 {scores.get('detour_cost', 0.0):.2f}，"
                f"体验 {scores.get('experience_value', 0.0):.2f}"
            )
        return (
            f"价格 {scores.get('price', 0.0):.2f}，"
            f"ETA {scores.get('eta', 0.0):.2f}，"
            f"绕路 {scores.get('detour_cost', 0.0):.2f}，"
            f"偏好 {scores.get('preference_match', 0.0):.2f}"
        )

    def _build_basis(
        self,
        *,
        ranked_items: Sequence[RankedCandidate | RankedBundle],
        rejected_reasons: dict[str, list[str]],
        hard_constraints: dict[str, Any],
        kind: Literal["candidate", "bundle"],
    ) -> dict[str, Any]:
        """把排序、拒绝原因和硬约束整理成统一的解释块。"""

        if not ranked_items:
            return {
                "why_selected": [],
                "why_not_others": [],
                "tradeoffs": [],
                "explanation_text": "",
            }

        selected_label = self._selected_label(ranked_items[0], kind=kind)
        why_selected = self._build_why_selected(
            score_breakdown=ranked_items[0].score_breakdown,
            hard_constraints=hard_constraints,
            kind=kind,
            selected_label=selected_label,
        )
        why_not_others = self._build_why_not_others(
            ranked_items=ranked_items,
            rejected_reasons=rejected_reasons,
            kind=kind,
        )
        tradeoffs = self._build_tradeoffs(
            top_item=ranked_items[0],
            runner_up=ranked_items[1] if len(ranked_items) > 1 else None,
            kind=kind,
        )
        explanation_text = self._build_explanation_text(
            kind=kind,
            selected_label=selected_label,
            why_selected=why_selected,
            tradeoffs=tradeoffs,
        )
        return {
            "why_selected": why_selected,
            "why_not_others": why_not_others,
            "tradeoffs": tradeoffs,
            "explanation_text": explanation_text,
        }

    def _selected_label(
        self,
        item: RankedCandidate | RankedBundle,
        *,
        kind: Literal["candidate", "bundle"],
    ) -> str:
        """提取当前选中项的展示标签。"""

        if kind == "bundle":
            return cast(str, item.bundle_id)
        return cast(str, item.label)

    def _build_why_selected(
        self,
        *,
        score_breakdown: dict[str, float],
        hard_constraints: dict[str, Any],
        kind: Literal["candidate", "bundle"],
        selected_label: str,
    ) -> list[str]:
        """把综合得分拆成用户能理解的选择原因。"""

        reasons: list[str] = []
        if hard_constraints.get("budget_max") is not None:
            reasons.append("价格在当前预算内")
        if hard_constraints.get("max_detour_minutes") is not None:
            reasons.append("绕路成本控制在限制内")
        if score_breakdown.get("preference_match", 0.0) >= 0.8:
            reasons.append("更符合当前偏好")
        if score_breakdown.get("eta", 0.0) >= 0.8:
            reasons.append("完成/到达更快")
        if score_breakdown.get("detour_cost", 0.0) >= 0.8:
            reasons.append("路线更顺路")
        if kind == "bundle" and score_breakdown.get("experience_value", 0.0) >= 0.75:
            reasons.append("整体体验收益更高")
        if not reasons:
            reasons.append(f"{selected_label} 的综合权衡最优")
        return reasons

    def _build_why_not_others(
        self,
        *,
        ranked_items: Sequence[RankedCandidate | RankedBundle],
        rejected_reasons: dict[str, list[str]],
        kind: Literal["candidate", "bundle"],
    ) -> list[dict[str, Any]]:
        """把未选项的原因整理成结构化说明。"""

        reasons: list[dict[str, Any]] = []
        item_key = "candidate_id" if kind == "candidate" else "bundle_id"
        for item_id, rejected in rejected_reasons.items():
            reasons.append(
                {
                    item_key: item_id,
                    "reason": " / ".join(rejected) if rejected else "未通过硬约束过滤",
                }
            )

        if len(ranked_items) <= 1:
            return reasons

        selected = ranked_items[0]
        for peer in ranked_items[1:]:
            gap_reason = self._compare_ranked_items(selected.score_breakdown, peer.score_breakdown)
            peer_id = getattr(peer, item_key)
            if not any(entry.get(item_key) == peer_id for entry in reasons):
                reasons.append(
                    {
                        item_key: peer_id,
                        "reason": gap_reason,
                    }
                )
        return reasons

    def _build_tradeoffs(
        self,
        *,
        top_item: RankedCandidate | RankedBundle,
        runner_up: RankedCandidate | RankedBundle | None,
        kind: Literal["candidate", "bundle"],
    ) -> list[str]:
        """总结 top1 与备选方案之间的关键权衡。"""

        if runner_up is None:
            return []

        clauses: list[str] = []
        if top_item.score_breakdown.get("price", 0.0) < runner_up.score_breakdown.get("price", 0.0):
            clauses.append("价格略高，但综合体验更稳")
        elif top_item.score_breakdown.get("price", 0.0) > runner_up.score_breakdown.get("price", 0.0):
            clauses.append("价格更友好，但在其他维度上更均衡")

        if top_item.score_breakdown.get("eta", 0.0) > runner_up.score_breakdown.get("eta", 0.0):
            clauses.append("总 ETA 更短，时间余量更安全")
        if top_item.score_breakdown.get("detour_cost", 0.0) > runner_up.score_breakdown.get("detour_cost", 0.0):
            clauses.append("绕路更少，行程组织更顺")
        if kind == "bundle" and top_item.score_breakdown.get("experience_value", 0.0) > runner_up.score_breakdown.get("experience_value", 0.0):
            clauses.append("整体体验价值更高")
        return list(dict.fromkeys(clauses))

    def _build_explanation_text(
        self,
        *,
        kind: Literal["candidate", "bundle"],
        selected_label: str,
        why_selected: list[str],
        tradeoffs: list[str],
    ) -> str:
        """生成可直接渲染给用户的自然语言解释。"""

        if kind == "bundle":
            prefix = f"推荐 bundle {selected_label}"
        else:
            prefix = f"推荐 {selected_label}"

        if tradeoffs:
            return f"{prefix}：{'；'.join(why_selected)}。权衡上，{'；'.join(tradeoffs)}。"
        return f"{prefix}：{'；'.join(why_selected)}。"

    def _compare_ranked_items(
        self,
        lhs: dict[str, float],
        rhs: dict[str, float],
    ) -> str:
        """比较两个评分拆解，提炼出最明显的差异点。"""

        deltas = {
            "price": lhs.get("price", 0.0) - rhs.get("price", 0.0),
            "eta": lhs.get("eta", 0.0) - rhs.get("eta", 0.0),
            "detour_cost": lhs.get("detour_cost", 0.0) - rhs.get("detour_cost", 0.0),
            "preference_match": lhs.get("preference_match", 0.0) - rhs.get("preference_match", 0.0),
            "experience_value": lhs.get("experience_value", 0.0) - rhs.get("experience_value", 0.0),
        }
        dominant = max(deltas, key=lambda key: abs(deltas[key]))
        if dominant == "price":
            return "价格权衡不如更优项"
        if dominant == "eta":
            return "总 ETA 更长，时间余量更弱"
        if dominant == "detour_cost":
            return "绕路更大，路线不如更优项顺"
        if dominant == "preference_match":
            return "偏好匹配度更弱"
        if dominant == "experience_value":
            return "整体体验价值更低"
        return "综合权衡不如更优项"
