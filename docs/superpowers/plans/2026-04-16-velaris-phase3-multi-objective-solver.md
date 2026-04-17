# Velaris Phase 3 Multi-Objective Solver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `procurement` decision graph 从“硬约束 + 全量 weighted-sum 排序”升级为“Feasibility 可行域 + Pareto frontier + frontier 内 operating point 选择”，同时保持 legacy `biz/engine.py` 协议兼容。

**Architecture:** 继续沿用单体内核，不引入新中间件。Phase 3 只改 `src/velaris_agent/decision/` 与 `procurement` 兼容壳层：把硬约束过滤从 `NormalizationOp` 下沉到新的 `FeasibilityOp`，新增 `ParetoFrontierOp` 负责非支配筛选，再由 `OperatingPointSelectorOp` 只在 Pareto 前沿内做 operating point 选择，并把 dominated feasible options 追加到 ranked tail，确保 legacy `options` 列表不丢项。

**Tech Stack:** Python 3.11, Pydantic 2, pytest, existing decision graph core, `./scripts/run_pytest.sh`

---

## Current Baseline

- `src/velaris_agent/decision/operators/normalization_op.py` 当前同时承担“schema 标准化 + 硬约束过滤 + cost/delivery 归一化”三类职责，这与 Phase 3 目标里的 `FeasibilityOp` 分层不一致。
- `src/velaris_agent/decision/operators/optimization_op.py` 当前仍以 weighted-sum 对全部 feasible options 排序；虽然已经支持 payload / orchestrator 注入 `decision_weights`，但还没有 Pareto frontier 概念。
- `src/velaris_agent/decision/context.py` 与 `src/velaris_agent/decision/graph.py` 还没有 `pareto_frontier / dominated_options / operating_point_summary` 等运行期字段。
- `src/velaris_agent/biz/engine.py` 目前通过 `graph_result.ranked_options` 回填 legacy `options`；如果 Phase 3 只返回 frontier，会导致 dominated feasible options 从旧协议里消失，这是本阶段必须避免的回退。
- `src/velaris_agent/memory/types.py` 已有统一指标注册表与 `PreferenceDirection`，可直接复用来定义 Pareto 比较维度，无需新建第二套方向配置。
- 用户已确认 `Phase 3` 当前只需要“产出并评审详细计划”，本轮不进入实现。

## File Structure

### New Files

- Create: `src/velaris_agent/decision/operators/feasibility_op.py` — 负责硬约束过滤、可行域划分与 lower-is-better 指标在 feasible set 上的归一化
- Create: `src/velaris_agent/decision/operators/pareto_frontier_op.py` — 负责 Pareto frontier / dominated feasible options 识别
- Create: `src/velaris_agent/decision/operators/operating_point_selector_op.py` — 负责 frontier 内 operating point 选择与 dominated tail 拼接
- Create: `tests/test_decision/test_multi_objective_solver.py` — 覆盖 feasibility、Pareto frontier、operating point 的决策核心回归

### Existing Files To Modify

- Modify: `src/velaris_agent/decision/context.py` — 扩充 frontier / operating point 运行期 contract
- Modify: `src/velaris_agent/decision/graph.py` — 装配新算子并回填新增结果字段
- Modify: `src/velaris_agent/decision/operators/registry.py` — 将 graph 顺序升级为 feasibility + pareto + operating point
- Modify: `src/velaris_agent/decision/operators/normalization_op.py` — 回归“只做 schema 标准化”的单一职责
- Modify: `src/velaris_agent/decision/operators/explanation_op.py` — 输出 frontier-aware explanation
- Modify: `src/velaris_agent/decision/operators/optimization_op.py` — 降级为 shared weighted-sum helper，供 `OperatingPointSelectorOp` 复用
- Modify: `src/velaris_agent/biz/engine.py` — 保持 legacy adapter 返回完整 feasible `options`，并透出 frontier 选择结果
- Modify: `tests/test_decision/test_operator_registry.py` — 更新默认 graph 顺序断言
- Modify: `tests/test_decision/test_procurement_operator_graph.py` — 更新 Phase 3 集成断言
- Modify: `tests/test_biz/test_engine_operator_graph.py` — 覆盖 legacy 协议下 dominated feasible options 仍被保留
- Modify: `tests/test_biz/test_engine_procurement.py` — 覆盖 frontier explanation 与推荐稳定性
- Modify: `tests/test_biz/test_orchestrator.py` — 覆盖新增 operator trace 顺序与 audit summary

## Guardrails

- Phase 3 仍然只迁移 `procurement`；`travel / tokencost / robotclaw / lifegoal` 不改协议、不接新 graph。
- `FeasibilityOp` 是 Phase 3 的唯一硬约束裁剪入口；`NormalizationOp` 不能继续持有 accepted/rejected 的业务判断。
- `ParetoFrontierOp` 只在 `feasible_options` 上运行，不能把 rejected options 再拉回来比较。
- `OperatingPointSelectorOp` 可以继续复用 weighted-sum，但只能在 Pareto frontier 内选 operating point；不能再对全量 feasible set 做唯一最终排序。
- legacy `options` 列表必须继续返回完整 feasible options；frontier options 在前，dominated feasible options 只能排在 tail，不能消失。
- `accepted_option_ids` 必须表示“通过硬约束的全部 options”，不能在 Phase 3 退化成仅 frontier ids。
- explanation 与 audit trace 只能新增结构化 frontier 信息，不能删除既有 `recommended / summary / audit_trace / operator_trace` 字段。
- 本阶段不引入数据库 schema 变更，不写 `decision_frontier` 持久化表；那是 Phase 5 范围。

---

### Task 1: 引入 Feasibility contract，并把硬约束过滤从 NormalizationOp 拆出去

