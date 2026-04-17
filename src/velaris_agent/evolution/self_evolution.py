"""自进化评估引擎。

核心思想：
- 从真实决策结果中识别“推荐偏差”与“满意度下滑”；
- 自动给出下一轮可执行的优化动作；
- 支持周期性落盘，形成可追踪的改进历史。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from velaris_agent.evolution.types import EvolutionAction, SelfEvolutionReport
from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.memory.preference_learner import PreferenceLearner
from velaris_agent.memory.types import DecisionRecord

SELF_EVOLUTION_REVIEW_JOB_TYPE = "self_evolution_review"


def _now() -> datetime:
    """返回 UTC 当前时间，保持报告时间统一。"""
    return datetime.now(timezone.utc)


def build_self_evolution_review_job_payload(
    *,
    user_id: str,
    scenario: str,
    window: int,
    persist_report: bool,
    report_dir: str | Path | None = None,
    decision_memory_dir: str | Path | None = None,
) -> dict[str, Any]:
    """构造 self_evolution_review 队列任务 payload。

    payload 只保留 worker 执行所需的最小字段，避免把整个上下文对象塞进队列。
    """

    payload: dict[str, Any] = {
        "user_id": user_id,
        "scenario": scenario,
        "window": window,
        "persist_report": persist_report,
    }
    if report_dir is not None:
        payload["report_dir"] = str(report_dir)
    if decision_memory_dir is not None:
        payload["decision_memory_dir"] = str(decision_memory_dir)
    return payload


def run_self_evolution_review_job(
    *,
    postgres_dsn: str,
    payload: dict[str, Any],
) -> SelfEvolutionReport:
    """执行一条 self_evolution_review 队列任务。

    worker 入口统一从 payload 中恢复最小参数，
    并复用现有 `SelfEvolutionEngine.review()` 逻辑，避免重复实现统计规则。
    """

    from velaris_agent.persistence.factory import build_decision_memory

    memory = build_decision_memory(
        postgres_dsn=postgres_dsn,
        base_dir=payload.get("decision_memory_dir"),
    )
    engine = SelfEvolutionEngine(
        memory=memory,
        report_dir=payload.get("report_dir"),
    )
    return engine.review(
        user_id=str(payload["user_id"]),
        scenario=str(payload["scenario"]),
        window=max(3, int(payload.get("window", 20))),
        persist_report=bool(payload.get("persist_report", True)),
    )


class SelfEvolutionEngine:
    """对历史决策进行回顾并生成优化建议。"""

    def __init__(
        self,
        memory: DecisionMemory,
        *,
        report_dir: str | Path | None = None,
    ) -> None:
        """初始化自进化引擎。"""
        self._memory = memory
        if report_dir is None:
            report_dir = Path.home() / ".velaris" / "evolution" / "reports"
        self._report_dir = Path(report_dir)

    def review(
        self,
        *,
        user_id: str,
        scenario: str,
        window: int = 20,
        persist_report: bool = True,
    ) -> SelfEvolutionReport:
        """生成一次自进化报告。"""
        records = self._memory.list_by_user(user_id=user_id, scenario=scenario, limit=window)
        accepted_rate = self._compute_accept_rate(records)
        avg_feedback = self._compute_avg_feedback(records)
        drift = self._compute_drift(records)
        actions = self._build_actions(
            user_id=user_id,
            scenario=scenario,
            sample_size=len(records),
            accepted_rate=accepted_rate,
            avg_feedback=avg_feedback,
            drift=drift,
        )

        report = SelfEvolutionReport(
            user_id=user_id,
            scenario=scenario,
            generated_at=_now(),
            sample_size=len(records),
            accepted_recommendation_rate=accepted_rate,
            average_feedback=avg_feedback,
            top_preference_drift=drift,
            actions=actions,
        )
        if not persist_report:
            return report
        saved_path = self._save_report(report)
        return report.model_copy(update={"report_path": str(saved_path)})

    def _compute_accept_rate(self, records: list[DecisionRecord]) -> float | None:
        """计算推荐接受率。"""
        comparable = [
            r
            for r in records
            if r.user_choice is not None and r.recommended is not None
        ]
        if not comparable:
            return None
        accepted = sum(
            1
            for r in comparable
            if r.user_choice and r.recommended
            and r.user_choice.get("id") == r.recommended.get("id")
        )
        return round(accepted / len(comparable), 4)

    def _compute_avg_feedback(self, records: list[DecisionRecord]) -> float | None:
        """计算平均满意度。"""
        feedbacks = [r.user_feedback for r in records if r.user_feedback is not None]
        if not feedbacks:
            return None
        return round(sum(feedbacks) / len(feedbacks), 4)

    def _compute_drift(self, records: list[DecisionRecord]) -> dict[str, float]:
        """计算维度偏好漂移。

        若用户持续选择“非推荐项”，则比较 chosen 与 recommended 的维度差值，
        作为下一轮权重调整的信号。
        """
        drift: dict[str, float] = {}
        signal_count = 0

        for record in records:
            if not record.user_choice or not record.recommended:
                continue
            if record.user_choice.get("id") == record.recommended.get("id"):
                continue
            chosen_scores = self._find_scores(record.scores, str(record.user_choice.get("id", "")))
            rec_scores = self._find_scores(record.scores, str(record.recommended.get("id", "")))
            if not chosen_scores or not rec_scores:
                continue
            signal_count += 1
            for dimension in set(chosen_scores) | set(rec_scores):
                delta = float(chosen_scores.get(dimension, 0.0)) - float(
                    rec_scores.get(dimension, 0.0)
                )
                drift[dimension] = drift.get(dimension, 0.0) + delta

        if signal_count == 0:
            return {}
        normalized = {
            key: round(value / signal_count, 4)
            for key, value in drift.items()
            if abs(value / signal_count) >= 0.01
        }
        sorted_items = sorted(
            normalized.items(),
            key=lambda item: abs(item[1]),
            reverse=True,
        )
        return dict(sorted_items[:5])

    def _build_actions(
        self,
        *,
        user_id: str,
        scenario: str,
        sample_size: int,
        accepted_rate: float | None,
        avg_feedback: float | None,
        drift: dict[str, float],
    ) -> list[EvolutionAction]:
        """根据指标生成行动建议。"""
        actions: list[EvolutionAction] = []

        if sample_size < 3:
            actions.append(
                EvolutionAction(
                    action_id="collect_more_samples",
                    priority="low",
                    title="样本不足，先扩充反馈数据",
                    reason="当前决策样本过少，暂不适合做强权重迁移。",
                    details={"sample_size": str(sample_size)},
                )
            )
            return actions

        if accepted_rate is not None and accepted_rate < 0.5:
            actions.append(
                EvolutionAction(
                    action_id="tighten_recall_pipeline",
                    priority="high",
                    title="提高推荐命中率",
                    reason="用户经常选择非推荐项，说明召回或评分逻辑偏离真实偏好。",
                    details={"accepted_rate": accepted_rate},
                )
            )

        if avg_feedback is not None and avg_feedback < 3.5:
            actions.append(
                EvolutionAction(
                    action_id="improve_explanation_quality",
                    priority="high",
                    title="强化解释与风险披露",
                    reason="满意度偏低，建议补充 trade-off、风险与回顾节点。",
                    details={"average_feedback": avg_feedback},
                )
            )

        if drift:
            learner = PreferenceLearner(self._memory)
            learned_weights = learner.get_personalized_weights(user_id=user_id, scenario=scenario)
            top_dimension, top_delta = next(iter(drift.items()))
            actions.append(
                EvolutionAction(
                    action_id="adjust_weight_with_drift",
                    priority="medium",
                    title=f"关注维度漂移：{top_dimension}",
                    reason="用户近期选择行为显示偏好发生变化，建议在评分时显式提升该维度权重。",
                    details={
                        "top_dimension": top_dimension,
                        "drift_delta": top_delta,
                        "learned_weight": learned_weights.get(top_dimension, 0.0),
                    },
                )
            )

        if not actions:
            actions.append(
                EvolutionAction(
                    action_id="keep_strategy",
                    priority="low",
                    title="维持当前策略并继续观测",
                    reason="当前推荐接受率和满意度稳定，无需立即改动。",
                    details={},
                )
            )
        return actions

    def _find_scores(
        self, scores: list[dict[str, Any]], option_id: str
    ) -> dict[str, float]:
        """提取某个选项的维度评分。"""
        for item in scores:
            if item.get("id") != option_id:
                continue
            data = item.get("scores", {})
            if isinstance(data, dict):
                return {str(k): float(v) for k, v in data.items()}
        return {}

    def _save_report(self, report: SelfEvolutionReport) -> Path:
        """持久化报告到 JSON 文件。"""
        self._report_dir.mkdir(parents=True, exist_ok=True)
        stamp = report.generated_at.strftime("%Y%m%dT%H%M%SZ")
        filename = f"evo-{stamp}-{report.user_id}-{report.scenario}.json"
        path = self._report_dir / filename
        path.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path
