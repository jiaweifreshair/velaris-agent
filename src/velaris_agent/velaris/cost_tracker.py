"""DecisionCostTracker — 决策成本追踪与 ROI 报告。

追踪每次决策执行的 token 消耗、延迟、模型等指标，
按场景/时间段生成 ROI 报告，为 DynamicRouter 提供成本感知数据。

核心能力：
1. track(): 记录每次执行的成本
2. roi(): 按场景/时间段计算 ROI
3. budget_status(): 查询当前预算使用状况
4. cost_by_scenario(): 按场景聚合成本
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any


@dataclass(frozen=True)
class CostRecord:
    """单次决策执行的成本记录。"""

    execution_id: str
    scenario: str
    model_tier: str
    token_input: int
    token_output: int
    latency_ms: float
    timestamp: str            # ISO 8601
    session_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def token_total(self) -> int:
        """总 token 消耗。"""
        return self.token_input + self.token_output

    @property
    def cost_estimate(self) -> float:
        """成本估算（基于模型等级的相对成本）。"""
        tier_rates = {"premium": 1.0, "standard": 0.3, "economy": 0.05}
        rate = tier_rates.get(self.model_tier, 0.3)
        return self.token_total * rate / 1000.0


@dataclass(frozen=True)
class ROIReport:
    """ROI 报告。"""

    scenario: str
    period_days: int
    total_executions: int
    total_token_input: int
    total_token_output: int
    total_cost_estimate: float
    avg_latency_ms: float
    avg_token_per_execution: float
    quality_score_avg: float | None     # 可选：质量评分
    cost_efficiency: float              # 成本效率（output_tokens / cost）

    def to_dict(self) -> dict[str, Any]:
        """转换为 JSON 友好的字典。"""
        return asdict(self)


@dataclass(frozen=True)
class BudgetStatus:
    """预算使用状况。"""

    total_budget: float
    consumed: float
    remaining: float
    utilization: float       # 0.0 ~ 1.0
    projected_depletion_date: str | None  # ISO 8601 或 None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _AggregationBucket:
    """聚合桶，用于按场景统计。"""

    token_input: int = 0
    token_output: int = 0
    cost_estimate: float = 0.0
    latency_ms: float = 0.0
    count: int = 0
    quality_scores: list[float] = field(default_factory=list)


class DecisionCostTracker:
    """决策成本追踪器。

    使用方式：
    1. 创建追踪器：tracker = DecisionCostTracker(total_budget=1000000)
    2. 每次执行后记录：tracker.track(execution_id, scenario, ...)
    3. 查询 ROI：report = tracker.roi("travel", period_days=30)
    4. 查询预算：status = tracker.budget_status()

    存储设计：
    - 内存存储（默认），适合单次会话
    - 可通过子类覆盖 _store/_load 实现持久化
    """

    def __init__(self, total_budget: float = 0.0) -> None:
        self._total_budget = total_budget
        self._records: list[CostRecord] = []

    # ── 核心接口 ─────────────────────────────────────────────

    def track(
        self,
        execution_id: str,
        scenario: str,
        token_input: int,
        token_output: int,
        model_tier: str = "standard",
        latency_ms: float = 0.0,
        session_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> CostRecord:
        """记录一次决策执行的成本。

        Args:
            execution_id: 执行 ID
            scenario: 场景名
            token_input: 输入 token 数
            token_output: 输出 token 数
            model_tier: 模型等级
            latency_ms: 执行延迟（毫秒）
            session_id: 会话 ID
            metadata: 额外元数据

        Returns:
            CostRecord 记录
        """
        record = CostRecord(
            execution_id=execution_id,
            scenario=scenario,
            model_tier=model_tier,
            token_input=max(0, token_input),
            token_output=max(0, token_output),
            latency_ms=max(0.0, latency_ms),
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            metadata=metadata or {},
        )
        self._records.append(record)
        return record

    def roi(self, scenario: str | None = None, period_days: int = 30) -> ROIReport:
        """计算 ROI 报告。

        Args:
            scenario: 场景名（None 表示所有场景）
            period_days: 统计时间段（天）

        Returns:
            ROIReport 报告
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        filtered = [
            r for r in self._records
            if (scenario is None or r.scenario == scenario)
            and datetime.fromisoformat(r.timestamp) >= cutoff
        ]

        if not filtered:
            return ROIReport(
                scenario=scenario or "all",
                period_days=period_days,
                total_executions=0,
                total_token_input=0,
                total_token_output=0,
                total_cost_estimate=0.0,
                avg_latency_ms=0.0,
                avg_token_per_execution=0.0,
                quality_score_avg=None,
                cost_efficiency=0.0,
            )

        total_in = sum(r.token_input for r in filtered)
        total_out = sum(r.token_output for r in filtered)
        total_cost = sum(r.cost_estimate for r in filtered)
        avg_latency = sum(r.latency_ms for r in filtered) / len(filtered)
        avg_token = (total_in + total_out) / len(filtered)

        # 质量评分（从 metadata 中收集）
        quality_scores: list[float] = []
        for r in filtered:
            if "quality_score" in r.metadata:
                quality_scores.append(float(r.metadata["quality_score"]))
        quality_avg = sum(quality_scores) / len(quality_scores) if quality_scores else None

        # 成本效率：每单位成本产出的 token
        cost_efficiency = total_out / total_cost if total_cost > 0 else 0.0

        return ROIReport(
            scenario=scenario or "all",
            period_days=period_days,
            total_executions=len(filtered),
            total_token_input=total_in,
            total_token_output=total_out,
            total_cost_estimate=total_cost,
            avg_latency_ms=round(avg_latency, 1),
            avg_token_per_execution=round(avg_token, 1),
            quality_score_avg=round(quality_avg, 3) if quality_avg is not None else None,
            cost_efficiency=round(cost_efficiency, 3),
        )

    def budget_status(self) -> BudgetStatus:
        """查询当前预算使用状况。"""
        consumed = sum(r.cost_estimate for r in self._records)
        remaining = max(0.0, self._total_budget - consumed)
        utilization = consumed / self._total_budget if self._total_budget > 0 else 0.0

        # 简单预测耗尽时间：基于最近消耗速率
        projected_date: str | None = None
        if len(self._records) >= 2 and self._total_budget > 0 and remaining > 0:
            first_ts = datetime.fromisoformat(self._records[0].timestamp)
            last_ts = datetime.fromisoformat(self._records[-1].timestamp)
            elapsed_hours = max((last_ts - first_ts).total_seconds() / 3600, 0.001)
            rate_per_hour = consumed / elapsed_hours
            if rate_per_hour > 0:
                hours_to_deplete = remaining / rate_per_hour
                depletion_dt = datetime.now(timezone.utc) + timedelta(hours=hours_to_deplete)
                projected_date = depletion_dt.isoformat()

        return BudgetStatus(
            total_budget=self._total_budget,
            consumed=round(consumed, 3),
            remaining=round(remaining, 3),
            utilization=round(min(utilization, 1.0), 4),
            projected_depletion_date=projected_date,
        )

    def cost_by_scenario(self, period_days: int = 30) -> dict[str, dict[str, Any]]:
        """按场景聚合成本统计。

        Returns:
            {scenario_name: {executions, total_cost, avg_latency, ...}}
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        filtered = [
            r for r in self._records
            if datetime.fromisoformat(r.timestamp) >= cutoff
        ]

        buckets: dict[str, _AggregationBucket] = {}
        for r in filtered:
            if r.scenario not in buckets:
                buckets[r.scenario] = _AggregationBucket()
            b = buckets[r.scenario]
            b.token_input += r.token_input
            b.token_output += r.token_output
            b.cost_estimate += r.cost_estimate
            b.latency_ms += r.latency_ms
            b.count += 1
            if "quality_score" in r.metadata:
                b.quality_scores.append(float(r.metadata["quality_score"]))

        result: dict[str, dict[str, Any]] = {}
        for name, b in buckets.items():
            result[name] = {
                "executions": b.count,
                "total_token_input": b.token_input,
                "total_token_output": b.token_output,
                "total_cost_estimate": round(b.cost_estimate, 3),
                "avg_latency_ms": round(b.latency_ms / b.count, 1) if b.count else 0.0,
                "avg_token_per_execution": round((b.token_input + b.token_output) / b.count, 1) if b.count else 0.0,
                "quality_score_avg": round(sum(b.quality_scores) / len(b.quality_scores), 3) if b.quality_scores else None,
            }
        return result

    # ── 查询接口 ─────────────────────────────────────────────

    def get_records(
        self,
        scenario: str | None = None,
        model_tier: str | None = None,
        limit: int = 100,
    ) -> list[CostRecord]:
        """查询成本记录。"""
        result = self._records
        if scenario is not None:
            result = [r for r in result if r.scenario == scenario]
        if model_tier is not None:
            result = [r for r in result if r.model_tier == model_tier]
        return result[-limit:]

    @property
    def total_consumed(self) -> float:
        """总消耗成本估算。"""
        return sum(r.cost_estimate for r in self._records)

    @property
    def record_count(self) -> int:
        """记录总数。"""
        return len(self._records)

    def reset(self) -> None:
        """重置所有记录（主要用于测试）。"""
        self._records.clear()