**Files:**
- Modify: `src/velaris_agent/decision/context.py`
- Modify: `src/velaris_agent/decision/operators/normalization_op.py`
- Create: `src/velaris_agent/decision/operators/feasibility_op.py`
- Create: `tests/test_decision/test_multi_objective_solver.py`

- [ ] **Step 1: 先写失败测试，锁定 Normalization / Feasibility 的职责边界**

```python
from velaris_agent.decision.context import DecisionExecutionContext
from velaris_agent.decision.operators.feasibility_op import FeasibilityOp
from velaris_agent.decision.operators.intent_op import IntentOp
from velaris_agent.decision.operators.normalization_op import NormalizationOp
from velaris_agent.decision.operators.option_discovery_op import OptionDiscoveryOp


def _build_procurement_context(
    *,
    options: list[dict[str, object]],
    decision_weights: dict[str, float] | None = None,
    budget_max: int = 250000,
    require_compliance: bool = True,
    max_delivery_days: int | None = None,
) -> DecisionExecutionContext:
    return DecisionExecutionContext(
        scenario="procurement",
        query="比较供应商并输出推荐。",
        payload={
            "budget_max": budget_max,
            "require_compliance": require_compliance,
            "max_delivery_days": max_delivery_days,
            "decision_weights": decision_weights or {},
            "options": options,
        },
        constraints={},
        decision_weights=decision_weights or {},
    )


def test_normalization_op_only_outputs_normalized_options() -> None:
    context = _build_procurement_context(
        budget_max=130000,
        max_delivery_days=10,
        options=[
            {
                "id": "vendor-a",
                "label": "供应商 A",
                "price_cny": 118000,
                "delivery_days": 9,
                "quality_score": 0.90,
                "compliance_score": 0.98,
                "risk_score": 0.10,
                "available": True,
            },
            {
                "id": "vendor-b",
                "label": "供应商 B",
                "price_cny": 145000,
                "delivery_days": 12,
                "quality_score": 0.86,
                "compliance_score": 0.82,
                "risk_score": 0.14,
                "available": True,
            },
        ],
    )

    context = IntentOp().run(context)
    context = OptionDiscoveryOp().run(context)
    context = NormalizationOp().run(context)

    assert [item.option_id for item in context.normalized_options] == ["vendor-a", "vendor-b"]
    assert context.accepted_options == []
    assert context.rejected_options == []


def test_feasibility_op_owns_hard_constraint_filtering() -> None:
    context = _build_procurement_context(
        budget_max=130000,
        max_delivery_days=10,
        options=[
            {
                "id": "vendor-a",
                "label": "供应商 A",
                "price_cny": 118000,
                "delivery_days": 9,
                "quality_score": 0.90,
                "compliance_score": 0.98,
                "risk_score": 0.10,
                "available": True,
            },
            {
                "id": "vendor-b",
                "label": "供应商 B",
                "price_cny": 145000,
                "delivery_days": 12,
                "quality_score": 0.86,
                "compliance_score": 0.82,
                "risk_score": 0.14,
                "available": True,
            },
        ],
    )

    context = IntentOp().run(context)
    context = OptionDiscoveryOp().run(context)
    context = NormalizationOp().run(context)
    context = FeasibilityOp().run(context)

    assert [item.option_id for item in context.accepted_options] == ["vendor-a"]
    assert [item.option_id for item in context.rejected_options] == ["vendor-b"]
    assert context.rejection_reasons["vendor-b"] == [
        "budget_exceeded",
        "delivery_exceeds_limit",
        "compliance_below_threshold",
    ]
```

- [ ] **Step 2: 运行测试，确认 Phase 2 代码还没有 feasibility 分层**

Run:
```bash
./scripts/run_pytest.sh tests/test_decision/test_multi_objective_solver.py -q
```

Expected:
- `ModuleNotFoundError: No module named 'velaris_agent.decision.operators.feasibility_op'`
- 或 `NormalizationOp` 仍然直接写入 `accepted_options`

- [ ] **Step 3: 扩充 context / result contract，为 feasible set 与 frontier 留位置**

```python
# src/velaris_agent/decision/context.py
@dataclass
class DecisionGraphResult:
    scenario: str
    ranked_options: list[DecisionOptionSchema] = field(default_factory=list)
    accepted_option_ids: list[str] = field(default_factory=list)
    rejected_option_ids: list[str] = field(default_factory=list)
    rejection_reasons: dict[str, list[str]] = field(default_factory=dict)
    pareto_frontier_ids: list[str] = field(default_factory=list)
    dominated_option_ids: list[str] = field(default_factory=list)
    frontier_metrics: list[dict[str, Any]] = field(default_factory=list)
    operating_point_summary: dict[str, Any] = field(default_factory=dict)
    recommended_option_id: str | None = None
    explanation: str = ""
    warnings: list[str] = field(default_factory=list)
    operator_traces: list[OperatorTraceRecord] = field(default_factory=list)


@dataclass
class DecisionExecutionContext:
    scenario: str
    query: str
    payload: dict[str, Any]
    constraints: dict[str, Any]
    intent: dict[str, Any] = field(default_factory=dict)
    raw_options: list[dict[str, Any]] = field(default_factory=list)
    normalized_options: list[DecisionOptionSchema] = field(default_factory=list)
    accepted_options: list[DecisionOptionSchema] = field(default_factory=list)
    rejected_options: list[DecisionOptionSchema] = field(default_factory=list)
    rejection_reasons: dict[str, list[str]] = field(default_factory=dict)
    pareto_frontier: list[DecisionOptionSchema] = field(default_factory=list)
    dominated_options: list[DecisionOptionSchema] = field(default_factory=list)
    frontier_metrics: list[dict[str, Any]] = field(default_factory=list)
    operating_point_summary: dict[str, Any] = field(default_factory=dict)
    decision_weights: dict[str, float] = field(default_factory=dict)
    stakeholder_context: dict[str, Any] = field(default_factory=dict)
    ranked_options: list[DecisionOptionSchema] = field(default_factory=list)
    recommended_option_id: str | None = None
    negotiation_summary: dict[str, Any] = field(default_factory=dict)
    bias_summary: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    warnings: list[str] = field(default_factory=list)
    operator_traces: list[OperatorTraceRecord] = field(default_factory=list)
```

