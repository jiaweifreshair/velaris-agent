"""偏好学习器 - 从用户实际选择中学习个性化权重。

核心思想:
- 用户选了不是推荐的那个 → 说明权重需要调整
- chosen 在哪些维度更好 → 那些维度权重应该提高
- 用指数衰减加权 (近期决策权重更大)
- 与场景默认权重混合 (贝叶斯先验)
- 检测决策偏差 (近因偏差、锚定效应、损失厌恶等)
- 分析用户-组织决策对齐度
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.memory.types import (
    AlignmentReport,
    BiasDetection,
    DecisionRecord,
    OrgPolicy,
    UserPreferences,
)
from velaris_agent.scenarios.lifegoal.types import DOMAIN_DIMENSIONS

# 场景默认权重 (先验)
DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "travel": {"price": 0.40, "time": 0.35, "comfort": 0.25},
    "tokencost": {"cost": 0.50, "quality": 0.35, "speed": 0.15},
    "robotclaw": {"safety": 0.40, "eta": 0.25, "cost": 0.20, "compliance": 0.15},
    # 酒店 / 商旅共享决策场景要和 bundle 规划器的评分字段保持一致，
    # 这样用户确认后的回写记录才能在同一组维度上持续学习。
    "hotel_biztravel": {
        "price": 0.20,
        "eta": 0.30,
        "detour_cost": 0.20,
        "preference_match": 0.20,
        "experience_value": 0.10,
    },
    **{domain: dict(weights) for domain, weights in DOMAIN_DIMENSIONS.items()},
}

FALLBACK_WEIGHTS: dict[str, float] = {"quality": 0.5, "cost": 0.3, "speed": 0.2}

SCENARIO_ALIASES: dict[str, str] = {
    "openclaw": "robotclaw",
}

# 时间衰减半衰期 (天)
DECAY_HALF_LIFE_DAYS = 30.0

# 最大学习比例 (防止先验被完全覆盖)
MAX_LEARNING_ALPHA = 0.8

# 达到最大学习比例所需的最小样本数
MIN_SAMPLES_FOR_MAX_ALPHA = 20


class PreferenceLearner:
    """从用户历史选择中学习个性化权重。"""

    def __init__(self, memory: DecisionMemory) -> None:
        """初始化偏好学习器。"""
        self._memory = memory

    def compute_preferences(
        self, user_id: str, scenario: str
    ) -> UserPreferences:
        """计算用户在该场景下的完整偏好画像。"""
        normalized_scenario = self._normalize_scenario(scenario)
        records = self._memory.list_by_user(user_id, scenario=normalized_scenario, limit=100)

        if not records:
            default_w = self._default_weights(normalized_scenario)
            return UserPreferences(
                user_id=user_id,
                scenario=normalized_scenario,
                weights=dict(default_w),
                total_decisions=0,
                confidence=0.0,
            )

        # 计算个性化权重
        weights = self._learn_weights(records, normalized_scenario)

        # 计算行为指标
        total = len(records)
        accepted = sum(
            1 for r in records
            if r.user_choice and r.recommended
            and r.user_choice.get("id") == r.recommended.get("id")
        )
        feedbacks = [r.user_feedback for r in records if r.user_feedback is not None]

        # 识别行为模式
        patterns = self._detect_patterns(records, scenario)

        # 识别决策偏差倾向
        known_biases = [
            b.bias_type
            for b in self.detect_biases(records)
            if b.severity >= 0.5
        ]

        # 置信度: 样本越多越高, 上限 0.95
        confidence = min(total / MIN_SAMPLES_FOR_MAX_ALPHA, 0.95)

        return UserPreferences(
            user_id=user_id,
            scenario=normalized_scenario,
            weights=weights,
            total_decisions=total,
            accepted_recommendation_rate=accepted / total if total > 0 else 0,
            average_satisfaction=(
                sum(feedbacks) / len(feedbacks) if feedbacks else None
            ),
            common_patterns=patterns,
            known_biases=known_biases,
            last_updated=datetime.now(timezone.utc),
            confidence=confidence,
        )

    def get_personalized_weights(
        self, user_id: str, scenario: str
    ) -> dict[str, float]:
        """获取个性化权重 (简化接口)。"""
        prefs = self.compute_preferences(user_id, scenario)
        return prefs.weights

    def _learn_weights(
        self, records: list[DecisionRecord], scenario: str
    ) -> dict[str, float]:
        """从历史选择中学习权重调整。

        算法:
        1. 对每条有反馈的记录, 比较 user_choice 和 recommended 的维度差异
        2. chosen 更好的维度 → 权重 +; chosen 更差的维度 → 权重 -
        3. 用指数衰减加权 (近期决策影响更大)
        4. 与默认权重混合 (贝叶斯先验)
        """
        prior = self._default_weights(scenario)
        dims = list(prior.keys())

        # 收集权重调整信号
        adjustments: dict[str, float] = {d: 0.0 for d in dims}
        total_weight_sum = 0.0
        now = datetime.now(timezone.utc)

        for record in records:
            if not record.user_choice or not record.recommended:
                continue
            if not record.scores:
                continue

            # 时间衰减权重
            age_days = (now - record.created_at).total_seconds() / 86400
            decay = math.exp(-0.693 * age_days / DECAY_HALF_LIFE_DAYS)

            # 找到 chosen 和 recommended 的评分
            chosen_scores = self._find_scores(record.scores, record.user_choice.get("id", ""))
            recommended_scores = self._find_scores(record.scores, record.recommended.get("id", ""))

            if not chosen_scores or not recommended_scores:
                continue

            # 如果选了推荐的, 不需要调整
            if record.user_choice.get("id") == record.recommended.get("id"):
                total_weight_sum += decay
                continue

            # 选了不同的 → 分析差异
            for dim in dims:
                chosen_val = chosen_scores.get(dim, 0.0)
                rec_val = recommended_scores.get(dim, 0.0)
                diff = chosen_val - rec_val
                # diff > 0: chosen 在此维度更好 → 用户更看重此维度 → 权重 +
                adjustments[dim] += diff * decay

            total_weight_sum += decay

        if total_weight_sum <= 0:
            return prior

        # 归一化调整
        learned: dict[str, float] = {}
        for dim in dims:
            learned[dim] = prior[dim] + adjustments[dim] / total_weight_sum

        # 混合先验和学习结果
        sample_size = len([r for r in records if r.user_choice])
        return self._blend(prior, learned, sample_size)

    def _blend(
        self,
        prior: dict[str, float],
        learned: dict[str, float],
        sample_size: int,
    ) -> dict[str, float]:
        """先验 + 学习的混合。

        sample_size 小时偏向先验, 大时偏向学习。
        """
        alpha = min(
            sample_size / MIN_SAMPLES_FOR_MAX_ALPHA, MAX_LEARNING_ALPHA
        )

        blended: dict[str, float] = {}
        for dim in prior:
            blended[dim] = prior[dim] * (1 - alpha) + learned.get(dim, prior[dim]) * alpha

        # 归一化为总和 1.0
        total = sum(max(v, 0.01) for v in blended.values())
        return {dim: round(max(v, 0.01) / total, 4) for dim, v in blended.items()}

    def _find_scores(
        self, scores: list[dict[str, Any]], option_id: str
    ) -> dict[str, float]:
        """从评分列表中找到某选项的维度分数。"""
        for item in scores:
            if item.get("id") == option_id:
                return item.get("scores", {})
        return {}

    def _detect_patterns(
        self, records: list[DecisionRecord], scenario: str
    ) -> list[str]:
        """从历史决策中检测行为模式。"""
        patterns: list[str] = []

        choices_with_feedback = [
            r for r in records if r.user_choice and r.scores
        ]
        if not choices_with_feedback:
            return patterns

        dims = list(self._default_weights(scenario).keys())

        # 分析: 用户总是选某维度最优的选项吗?
        for dim in dims:
            chose_best_count = 0
            for r in choices_with_feedback:
                chosen_id = r.user_choice.get("id", "") if r.user_choice else ""
                best_in_dim = max(r.scores, key=lambda s: s.get("scores", {}).get(dim, 0))
                if best_in_dim.get("id") == chosen_id:
                    chose_best_count += 1

            rate = chose_best_count / len(choices_with_feedback)
            if rate > 0.7:
                patterns.append(f"偏好{dim}最优 ({rate:.0%})")

        # 分析: 接受推荐的比率
        accepted = sum(
            1 for r in records
            if r.user_choice and r.recommended
            and r.user_choice.get("id") == r.recommended.get("id")
        )
        accept_rate = accepted / len(records)
        if accept_rate > 0.8:
            patterns.append(f"高度信任推荐 ({accept_rate:.0%})")
        elif accept_rate < 0.3:
            patterns.append(f"经常选择非推荐项 ({accept_rate:.0%})")

        return patterns

    def _default_weights(self, scenario: str) -> dict[str, float]:
        """解析场景默认权重。

        既支持标准业务场景, 也支持人生目标的六个领域,
        同时兼容历史别名写法, 避免 README、技能文档和运行时场景名不一致时失效。
        """
        normalized_scenario = self._normalize_scenario(scenario)
        return dict(DEFAULT_WEIGHTS.get(normalized_scenario, FALLBACK_WEIGHTS))

    def _normalize_scenario(self, scenario: str) -> str:
        """归一化场景名。

        这样历史兼容名和当前标准名会聚合到同一个偏好画像下,
        避免记忆被拆散。
        """
        lowered = scenario.strip().lower()
        return SCENARIO_ALIASES.get(lowered, lowered)

    # ------------------------------------------------------------------
    # 偏差检测: 识别不合理的决策模式
    # ------------------------------------------------------------------

    def detect_biases(
        self, records: list[DecisionRecord]
    ) -> list[BiasDetection]:
        """从历史决策中检测决策偏差。

        当前支持的偏差类型:
        - recency: 近因偏差 — 过度受最近一次决策影响
        - anchoring: 锚定效应 — 总是选第一个看到的选项
        - loss_aversion: 损失厌恶 — 过度回避风险, 放弃高收益选项
        - sunk_cost: 沉没成本 — 因为之前投入而继续选择同类选项
        """
        biases: list[BiasDetection] = []
        if len(records) < 5:
            return biases

        choices = [r for r in records if r.user_choice]
        if len(choices) < 3:
            return biases

        # 近因偏差: 最近 3 次选择是否高度相似
        recent = choices[:3]
        recent_ids = [r.user_choice.get("id", "") for r in recent if r.user_choice]
        if len(set(recent_ids)) == 1 and len(recent_ids) == 3:
            biases.append(BiasDetection(
                bias_type="recency",
                severity=0.6,
                evidence=f"最近 3 次决策都选了同一选项 ({recent_ids[0]})",
                correction_suggestion="建议重新评估其他候选项, 避免惯性选择",
            ))

        # 锚定效应: 是否总是选排在第一位的选项
        first_option_count = 0
        for r in choices:
            if r.options_discovered and r.user_choice:
                first_id = r.options_discovered[0].get("id", "")
                if r.user_choice.get("id", "") == first_id:
                    first_option_count += 1
        if len(choices) >= 5:
            anchor_rate = first_option_count / len(choices)
            if anchor_rate > 0.7:
                biases.append(BiasDetection(
                    bias_type="anchoring",
                    severity=round(min(anchor_rate, 1.0), 2),
                    evidence=f"在 {len(choices)} 次决策中, {anchor_rate:.0%} 选了第一个出现的选项",
                    correction_suggestion="建议在评分后再做选择, 不要被展示顺序影响",
                ))

        # 损失厌恶: 是否总是选最保守 (最低风险/最低价) 的选项
        dims = list(self._default_weights(records[0].scenario).keys())
        conservative_dims = [d for d in dims if d in ("stability", "safety", "compliance")]
        if conservative_dims:
            conservative_count = 0
            for r in choices:
                if not r.scores or not r.user_choice:
                    continue
                chosen_id = r.user_choice.get("id", "")
                for dim in conservative_dims:
                    best = max(r.scores, key=lambda s: s.get("scores", {}).get(dim, 0))
                    if best.get("id") == chosen_id:
                        conservative_count += 1
                        break
            if len(choices) >= 5:
                conserv_rate = conservative_count / len(choices)
                if conserv_rate > 0.8:
                    biases.append(BiasDetection(
                        bias_type="loss_aversion",
                        severity=round(min(conserv_rate, 1.0), 2),
                        evidence=f"{conserv_rate:.0%} 的决策选了最保守的选项",
                        correction_suggestion="过度规避风险可能错失高收益机会, 建议适当平衡",
                        affected_dimension=conservative_dims[0],
                    ))

        return biases

    # ------------------------------------------------------------------
    # 用户-组织对齐分析
    # ------------------------------------------------------------------

    def compute_alignment(
        self,
        user_id: str,
        org_policy: OrgPolicy,
    ) -> AlignmentReport:
        """分析用户偏好和组织策略之间的对齐度。

        返回匹配度、冲突点和协商空间。
        """
        scenario = self._normalize_scenario(org_policy.scenario)
        user_prefs = self.compute_preferences(user_id, scenario)
        user_w = user_prefs.weights
        org_w = org_policy.weights

        all_dims = set(user_w.keys()) | set(org_w.keys())
        conflicts: list[dict[str, Any]] = []
        synergies: list[str] = []
        total_gap = 0.0

        for dim in all_dims:
            uw = user_w.get(dim, 0.0)
            ow = org_w.get(dim, 0.0)
            gap = abs(uw - ow)
            total_gap += gap

            if gap < 0.1:
                synergies.append(dim)
            elif gap >= 0.2:
                conflicts.append({
                    "dimension": dim,
                    "user_weight": round(uw, 4),
                    "org_weight": round(ow, 4),
                    "gap": round(gap, 4),
                })

        max_possible_gap = len(all_dims) * 1.0
        alignment_score = round(
            max(0.0, 1.0 - total_gap / max_possible_gap) if max_possible_gap > 0 else 1.0,
            4,
        )

        # 协商空间: 冲突维度中, 双方各让一半
        negotiation: dict[str, Any] = {}
        for c in conflicts:
            dim = c["dimension"]
            midpoint = round((c["user_weight"] + c["org_weight"]) / 2, 4)
            negotiation[dim] = {
                "suggested_weight": midpoint,
                "user_concession": round(abs(c["user_weight"] - midpoint), 4),
                "org_concession": round(abs(c["org_weight"] - midpoint), 4),
            }

        return AlignmentReport(
            user_id=user_id,
            org_id=org_policy.org_id,
            scenario=scenario,
            alignment_score=alignment_score,
            conflicts=conflicts,
            synergies=synergies,
            negotiation_space=negotiation,
            created_at=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # 融合权重: 用户偏好 + 组织策略 + 偏差纠正
    # ------------------------------------------------------------------

    def compute_merged_weights(
        self,
        user_id: str,
        scenario: str,
        org_policy: OrgPolicy | None = None,
        bias_corrections: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """计算融合后的决策权重。

        融合顺序:
        1. 用户个性化权重 (从历史学习)
        2. 组织策略权重 (如果有, 按 0.3 比例混入)
        3. 偏差纠正 (如果有, 直接调整)
        4. 归一化
        """
        user_w = self.get_personalized_weights(user_id, scenario)

        # 混入组织权重
        if org_policy and org_policy.weights:
            org_blend_ratio = 0.3
            org_w = org_policy.weights
            for dim in user_w:
                if dim in org_w:
                    user_w[dim] = (
                        user_w[dim] * (1 - org_blend_ratio)
                        + org_w[dim] * org_blend_ratio
                    )

        # 应用偏差纠正
        corrections = bias_corrections or (
            org_policy.bias_corrections if org_policy else {}
        )
        if corrections:
            for dim, adjustment in corrections.items():
                if dim in user_w:
                    user_w[dim] = max(0.01, user_w[dim] + adjustment)

        # 归一化
        total = sum(max(v, 0.01) for v in user_w.values())
        return {dim: round(max(v, 0.01) / total, 4) for dim, v in user_w.items()}
