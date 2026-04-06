"""偏好学习器 - 从用户实际选择中学习个性化权重。

核心思想:
- 用户选了不是推荐的那个 → 说明权重需要调整
- chosen 在哪些维度更好 → 那些维度权重应该提高
- 用指数衰减加权 (近期决策权重更大)
- 与场景默认权重混合 (贝叶斯先验)
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.memory.types import DecisionRecord, UserPreferences
from velaris_agent.scenarios.lifegoal.types import DOMAIN_DIMENSIONS

# 场景默认权重 (先验)
DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "travel": {"price": 0.40, "time": 0.35, "comfort": 0.25},
    "tokencost": {"cost": 0.50, "quality": 0.35, "speed": 0.15},
    "robotclaw": {"safety": 0.40, "eta": 0.25, "cost": 0.20, "compliance": 0.15},
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