- [ ] **Step 4: 让 NormalizationOp 回归单一职责，并新增 FeasibilityOp**

```python
# src/velaris_agent/decision/operators/normalization_op.py
class NormalizationOp:
    spec = OperatorSpec("normalization")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        normalized: list[DecisionOptionSchema] = []
        for option in context.raw_options:
            evidence_refs = [str(item) for item in option.get("evidence_refs", [])]
            normalized.append(
                DecisionOptionSchema(
                    option_id=str(option["id"]),
                    scenario=context.scenario,
                    label=str(option["label"]),
                    metrics=[
                        DecisionOptionMetric(metric_id="cost", raw_value=option["price_cny"], normalized_score=0.0, evidence_refs=list(evidence_refs)),
                        DecisionOptionMetric(metric_id="quality", raw_value=option["quality_score"], normalized_score=float(option["quality_score"]), evidence_refs=list(evidence_refs)),
                        DecisionOptionMetric(metric_id="delivery", raw_value=option["delivery_days"], normalized_score=0.0, evidence_refs=list(evidence_refs)),
                        DecisionOptionMetric(metric_id="compliance", raw_value=option["compliance_score"], normalized_score=float(option["compliance_score"]), evidence_refs=list(evidence_refs)),
                        DecisionOptionMetric(metric_id="risk", raw_value=option["risk_score"], normalized_score=1 - float(option["risk_score"]), evidence_refs=list(evidence_refs)),
                    ],
                    metadata={"raw_option": dict(option), "available": bool(option.get("available", True))},
                )
            )
        context.normalized_options = normalized
        context.accepted_options = []
        context.rejected_options = []
        context.rejection_reasons = {}
        context.operator_traces.append(
            OperatorTraceRecord(
                operator_id=self.spec.operator_id,
                operator_version=self.spec.operator_version,
                input_schema_version=self.spec.input_schema_version,
                output_schema_version=self.spec.output_schema_version,
                confidence=1.0,
            )
        )
        return context
```

```python
# src/velaris_agent/decision/operators/feasibility_op.py
class FeasibilityOp:
    spec = OperatorSpec("feasibility")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        accepted: list[DecisionOptionSchema] = []
        rejected: list[DecisionOptionSchema] = []
        rejection_reasons: dict[str, list[str]] = {}

        for option in context.normalized_options:
            raw_option = dict(option.metadata.get("raw_option", {}))
            reasons = _collect_rejection_reasons(option=raw_option, intent=context.intent)
            if reasons:
                rejected.append(option)
                rejection_reasons[option.option_id] = reasons
            else:
                accepted.append(option)

        _normalize_lower_is_better_metrics(accepted, metric_ids=["cost", "delivery"])
        context.accepted_options = accepted
        context.rejected_options = rejected
        context.rejection_reasons = rejection_reasons
        context.operator_traces.append(
            OperatorTraceRecord(
                operator_id=self.spec.operator_id,
                operator_version=self.spec.operator_version,
                input_schema_version=self.spec.input_schema_version,
                output_schema_version=self.spec.output_schema_version,
                confidence=1.0 if accepted else 0.0,
                warnings=["no_feasible_option"] if not accepted else [],
            )
        )
        return context


def _collect_rejection_reasons(
    *,
    option: dict[str, object],
    intent: dict[str, object],
) -> list[str]:
    reasons: list[str] = []
    if not bool(option.get("available", True)):
        reasons.append("option_unavailable")

    budget_max = intent.get("budget_max")
    if budget_max is not None and float(option.get("price_cny", 0) or 0) > float(budget_max):
        reasons.append("budget_exceeded")

    max_delivery_days = intent.get("max_delivery_days")
    if max_delivery_days is not None and float(
        option.get("delivery_days", 0) or 0
    ) > float(max_delivery_days):
        reasons.append("delivery_exceeds_limit")

    if bool(intent.get("require_compliance", True)) and float(
        option.get("compliance_score", 0) or 0
    ) < 0.9:
        reasons.append("compliance_below_threshold")

    return reasons


def _normalize_lower_is_better_metrics(
    options: list[DecisionOptionSchema],
    *,
    metric_ids: list[str],
) -> None:
    for metric_id in metric_ids:
        samples = _collect_metric_samples(options, metric_id)
        for option in options:
            metric = next((item for item in option.metrics if item.metric_id == metric_id), None)
            if metric is None:
                continue
            metric.normalized_score = _inverse_score(float(metric.raw_value or 0), samples)


def _collect_metric_samples(
    options: list[DecisionOptionSchema],
    metric_id: str,
) -> list[float]:
    samples: list[float] = []
    for option in options:
        metric = next((item for item in option.metrics if item.metric_id == metric_id), None)
        if metric is None:
            continue
        samples.append(float(metric.raw_value or 0))
    return samples


def _inverse_score(value: float, samples: list[float]) -> float:
    if not samples:
        return 0.0
    minimum = min(samples)
    maximum = max(samples)
    if maximum == minimum:
        return 1.0
    return max(0.0, min(1.0, (maximum - value) / (maximum - minimum)))
```

- [ ] **Step 5: 跑 Task 1 验证**

Run:
```bash
./scripts/run_pytest.sh tests/test_decision/test_multi_objective_solver.py -q
```

Expected:
- `2 passed`
- `NormalizationOp` 不再负责 accepted/rejected

- [ ] **Step 6: 提交 Task 1**

```bash
git add src/velaris_agent/decision/context.py src/velaris_agent/decision/operators/normalization_op.py src/velaris_agent/decision/operators/feasibility_op.py tests/test_decision/test_multi_objective_solver.py
git commit -m "feat: add feasibility stage to procurement graph"
```

---

### Task 2: 新增 ParetoFrontierOp，识别 frontier 与 dominated feasible options

**Files:**
- Create: `src/velaris_agent/decision/operators/pareto_frontier_op.py`
- Modify: `tests/test_decision/test_multi_objective_solver.py`

- [ ] **Step 1: 先写失败测试，锁定 non-dominated filtering 行为**

```python
from velaris_agent.decision.operators.pareto_frontier_op import ParetoFrontierOp


def test_pareto_frontier_op_keeps_only_non_dominated_feasible_options() -> None:
    context = _build_procurement_context(
        options=[
            {
                "id": "cheap-fast",
                "label": "低价快交付",
                "price_cny": 100000,
                "delivery_days": 5,
                "quality_score": 0.80,
                "compliance_score": 0.95,
                "risk_score": 0.20,
                "available": True,
            },
            {
                "id": "premium-safe",
                "label": "高质量低风险",
                "price_cny": 170000,
                "delivery_days": 7,
                "quality_score": 0.95,
                "compliance_score": 0.98,
                "risk_score": 0.10,
                "available": True,
            },
            {
                "id": "dominated-mid",
                "label": "被支配方案",
                "price_cny": 175000,
                "delivery_days": 8,
                "quality_score": 0.90,
                "compliance_score": 0.96,
                "risk_score": 0.12,
                "available": True,
            },
        ],
    )

    context = IntentOp().run(context)
    context = OptionDiscoveryOp().run(context)
    context = NormalizationOp().run(context)
    context = FeasibilityOp().run(context)
    context = ParetoFrontierOp().run(context)

    assert [item.option_id for item in context.pareto_frontier] == ["cheap-fast", "premium-safe"]
    assert [item.option_id for item in context.dominated_options] == ["dominated-mid"]
    assert [item["option_id"] for item in context.frontier_metrics] == [
        "cheap-fast",
        "premium-safe",
    ]
    assert context.frontier_metrics[1]["dominated_option_ids"] == ["dominated-mid"]
```

- [ ] **Step 2: 运行测试，确认 ParetoFrontierOp 尚不存在**

Run:
```bash
./scripts/run_pytest.sh tests/test_decision/test_multi_objective_solver.py::test_pareto_frontier_op_keeps_only_non_dominated_feasible_options -q
```

Expected:
- `ModuleNotFoundError` 或 `AttributeError`

- [ ] **Step 3: 复用指标注册表方向，写最小 ParetoFrontierOp**

```python
# src/velaris_agent/decision/operators/pareto_frontier_op.py
from velaris_agent.memory.types import get_decision_metrics_for_scenario


class ParetoFrontierOp:
    spec = OperatorSpec("pareto_frontier")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        if not context.accepted_options:
            context.pareto_frontier = []
            context.dominated_options = []
            context.frontier_metrics = []
            context.operator_traces.append(
                OperatorTraceRecord(
                    operator_id=self.spec.operator_id,
                    operator_version=self.spec.operator_version,
                    input_schema_version=self.spec.input_schema_version,
                    output_schema_version=self.spec.output_schema_version,
                    confidence=0.0,
                    warnings=["no_feasible_option"],
                )
            )
            return context

        comparable_metrics = {
            item.metric_id
            for item in get_decision_metrics_for_scenario(context.scenario)
        }
        frontier: list[DecisionOptionSchema] = []
        dominated: list[DecisionOptionSchema] = []
        frontier_metrics: list[dict[str, Any]] = []

        for candidate in context.accepted_options:
            dominated_by: list[str] = []
            dominates_ids: list[str] = []
            for peer in context.accepted_options:
                if peer.option_id == candidate.option_id:
                    continue
                if _dominates(peer, candidate, comparable_metrics):
                    dominated_by.append(peer.option_id)
                if _dominates(candidate, peer, comparable_metrics):
                    dominates_ids.append(peer.option_id)
            if dominated_by:
                dominated.append(candidate)
                continue

            frontier.append(candidate)
            frontier_metrics.append(
                {
                    "option_id": candidate.option_id,
                    "dominates_option_ids": dominates_ids,
                    "dominated_by_option_ids": [],
                    "dominated_option_ids": dominates_ids,
                }
            )

        context.pareto_frontier = frontier
        context.dominated_options = dominated
        context.frontier_metrics = frontier_metrics
        context.operator_traces.append(
            OperatorTraceRecord(
                operator_id=self.spec.operator_id,
                operator_version=self.spec.operator_version,
                input_schema_version=self.spec.input_schema_version,
                output_schema_version=self.spec.output_schema_version,
                confidence=1.0,
            )
        )
        return context
```

- [ ] **Step 4: 用显式 helper 固化“非支配”的判定规则**

```python
# src/velaris_agent/decision/operators/pareto_frontier_op.py
def _dominates(
    lhs: DecisionOptionSchema,
    rhs: DecisionOptionSchema,
    comparable_metrics: set[str],
) -> bool:
    lhs_scores = {
        metric.metric_id: metric.normalized_score
        for metric in lhs.metrics
        if metric.metric_id in comparable_metrics
    }
    rhs_scores = {
        metric.metric_id: metric.normalized_score
        for metric in rhs.metrics
        if metric.metric_id in comparable_metrics
    }
    shared = set(lhs_scores) & set(rhs_scores)
    if not shared:
        return False
    return all(lhs_scores[mid] >= rhs_scores[mid] for mid in shared) and any(
        lhs_scores[mid] > rhs_scores[mid] for mid in shared
    )
```

- [ ] **Step 5: 跑 Task 2 验证**

Run:
```bash
./scripts/run_pytest.sh tests/test_decision/test_multi_objective_solver.py::test_pareto_frontier_op_keeps_only_non_dominated_feasible_options -q
```

Expected:
- `1 passed`
- frontier / dominated 输出稳定

- [ ] **Step 6: 提交 Task 2**

```bash
git add src/velaris_agent/decision/operators/pareto_frontier_op.py tests/test_decision/test_multi_objective_solver.py
git commit -m "feat: add pareto frontier operator"
```

---

### Task 3: 新增 OperatingPointSelectorOp，把 weighted-sum 降级为 frontier 内选择器

**Files:**
- Create: `src/velaris_agent/decision/operators/operating_point_selector_op.py`
- Modify: `src/velaris_agent/decision/operators/optimization_op.py`
- Modify: `src/velaris_agent/decision/operators/explanation_op.py`
- Modify: `src/velaris_agent/decision/operators/registry.py`
- Modify: `src/velaris_agent/decision/graph.py`
- Modify: `tests/test_decision/test_operator_registry.py`
- Modify: `tests/test_decision/test_procurement_operator_graph.py`
- Modify: `tests/test_decision/test_multi_objective_solver.py`

- [ ] **Step 1: 先写失败测试，锁定“切链 + frontier 内选点 + dominated tail 保留”行为**

```python
from velaris_agent.decision.operators.operating_point_selector_op import OperatingPointSelectorOp
from velaris_agent.decision.operators.registry import build_default_operator_registry


def test_operator_registry_includes_phase3_multi_objective_chain() -> None:
    registry = build_default_operator_registry()
    graph = registry.get_graph("procurement")

    assert [spec.operator_id for spec in graph] == [
        "intent",
        "option_discovery",
        "normalization",
        "stakeholder",
        "feasibility",
        "pareto_frontier",
        "operating_point_selector",
        "negotiation",
        "bias_audit",
        "explanation",
    ]


def test_operating_point_selector_scores_only_frontier_and_keeps_dominated_tail() -> None:
    context = _build_procurement_context(
        decision_weights={
            "cost": 0.10,
            "quality": 0.60,
            "delivery": 0.10,
            "compliance": 0.10,
            "risk": 0.10,
        },
        options=[
            {
                "id": "budget-choice",
                "label": "低价方案",
                "price_cny": 100000,
                "delivery_days": 7,
                "quality_score": 0.70,
                "compliance_score": 0.95,
                "risk_score": 0.10,
                "available": True,
            },
            {
                "id": "premium-choice",
                "label": "高质量方案",
                "price_cny": 170000,
                "delivery_days": 7,
                "quality_score": 0.95,
                "compliance_score": 0.95,
                "risk_score": 0.10,
                "available": True,
            },
            {
                "id": "dominated-choice",
                "label": "被支配方案",
                "price_cny": 175000,
                "delivery_days": 8,
                "quality_score": 0.90,
                "compliance_score": 0.95,
                "risk_score": 0.12,
                "available": True,
            },
        ],
    )

    context = IntentOp().run(context)
    context = OptionDiscoveryOp().run(context)
    context = NormalizationOp().run(context)
    context = FeasibilityOp().run(context)
    context = ParetoFrontierOp().run(context)
    context = OperatingPointSelectorOp().run(context)

    assert context.recommended_option_id == "premium-choice"
    assert [item.option_id for item in context.ranked_options] == [
        "premium-choice",
        "budget-choice",
        "dominated-choice",
    ]
    assert context.operating_point_summary["frontier_option_ids"] == [
        "budget-choice",
        "premium-choice",
    ]
    assert context.operating_point_summary["selector"] == "weighted_sum_over_frontier"
```

- [ ] **Step 2: 运行测试，确认 operating point 选择器尚不存在**

Run:
```bash
./scripts/run_pytest.sh tests/test_decision/test_operator_registry.py tests/test_decision/test_multi_objective_solver.py::test_operating_point_selector_scores_only_frontier_and_keeps_dominated_tail -q
```

Expected:
- registry 仍然包含 `optimization`
- `ModuleNotFoundError` 或 `AssertionError`

- [ ] **Step 3: 把 OptimizationOp 降级为共享 scorer helper，并新增 OperatingPointSelectorOp**

```python
# src/velaris_agent/decision/operators/optimization_op.py
DEFAULT_PROCUREMENT_WEIGHTS = {
    "cost": 0.28,
    "quality": 0.24,
    "delivery": 0.16,
    "compliance": 0.22,
    "risk": 0.10,
}


def merge_weights(
    default_weights: dict[str, float],
    override_weights: dict[str, float],
) -> dict[str, float]:
    merged = dict(default_weights)
    for dimension, value in override_weights.items():
        if dimension in merged:
            merged[dimension] = float(value)
    return merged


def score_weighted_sum(
    *,
    options: list[dict[str, Any]],
    weights: dict[str, float],
) -> list[dict[str, Any]]:
    total_weight = sum(max(weight, 0.0) for weight in weights.values())
    normalized_weights = {
        dimension: (max(weight, 0.0) / total_weight if total_weight > 0 else 0.0)
        for dimension, weight in weights.items()
    }

    ranked: list[dict[str, Any]] = []
    for option in options:
        raw_scores = option.get("scores", {})
        total_score = 0.0
        normalized_scores: dict[str, float] = {}
        for dimension, weight in normalized_weights.items():
            score = _clamp_score(raw_scores.get(dimension, 0.0))
            normalized_scores[dimension] = score
            total_score += score * weight
        ranked.append(
            {
                "id": option.get("id", ""),
                "label": option.get("label", option.get("id", "")),
                "scores": normalized_scores,
                "total_score": round(total_score, 4),
            }
        )

    return sorted(ranked, key=lambda item: item["total_score"], reverse=True)
```

```python
# src/velaris_agent/decision/operators/operating_point_selector_op.py
from velaris_agent.decision.operators.optimization_op import (
    DEFAULT_PROCUREMENT_WEIGHTS,
    merge_weights,
    score_weighted_sum,
)


class OperatingPointSelectorOp:
    spec = OperatorSpec("operating_point_selector")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        frontier = list(context.pareto_frontier or context.accepted_options)
        if not frontier:
            context.ranked_options = []
            context.recommended_option_id = None
            context.operating_point_summary = {
                "selector": "weighted_sum_over_frontier",
                "frontier_option_ids": [],
                "selected_option_id": None,
                "penalties": {},
            }
            context.operator_traces.append(
                OperatorTraceRecord(
                    operator_id=self.spec.operator_id,
                    operator_version=self.spec.operator_version,
                    input_schema_version=self.spec.input_schema_version,
                    output_schema_version=self.spec.output_schema_version,
                    confidence=0.0,
                    warnings=["no_feasible_option"],
                )
            )
            return context

        merged_weights = merge_weights(DEFAULT_PROCUREMENT_WEIGHTS, context.decision_weights)
        ranked_frontier = score_weighted_sum(options=_to_scored_input(frontier), weights=merged_weights)
        ranked_frontier_ids = [item["id"] for item in ranked_frontier]
        ranked_frontier_map = {item["id"]: item for item in ranked_frontier}
        ranked_dominated = score_weighted_sum(
            options=_to_scored_input(context.dominated_options),
            weights=merged_weights,
        )
        ranked_dominated_ids = [item["id"] for item in ranked_dominated]
        ranked_dominated_map = {item["id"]: item for item in ranked_dominated}

        ranked_frontier_options = sorted(frontier, key=lambda item: ranked_frontier_ids.index(item.option_id))
        dominated_tail_options = (
            sorted(
                context.dominated_options,
                key=lambda item: ranked_dominated_ids.index(item.option_id),
            )
            if ranked_dominated_ids
            else list(context.dominated_options)
        )
        context.ranked_options = ranked_frontier_options + dominated_tail_options
        context.recommended_option_id = ranked_frontier_ids[0]
        context.operating_point_summary = {
            "selector": "weighted_sum_over_frontier",
            "frontier_option_ids": [item.option_id for item in ranked_frontier_options],
            "selected_option_id": context.recommended_option_id,
            "selected_total_score": ranked_frontier_map[context.recommended_option_id]["total_score"],
            "penalties": {
                "conflict_cost": 0.0,
                "policy_risk": 0.0,
                "uncertainty": 0.0,
                "regret_estimate": 0.0,
            },
            "weights": merged_weights,
        }
        _write_score_metadata(
            context.ranked_options,
            {**ranked_frontier_map, **ranked_dominated_map},
        )
        context.operator_traces.append(
            OperatorTraceRecord(
                operator_id=self.spec.operator_id,
                operator_version=self.spec.operator_version,
                input_schema_version=self.spec.input_schema_version,
                output_schema_version=self.spec.output_schema_version,
                confidence=1.0,
            )
        )
        return context


def _to_scored_input(options: list[DecisionOptionSchema]) -> list[dict[str, Any]]:
    return [
        {
            "id": option.option_id,
            "label": option.label,
            "scores": {
                metric.metric_id: metric.normalized_score
                for metric in option.metrics
            },
        }
        for option in options
    ]


def _write_score_metadata(
    ranked_options: list[DecisionOptionSchema],
    scored_map: dict[str, dict[str, Any]],
) -> None:
    for option in ranked_options:
        scored = scored_map.get(option.option_id)
        if scored is None:
            continue
        option.metadata["total_score"] = scored["total_score"]
        option.metadata["score_breakdown"] = dict(scored["scores"])
```

- [ ] **Step 4: 让 ExplanationOp 显式解释“为什么这个点在 frontier 上被选中”**

```python
# src/velaris_agent/decision/operators/explanation_op.py
class ExplanationOp:
    spec = OperatorSpec("explanation")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        recommended = next(
            (item for item in context.ranked_options if item.option_id == context.recommended_option_id),
            None,
        )
        if recommended is None:
            context.explanation = "没有供应商同时满足预算、交付与合规约束。"
            context.operator_traces.append(
                OperatorTraceRecord(
                    operator_id=self.spec.operator_id,
                    operator_version=self.spec.operator_version,
                    input_schema_version=self.spec.input_schema_version,
                    output_schema_version=self.spec.output_schema_version,
                    confidence=0.0,
                    warnings=["no_feasible_option"],
                )
            )
            return context

        frontier_size = len(context.pareto_frontier)
        evidence_refs: list[str] = []
        for metric in recommended.metrics:
            evidence_refs.extend(metric.evidence_refs)
        context.explanation = (
            f"推荐 {recommended.label}，因为它位于 Pareto 前沿（共 {frontier_size} 个候选点），"
            f"并在当前权重下成为 operating point。"
        )
        context.operator_traces.append(
            OperatorTraceRecord(
                operator_id=self.spec.operator_id,
                operator_version=self.spec.operator_version,
                input_schema_version=self.spec.input_schema_version,
                output_schema_version=self.spec.output_schema_version,
                confidence=1.0,
                evidence_refs=list(dict.fromkeys(evidence_refs)),
            )
        )
        return context
```

- [ ] **Step 5: 在新算子都落地后切换默认 procurement graph，并扩展 graph result**

```python
# src/velaris_agent/decision/operators/registry.py
default_graph = [
    OperatorSpec("intent"),
    OperatorSpec("option_discovery"),
    OperatorSpec("normalization"),
    OperatorSpec("stakeholder"),
    OperatorSpec("feasibility"),
    OperatorSpec("pareto_frontier"),
    OperatorSpec("operating_point_selector"),
    OperatorSpec("negotiation"),
    OperatorSpec("bias_audit"),
    OperatorSpec("explanation"),
]
```

```python
# src/velaris_agent/decision/graph.py
from velaris_agent.decision.operators.feasibility_op import FeasibilityOp
from velaris_agent.decision.operators.operating_point_selector_op import OperatingPointSelectorOp
from velaris_agent.decision.operators.pareto_frontier_op import ParetoFrontierOp


def build_default_operators_for_scenario(scenario: str) -> list[DecisionOperator]:
    registry = build_default_operator_registry()
    operator_map = {
        "intent": IntentOp,
        "option_discovery": OptionDiscoveryOp,
        "normalization": NormalizationOp,
        "stakeholder": StakeholderOp,
        "feasibility": FeasibilityOp,
        "pareto_frontier": ParetoFrontierOp,
        "operating_point_selector": OperatingPointSelectorOp,
        "negotiation": NegotiationOp,
        "bias_audit": BiasAuditOp,
        "explanation": ExplanationOp,
    }
    return [operator_map[spec.operator_id]() for spec in registry.get_graph(scenario)]


return DecisionGraphResult(
    scenario=context.scenario,
    ranked_options=context.ranked_options,
    accepted_option_ids=[item.option_id for item in context.accepted_options],
    rejected_option_ids=[item.option_id for item in context.rejected_options],
    rejection_reasons=context.rejection_reasons,
    pareto_frontier_ids=[item.option_id for item in context.pareto_frontier],
    dominated_option_ids=[item.option_id for item in context.dominated_options],
    frontier_metrics=context.frontier_metrics,
    operating_point_summary=context.operating_point_summary,
    recommended_option_id=context.recommended_option_id,
    explanation=context.explanation,
    warnings=context.warnings,
    operator_traces=context.operator_traces,
)
```

- [ ] **Step 6: 跑 Task 3 验证**

Run:
```bash
./scripts/run_pytest.sh tests/test_decision/test_operator_registry.py tests/test_decision/test_multi_objective_solver.py tests/test_decision/test_procurement_operator_graph.py -q
```

Expected:
- decision graph 相关用例全部通过
- 推荐只在 frontier 内选出
- dominated feasible options 仍然出现在 ranked tail
- explanation 明确提到 Pareto frontier 与 operating point

- [ ] **Step 7: 提交 Task 3**

```bash
git add src/velaris_agent/decision/operators/operating_point_selector_op.py src/velaris_agent/decision/operators/optimization_op.py src/velaris_agent/decision/operators/explanation_op.py src/velaris_agent/decision/operators/registry.py src/velaris_agent/decision/graph.py tests/test_decision/test_operator_registry.py tests/test_decision/test_multi_objective_solver.py tests/test_decision/test_procurement_operator_graph.py
git commit -m "feat: select procurement operating point on pareto frontier"
```

---

### Task 4: 保持 procurement legacy adapter 兼容，并把 Phase 3 frontier 结果接回 business flow

**Files:**
- Modify: `src/velaris_agent/biz/engine.py`
- Modify: `tests/test_biz/test_engine_operator_graph.py`
- Modify: `tests/test_biz/test_engine_procurement.py`
- Modify: `tests/test_biz/test_orchestrator.py`

- [ ] **Step 1: 先写失败测试，锁定 legacy `options` 不能丢 dominated feasible options**

```python
from openharness.biz.engine import run_scenario


def test_run_procurement_scenario_keeps_dominated_feasible_options_in_legacy_options() -> None:
    result = run_scenario(
        "procurement",
        {
            "query": "比较三家供应商，质量优先，但仍需满足合规。",
            "budget_max": 250000,
            "require_compliance": True,
            "decision_weights": {
                "cost": 0.10,
                "quality": 0.60,
                "delivery": 0.10,
                "compliance": 0.10,
                "risk": 0.10,
            },
            "options": [
                {
                    "id": "budget-choice",
                    "label": "低价方案",
                    "price_cny": 100000,
                    "delivery_days": 7,
                    "quality_score": 0.70,
                    "compliance_score": 0.95,
                    "risk_score": 0.10,
                    "available": True,
                },
                {
                    "id": "premium-choice",
                    "label": "高质量方案",
                    "price_cny": 170000,
                    "delivery_days": 7,
                    "quality_score": 0.95,
                    "compliance_score": 0.95,
                    "risk_score": 0.10,
                    "available": True,
                },
                {
                    "id": "dominated-choice",
                    "label": "被支配方案",
                    "price_cny": 175000,
                    "delivery_days": 8,
                    "quality_score": 0.90,
                    "compliance_score": 0.95,
                    "risk_score": 0.12,
                    "available": True,
                },
            ],
        },
    )

    assert result["recommended"]["id"] == "premium-choice"
    assert result["accepted_option_ids"] == [
        "budget-choice",
        "premium-choice",
        "dominated-choice",
    ]
    assert [item["id"] for item in result["options"]] == [
        "premium-choice",
        "budget-choice",
        "dominated-choice",
    ]
    assert result["explanation"].startswith("推荐 高质量方案，因为它位于 Pareto 前沿")
```

- [ ] **Step 2: 运行测试，确认当前 legacy adapter 还没有 frontier 语义**

Run:
```bash
./scripts/run_pytest.sh tests/test_biz/test_engine_operator_graph.py tests/test_biz/test_engine_procurement.py tests/test_biz/test_orchestrator.py -q
```

Expected:
- operator trace 顺序仍断言 `optimization`
- explanation 仍是“成本、合规和风险之间最均衡”
- 或 `options` 列表没有 dominated feasible option 的 tail 顺序保证

- [ ] **Step 3: 更新 procurement adapter，继续回填完整 feasible `options` 并接受 frontier 结果**

```python
# src/velaris_agent/biz/engine.py
def _run_procurement_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    graph_result = execute_decision_graph(
        scenario="procurement",
        query=query,
        payload=payload,
        constraints={},
    )
    ranked_options = [
        _build_procurement_option_from_graph(
            normalized_option=option,
            budget_max=budget_max,
            require_compliance=require_compliance,
            max_delivery_days=max_delivery_days,
        )
        for option in graph_result.ranked_options
    ]
    recommended = ranked_options[0] if ranked_options else None
    summary = (
        graph_result.explanation
        if recommended is None
        else (
            f"共评估 {len(payload.get('options', []))} 个供应商方案，"
            f"其中 {len(graph_result.accepted_option_ids)} 个通过硬约束，"
            f"{len(graph_result.pareto_frontier_ids)} 个进入 Pareto 前沿。"
        )
    )
```

- [ ] **Step 4: 更新 orchestrator / engine tests，接受 Phase 3 operator 顺序与 explanation**

```python
assert [trace["operator_id"] for trace in result["operator_trace"]] == [
    "intent",
    "option_discovery",
    "normalization",
    "stakeholder",
    "feasibility",
    "pareto_frontier",
    "operating_point_selector",
    "negotiation",
    "bias_audit",
    "explanation",
]
assert result["result"]["recommended"]["id"] == "premium-choice"
assert result["result"]["explanation"].startswith("推荐 高质量方案，因为它位于 Pareto 前沿")
```

- [ ] **Step 5: 跑 Task 4 回归**

Run:
```bash
./scripts/run_pytest.sh tests/test_biz/test_engine.py tests/test_biz/test_engine_procurement.py tests/test_biz/test_engine_operator_graph.py tests/test_biz/test_orchestrator.py tests/test_biz/test_engine_stakeholder.py -q
```

Expected:
- 业务回归相关用例全部通过
- legacy `recommended / options / accepted_option_ids / audit_trace` 保持兼容
- orchestrator audit payload 能接受新增 operator ids

- [ ] **Step 6: 提交 Task 4**

```bash
git add src/velaris_agent/biz/engine.py tests/test_biz/test_engine_operator_graph.py tests/test_biz/test_engine_procurement.py tests/test_biz/test_orchestrator.py
git commit -m "refactor: upgrade procurement graph to pareto operating point"
```

---

## Verification Matrix

按顺序执行以下验证，不要跳步：

```bash
./scripts/run_pytest.sh tests/test_decision/test_operator_registry.py tests/test_decision/test_multi_objective_solver.py tests/test_decision/test_procurement_operator_graph.py -q
./scripts/run_pytest.sh tests/test_biz/test_engine.py tests/test_biz/test_engine_procurement.py tests/test_biz/test_engine_operator_graph.py tests/test_biz/test_orchestrator.py tests/test_biz/test_engine_stakeholder.py -q
./scripts/run_pytest.sh tests/test_memory/test_decision_metrics_registry.py tests/test_memory/test_stakeholder_integration.py -q
```

Expected:
- decision core 能稳定输出 feasible set、Pareto frontier 与 operating point summary
- business layer 不回退，legacy `procurement` 协议继续完整返回 feasible `options`
- metric registry 与 stakeholder integration 回归保持通过

## Out of Scope

- 不在 Phase 3 引入数据库持久化 `decision_frontier` / `decision_recommendation_v2` 表
- 不在 Phase 3 为 `travel / tokencost / robotclaw / lifegoal` 接入 Pareto frontier
- 不在 Phase 3 实现按 option 精细化计算的 `conflict_cost / regret_estimate / uncertainty`；这里只预留 structured penalty slots，Phase 4 再细化
- 不在 Phase 3 修改 CLI / UI / MCP 工具注册与外部 API 形状
- 不在 Phase 3 引入外部 solver、线性规划器或多目标优化第三方库

## Completion Criteria

- `procurement` graph 新增 `FeasibilityOp / ParetoFrontierOp / OperatingPointSelectorOp`
- `NormalizationOp` 回归为 schema 标准化，不再直接产生 accepted/rejected
- `accepted_option_ids` 表示全部 feasible options，`pareto_frontier_ids` / `dominated_option_ids` 作为新增附加字段暴露
- `ranked_options` 对 legacy adapter 仍然保留完整 feasible options，其中 frontier options 在前、dominated options 在 tail
- recommendation 解释能够说明“为什么这个点在 Pareto 前沿上被选中”
- 所有验证命令通过，并且统一使用 `./scripts/run_pytest.sh`

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | 当前会话 scoped review | 识别 Phase 2 → Phase 3 的结构性缺口与 plan 风险 | 2 | PASS WITH CHANGES | 已纳入 5 个关键修订：① lower-is-better 归一化随 feasibility 下沉；② legacy `options` 继续包含 dominated feasible options；③ weighted-sum 只保留为 frontier 内 selector；④ 补齐 `_build_procurement_context / _to_scored_input / _write_score_metadata` 等执行所需 helper；⑤ 将默认 graph 切换延后到 Task 3，避免 Task 1 中间提交因算子未落地而失稳 |
| Eng Review | `/plan-eng-review` | Architecture & tests (recommended) | 0 | — | — |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**VERDICT:** READY FOR USER REVIEW — 当前计划已把 Phase 3 的核心边界收口为 procurement 单场景的 multi-objective solver 升级，重点解决 feasibility 分层、Pareto frontier 判定与 operating point 选择，同时保持 legacy adapter 不丢失 dominated feasible options。
