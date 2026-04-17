# Velaris Phase 2 Operator Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前 `src/velaris_agent/biz/engine.py` 中混合的采购决策流程拆成可注册、可追踪、可审计的 operator graph；Phase 2 仅让 `procurement` 接入新 graph，`travel / tokencost / robotclaw` 继续走 legacy 路径，保持外部协议兼容。

**Architecture:** 继续沿用单体内核，不引入新中间件。新增 `src/velaris_agent/decision/` 作为 Phase 2 的唯一决策核心目录，由 registry 作为 graph 编排的单一真相，graph executor 只按 registry 装配算子；`biz/engine.py` 仅在 `procurement` 分支委托给 operator graph 并把完整结果映射回旧协议，`velaris/orchestrator.py` 只补 trace 摘要，不改 CLI/UI 入口。

**Tech Stack:** Python, Pydantic 2, pytest, Velaris memory models, OpenHarness compatibility layer, `./scripts/run_pytest.sh`

---

## Current Baseline

- `src/velaris_agent/biz/engine.py` 当前仍是“场景路由 + 评分 + 协议组装”的上帝文件。
- `src/velaris_agent/memory/types.py` 已有 `DecisionOptionSchema`、`DecisionAuditSchema`、`get_decision_metrics_for_scenario()`，可以直接作为 Phase 2 的统一 schema 基座。
- `src/velaris_agent/memory/conflict_engine.py` 与 `src/velaris_agent/memory/negotiation.py` 已提供 `StakeholderOp` / `NegotiationOp` 的可复用实现。
- `src/velaris_agent/velaris/orchestrator.py` 已具备审计事件落盘入口，可在不改 API 形状的前提下追加 operator trace 摘要。
- 当前本地验证命令必须统一走 `./scripts/run_pytest.sh`，不要再直接使用默认 `python3 -m pytest`。

## File Structure

### New Core Files

- Create: `src/velaris_agent/decision/__init__.py` — 决策图公共导出层
- Create: `src/velaris_agent/decision/context.py` — `DecisionExecutionContext`、`OperatorTraceRecord`、`DecisionGraphResult`
- Create: `src/velaris_agent/decision/operators/base.py` — `OperatorSpec`、`DecisionOperator` 协议与公共 trace helper
- Create: `src/velaris_agent/decision/operators/registry.py` — 场景到 operator graph 的注册表
- Create: `src/velaris_agent/decision/operators/intent_op.py` — `IntentOp`
- Create: `src/velaris_agent/decision/operators/option_discovery_op.py` — `OptionDiscoveryOp`
- Create: `src/velaris_agent/decision/operators/normalization_op.py` — `NormalizationOp`
- Create: `src/velaris_agent/decision/operators/stakeholder_op.py` — `StakeholderOp`
- Create: `src/velaris_agent/decision/operators/optimization_op.py` — `OptimizationOp`
- Create: `src/velaris_agent/decision/operators/negotiation_op.py` — `NegotiationOp`
- Create: `src/velaris_agent/decision/operators/bias_audit_op.py` — `BiasAuditOp`
- Create: `src/velaris_agent/decision/operators/explanation_op.py` — `ExplanationOp`
- Create: `src/velaris_agent/decision/graph.py` — graph 执行器与 legacy result adapter

### Existing Files To Modify

- Modify: `src/velaris_agent/biz/engine.py` — 保留 public API，仅把 `procurement` 分支委托给 `decision.graph`
- Modify: `src/velaris_agent/velaris/orchestrator.py` — 在审计 payload 中追加 `operator_trace_summary`
- Modify: `src/velaris_agent/scenarios/procurement/types.py` — 允许挂载 operator trace 输出而不破坏既有字段
- Modify: `src/velaris_agent/memory/types.py` — 仅在 Phase 2 真正需要时补 trace model，不重复定义 option/audit schema

### New Tests

- Create: `tests/test_decision/test_operator_registry.py`
- Create: `tests/test_decision/test_procurement_operator_graph.py`
- Create: `tests/test_decision/test_operator_trace_contract.py`
- Create: `tests/test_biz/test_engine_operator_graph.py`
- Modify: `tests/test_biz/test_engine_procurement.py`
- Modify: `tests/test_biz/test_orchestrator.py`

## Guardrails

- Phase 2 不改 UI、CLI、Textual、React 或 MCP 协议。
- Phase 2 仅让 `procurement` 接入 operator graph；`travel / tokencost / robotclaw` 保持当前 legacy 实现与协议不变。
- registry 是 operator graph 编排的唯一真相；graph executor 不允许再硬编码一份独立算子列表。
- 采购里的预算、合规、交付仍然是硬约束，不能在 Phase 2 退化成纯 weighted-sum 软评分；context/result 必须显式携带 accepted/rejected/reasons。
- `OptimizationOp` 仍允许先用 weighted-sum 作为临时排序器；Pareto frontier 留到 Phase 3。
- `BiasAuditOp` 允许先输出结构化 warnings/no-op payload，不能阻塞主链推荐。
- 所有新增 trace 字段都必须是“附加兼容”，不能删除既有 `summary / recommended / audit_trace`。
- legacy adapter 必须回填完整 `options` 列表，不能只返回 `recommended`。
- 审计里的 `trace_id / created_at / input_ref / output_ref` 必须保持动态生成，不能写死。

---

### Task 1: 建立 operator contract、execution context 与 registry

**Files:**
- Create: `src/velaris_agent/decision/__init__.py`
- Create: `src/velaris_agent/decision/context.py`
- Create: `src/velaris_agent/decision/operators/base.py`
- Create: `src/velaris_agent/decision/operators/registry.py`
- Test: `tests/test_decision/test_operator_registry.py`
- Test: `tests/test_decision/test_operator_trace_contract.py`

- [ ] **Step 1: 先写 registry 与 trace contract 的失败测试**

```python
import pytest

from velaris_agent.decision.operators.registry import build_default_operator_registry


def test_operator_registry_returns_default_procurement_graph() -> None:
    registry = build_default_operator_registry()
    graph = registry.get_graph("procurement")
    assert [spec.operator_id for spec in graph] == [
        "intent",
        "option_discovery",
        "normalization",
        "stakeholder",
        "optimization",
        "negotiation",
        "bias_audit",
        "explanation",
    ]


def test_operator_registry_keeps_non_procurement_scenarios_on_legacy_path() -> None:
    registry = build_default_operator_registry()
    with pytest.raises(KeyError):
        registry.get_graph("travel")


def test_operator_trace_record_contains_phase2_contract_fields() -> None:
    registry = build_default_operator_registry()
    spec = registry.get_graph("procurement")[0]
    assert spec.operator_version == "v1"
    assert spec.input_schema_version == "v1"
    assert spec.output_schema_version == "v1"
```

- [ ] **Step 2: 运行测试，确认当前仓库确实缺少 decision core**

Run:
```bash
./scripts/run_pytest.sh tests/test_decision/test_operator_registry.py tests/test_decision/test_operator_trace_contract.py -q
```

Expected:
- `ModuleNotFoundError: No module named 'velaris_agent.decision'`
- 或 registry / context symbol not found

- [ ] **Step 3: 写最小 contract 与 context 实现**

```python
# src/velaris_agent/decision/operators/base.py
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OperatorSpec:
    operator_id: str
    operator_version: str = "v1"
    input_schema_version: str = "v1"
    output_schema_version: str = "v1"


class DecisionOperator(Protocol):
    spec: OperatorSpec

    def run(self, context: "DecisionExecutionContext") -> "DecisionExecutionContext":
        raise NotImplementedError
```

```python
# src/velaris_agent/decision/context.py
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OperatorTraceRecord:
    operator_id: str
    operator_version: str
    input_schema_version: str
    output_schema_version: str
    confidence: float
    evidence_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DecisionExecutionContext:
    scenario: str
    query: str
    payload: dict[str, Any]
    constraints: dict[str, Any]
    operator_traces: list[OperatorTraceRecord] = field(default_factory=list)
```

- [ ] **Step 4: 写默认 registry**

```python
# src/velaris_agent/decision/operators/registry.py
from dataclasses import dataclass

from velaris_agent.decision.operators.base import OperatorSpec


@dataclass
class OperatorRegistry:
    graphs: dict[str, list[OperatorSpec]]

    def get_graph(self, scenario: str) -> list[OperatorSpec]:
        return self.graphs[scenario]


def build_default_operator_registry() -> OperatorRegistry:
    default_graph = [
        OperatorSpec("intent"),
        OperatorSpec("option_discovery"),
        OperatorSpec("normalization"),
        OperatorSpec("stakeholder"),
        OperatorSpec("optimization"),
        OperatorSpec("negotiation"),
        OperatorSpec("bias_audit"),
        OperatorSpec("explanation"),
    ]
    return OperatorRegistry(
        graphs={
            "procurement": list(default_graph),
        }
    )
```

- [ ] **Step 5: 运行 Task 1 测试**

Run:
```bash
./scripts/run_pytest.sh tests/test_decision/test_operator_registry.py tests/test_decision/test_operator_trace_contract.py -q
```

Expected:
- `2 passed`

- [ ] **Step 6: 提交 Task 1**

```bash
git add src/velaris_agent/decision/__init__.py src/velaris_agent/decision/context.py src/velaris_agent/decision/operators/base.py src/velaris_agent/decision/operators/registry.py tests/test_decision/test_operator_registry.py tests/test_decision/test_operator_trace_contract.py
git commit -m "feat: add operator contract and registry"
```

---

### Task 2: 落地 Intent / OptionDiscovery / Normalization 三个前置算子

**Files:**
- Create: `src/velaris_agent/decision/operators/intent_op.py`
- Create: `src/velaris_agent/decision/operators/option_discovery_op.py`
- Create: `src/velaris_agent/decision/operators/normalization_op.py`
- Create: `tests/test_decision/test_procurement_operator_graph.py`
- Modify: `src/velaris_agent/decision/context.py`
- Modify: `src/velaris_agent/memory/types.py`

- [ ] **Step 1: 先写 procurement front-half 的失败测试**

```python
from velaris_agent.decision.context import DecisionExecutionContext
from velaris_agent.decision.operators.intent_op import IntentOp
from velaris_agent.decision.operators.normalization_op import NormalizationOp
from velaris_agent.decision.operators.option_discovery_op import OptionDiscoveryOp


def test_procurement_front_half_builds_normalized_options() -> None:
    context = DecisionExecutionContext(
        scenario="procurement",
        query="比较三家供应商，预算不超过 130000，必须通过合规审计。",
        payload={
            "budget_max": 130000,
            "require_compliance": True,
            "options": [
                {
                    "id": "vendor-a",
                    "label": "供应商 A",
                    "price_cny": 118000,
                    "delivery_days": 9,
                    "quality_score": 0.90,
                    "compliance_score": 0.98,
                    "risk_score": 0.10,
                    "available": True,
                    "evidence_refs": ["quote://vendor-a"],
                },
                {
                    "id": "vendor-b",
                    "label": "供应商 B",
                    "price_cny": 126000,
                    "delivery_days": 12,
                    "quality_score": 0.86,
                    "compliance_score": 0.82,
                    "risk_score": 0.14,
                    "available": True,
                    "evidence_refs": ["quote://vendor-b"],
                }
            ],
        },
        constraints={},
    )
    context = IntentOp().run(context)
    context = OptionDiscoveryOp().run(context)
    context = NormalizationOp().run(context)

    assert context.intent["budget_max"] == 130000
    assert len(context.normalized_options) == 2
    assert [item.option_id for item in context.accepted_options] == ["vendor-a"]
    assert context.rejection_reasons["vendor-b"] == [
        "delivery_exceeds_limit",
        "compliance_below_threshold",
    ]
    assert context.normalized_options[0].metrics[0].metric_id == "cost"
    assert [trace.operator_id for trace in context.operator_traces] == [
        "intent",
        "option_discovery",
        "normalization",
    ]
```

- [ ] **Step 2: 跑失败测试，确认缺的是前置算子而不是测试本身**

Run:
```bash
./scripts/run_pytest.sh tests/test_decision/test_procurement_operator_graph.py::test_procurement_front_half_builds_normalized_options -q
```

Expected:
- `AttributeError` / `ImportError` 指向 `IntentOp`、`normalization` 相关符号缺失

- [ ] **Step 3: 扩展 execution context，让前置算子有稳定读写面**

```python
# src/velaris_agent/decision/context.py
from velaris_agent.memory.types import DecisionOptionSchema


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
    warnings: list[str] = field(default_factory=list)
    operator_traces: list[OperatorTraceRecord] = field(default_factory=list)
```

- [ ] **Step 4: 实现 IntentOp / OptionDiscoveryOp / NormalizationOp**

```python
# src/velaris_agent/decision/operators/intent_op.py
class IntentOp:
    spec = OperatorSpec("intent")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        budget_max = context.payload.get("budget_max")
        context.intent = {
            "query": context.query,
            "budget_max": budget_max,
            "require_compliance": bool(context.payload.get("require_compliance", True)),
            "max_delivery_days": context.payload.get("max_delivery_days"),
        }
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
# src/velaris_agent/decision/operators/option_discovery_op.py
class OptionDiscoveryOp:
    spec = OperatorSpec("option_discovery")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        context.raw_options = list(context.payload.get("options", []))
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
# src/velaris_agent/decision/operators/normalization_op.py
from velaris_agent.memory.types import DecisionOptionMetric, DecisionOptionSchema


class NormalizationOp:
    spec = OperatorSpec("normalization")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        normalized: list[DecisionOptionSchema] = []
        accepted: list[DecisionOptionSchema] = []
        rejected: list[DecisionOptionSchema] = []
        rejection_reasons: dict[str, list[str]] = {}
        for option in context.raw_options:
            reasons: list[str] = []
            if not option.get("available", True):
                reasons.append("option_unavailable")
            if context.intent.get("budget_max") is not None and float(option["price_cny"]) > float(context.intent["budget_max"]):
                reasons.append("budget_exceeded")
            if context.intent.get("require_compliance") and float(option["compliance_score"]) < 0.9:
                reasons.append("compliance_below_threshold")
            if context.intent.get("max_delivery_days") is not None and float(option["delivery_days"]) > float(context.intent["max_delivery_days"]):
                reasons.append("delivery_exceeds_limit")

            normalized_option = DecisionOptionSchema(
                option_id=option["id"],
                scenario=context.scenario,
                label=option["label"],
                metrics=[
                    DecisionOptionMetric(
                        metric_id="cost",
                        raw_value=option["price_cny"],
                        normalized_score=0.0,
                        evidence_refs=list(option.get("evidence_refs", [])),
                    ),
                    DecisionOptionMetric(
                        metric_id="quality",
                        raw_value=option["quality_score"],
                        normalized_score=option["quality_score"],
                        evidence_refs=list(option.get("evidence_refs", [])),
                    ),
                    DecisionOptionMetric(
                        metric_id="delivery",
                        raw_value=option["delivery_days"],
                        normalized_score=0.0,
                        evidence_refs=list(option.get("evidence_refs", [])),
                    ),
                    DecisionOptionMetric(
                        metric_id="compliance",
                        raw_value=option["compliance_score"],
                        normalized_score=option["compliance_score"],
                        evidence_refs=list(option.get("evidence_refs", [])),
                    ),
                    DecisionOptionMetric(
                        metric_id="risk",
                        raw_value=option["risk_score"],
                        normalized_score=1 - option["risk_score"],
                        evidence_refs=list(option.get("evidence_refs", [])),
                    ),
                ],
                metadata={
                    "raw_option": dict(option),
                    "available": option.get("available", True),
                },
            )
            normalized.append(normalized_option)
            if reasons:
                rejected.append(normalized_option)
                rejection_reasons[normalized_option.option_id] = reasons
            else:
                accepted.append(normalized_option)
        context.normalized_options = normalized
        context.accepted_options = accepted
        context.rejected_options = rejected
        context.rejection_reasons = rejection_reasons
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

- [ ] **Step 5: 跑 front-half 测试**

Run:
```bash
./scripts/run_pytest.sh tests/test_decision/test_procurement_operator_graph.py::test_procurement_front_half_builds_normalized_options -q
```

Expected:
- `1 passed`

- [ ] **Step 6: 提交 Task 2**

```bash
git add src/velaris_agent/decision/context.py src/velaris_agent/decision/operators/intent_op.py src/velaris_agent/decision/operators/option_discovery_op.py src/velaris_agent/decision/operators/normalization_op.py tests/test_decision/test_procurement_operator_graph.py
git commit -m "feat: add front-half decision operators"
```

---

### Task 3: 落地 Stakeholder / Optimization / Negotiation / BiasAudit / Explanation 五个后置算子

**Files:**
- Create: `src/velaris_agent/decision/operators/stakeholder_op.py`
- Create: `src/velaris_agent/decision/operators/optimization_op.py`
- Create: `src/velaris_agent/decision/operators/negotiation_op.py`
- Create: `src/velaris_agent/decision/operators/bias_audit_op.py`
- Create: `src/velaris_agent/decision/operators/explanation_op.py`
- Modify: `src/velaris_agent/decision/context.py`
- Test: `tests/test_decision/test_operator_trace_contract.py`
- Test: `tests/test_decision/test_procurement_operator_graph.py`

- [ ] **Step 1: 先写 full graph 的失败测试**

```python
from velaris_agent.decision.graph import execute_decision_graph


def test_procurement_graph_returns_recommendation_and_trace() -> None:
    result = execute_decision_graph(
        scenario="procurement",
        query="比较三家供应商，预算不超过 130000，必须通过合规审计。",
        payload={
            "budget_max": 130000,
            "require_compliance": True,
            "options": [
                {
                    "id": "vendor-a",
                    "label": "供应商 A",
                    "price_cny": 118000,
                    "delivery_days": 9,
                    "quality_score": 0.90,
                    "compliance_score": 0.98,
                    "risk_score": 0.10,
                    "available": True,
                    "evidence_refs": ["quote://vendor-a", "policy://approved-vendors"],
                },
                {
                    "id": "vendor-b",
                    "label": "供应商 B",
                    "price_cny": 145000,
                    "delivery_days": 7,
                    "quality_score": 0.91,
                    "compliance_score": 0.99,
                    "risk_score": 0.08,
                    "available": True,
                    "evidence_refs": ["quote://vendor-b"],
                }
            ],
        },
        constraints={},
    )

    assert result.recommended_option_id == "vendor-a"
    assert result.accepted_option_ids == ["vendor-a"]
    assert result.rejected_option_ids == ["vendor-b"]
    assert result.rejection_reasons["vendor-b"] == ["budget_exceeded"]
    assert result.operator_traces[-1].operator_id == "explanation"
    assert result.operator_traces[-1].evidence_refs == ["quote://vendor-a", "policy://approved-vendors"]
    assert result.explanation.startswith("推荐 供应商 A")
```

- [ ] **Step 2: 跑失败测试，确认 graph executor 与 tail operators 还没接好**

Run:
```bash
./scripts/run_pytest.sh tests/test_decision/test_procurement_operator_graph.py::test_procurement_graph_returns_recommendation_and_trace -q
```

Expected:
- `ImportError` / `AttributeError` 指向 `execute_decision_graph` 或 tail operators 缺失

- [ ] **Step 3: 给 context 增加排序、协商、解释字段**

```python
# src/velaris_agent/decision/context.py
@dataclass
class DecisionGraphResult:
    scenario: str
    ranked_options: list[DecisionOptionSchema]
    accepted_option_ids: list[str]
    rejected_option_ids: list[str]
    rejection_reasons: dict[str, list[str]]
    recommended_option_id: str | None
    explanation: str
    operator_traces: list[OperatorTraceRecord]
    warnings: list[str] = field(default_factory=list)


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
    stakeholder_context: dict[str, Any] = field(default_factory=dict)
    ranked_options: list[DecisionOptionSchema] = field(default_factory=list)
    recommended_option_id: str | None = None
    negotiation_summary: dict[str, Any] = field(default_factory=dict)
    bias_summary: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    warnings: list[str] = field(default_factory=list)
    operator_traces: list[OperatorTraceRecord] = field(default_factory=list)
```

- [ ] **Step 4: 写五个 tail operators 的最小实现**

```python
# src/velaris_agent/decision/operators/optimization_op.py
class OptimizationOp:
    spec = OperatorSpec("optimization")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        if not context.accepted_options:
            context.ranked_options = []
            context.recommended_option_id = None
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

        ranked = score_options(
            options=[
                {
                    "id": option.option_id,
                    "label": option.label,
                    "scores": {metric.metric_id: metric.normalized_score for metric in option.metrics},
                }
                for option in context.accepted_options
            ],
            weights={"cost": 0.28, "quality": 0.24, "delivery": 0.16, "compliance": 0.22, "risk": 0.10},
        )
        ranked_ids = [item["id"] for item in ranked]
        ranked_map = {item["id"]: item for item in ranked}
        context.ranked_options = sorted(context.accepted_options, key=lambda item: ranked_ids.index(item.option_id))
        for option in context.ranked_options:
            option.metadata["total_score"] = ranked_map[option.option_id]["total_score"]
            option.metadata["score_breakdown"] = ranked_map[option.option_id]["scores"]
        context.recommended_option_id = ranked_ids[0] if ranked_ids else None
        context.operator_traces.append(
            OperatorTraceRecord(
                operator_id=self.spec.operator_id,
                operator_version=self.spec.operator_version,
                input_schema_version=self.spec.input_schema_version,
                output_schema_version=self.spec.output_schema_version,
                confidence=1.0 if ranked_ids else 0.0,
            )
        )
        return context
```

```python
# src/velaris_agent/decision/operators/negotiation_op.py
class NegotiationOp:
    spec = OperatorSpec("negotiation")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        context.negotiation_summary = {"proposals": [], "conflicts": context.stakeholder_context.get("conflicts", [])}
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
# src/velaris_agent/decision/operators/explanation_op.py
class ExplanationOp:
    spec = OperatorSpec("explanation")

    def run(self, context: DecisionExecutionContext) -> DecisionExecutionContext:
        recommended = next((item for item in context.ranked_options if item.option_id == context.recommended_option_id), None)
        evidence_refs: list[str] = []
        if recommended is not None:
            for metric in recommended.metrics:
                evidence_refs.extend(metric.evidence_refs)
        context.explanation = f"推荐 {recommended.label}，因为它在成本、合规和风险之间最均衡。"
        context.operator_traces.append(
            OperatorTraceRecord(
                operator_id=self.spec.operator_id,
                operator_version=self.spec.operator_version,
                input_schema_version=self.spec.input_schema_version,
                output_schema_version=self.spec.output_schema_version,
                confidence=1.0 if recommended is not None else 0.0,
                evidence_refs=list(dict.fromkeys(evidence_refs)),
            )
        )
        return context
```

- [ ] **Step 5: 实现 `execute_decision_graph()`**

```python
# src/velaris_agent/decision/graph.py
from velaris_agent.decision.operators.bias_audit_op import BiasAuditOp
from velaris_agent.decision.operators.explanation_op import ExplanationOp
from velaris_agent.decision.operators.intent_op import IntentOp
from velaris_agent.decision.operators.negotiation_op import NegotiationOp
from velaris_agent.decision.operators.normalization_op import NormalizationOp
from velaris_agent.decision.operators.option_discovery_op import OptionDiscoveryOp
from velaris_agent.decision.operators.optimization_op import OptimizationOp
from velaris_agent.decision.operators.stakeholder_op import StakeholderOp


def build_default_operators_for_scenario(scenario: str) -> list[DecisionOperator]:
    registry = build_default_operator_registry()
    operator_map = {
        "intent": IntentOp,
        "option_discovery": OptionDiscoveryOp,
        "normalization": NormalizationOp,
        "stakeholder": StakeholderOp,
        "optimization": OptimizationOp,
        "negotiation": NegotiationOp,
        "bias_audit": BiasAuditOp,
        "explanation": ExplanationOp,
    }
    return [operator_map[spec.operator_id]() for spec in registry.get_graph(scenario)]


def execute_decision_graph(
    scenario: str,
    query: str,
    payload: dict[str, Any],
    constraints: dict[str, Any] | None = None,
) -> DecisionGraphResult:
    context = DecisionExecutionContext(
        scenario=scenario,
        query=query,
        payload=payload,
        constraints=constraints or {},
    )
    for operator in build_default_operators_for_scenario(scenario):
        context = operator.run(context)
    return DecisionGraphResult(
        scenario=context.scenario,
        ranked_options=context.ranked_options,
        accepted_option_ids=[item.option_id for item in context.ranked_options],
        rejected_option_ids=[item.option_id for item in context.rejected_options],
        rejection_reasons=context.rejection_reasons,
        recommended_option_id=context.recommended_option_id,
        explanation=context.explanation,
        operator_traces=context.operator_traces,
        warnings=context.warnings,
    )
```

- [ ] **Step 6: 跑 Task 3 测试**

Run:
```bash
./scripts/run_pytest.sh tests/test_decision/test_procurement_operator_graph.py tests/test_decision/test_operator_trace_contract.py -q
```

Expected:
- `2 passed`

- [ ] **Step 7: 提交 Task 3**

```bash
git add src/velaris_agent/decision/context.py src/velaris_agent/decision/graph.py src/velaris_agent/decision/operators/stakeholder_op.py src/velaris_agent/decision/operators/optimization_op.py src/velaris_agent/decision/operators/negotiation_op.py src/velaris_agent/decision/operators/bias_audit_op.py src/velaris_agent/decision/operators/explanation_op.py tests/test_decision/test_procurement_operator_graph.py tests/test_decision/test_operator_trace_contract.py
git commit -m "feat: add decision graph operators"
```

---

### Task 4: 用 operator graph 接管 `biz/engine.py`，并把 trace 摘要接到 orchestrator

**Files:**
- Create: `src/velaris_agent/decision/graph.py`
- Modify: `src/velaris_agent/biz/engine.py`
- Modify: `src/velaris_agent/velaris/orchestrator.py`
- Modify: `src/velaris_agent/scenarios/procurement/types.py`
- Test: `tests/test_biz/test_engine_operator_graph.py`
- Modify: `tests/test_biz/test_engine_procurement.py`
- Modify: `tests/test_biz/test_orchestrator.py`

- [ ] **Step 1: 先写兼容层失败测试**

```python
from velaris_agent.biz.engine import run_scenario


def test_run_procurement_scenario_exposes_operator_trace_without_breaking_protocol() -> None:
    result = run_scenario(
        "procurement",
        {
            "query": "比较三家供应商，预算不超过 130000，必须通过合规审计。",
            "budget_max": 130000,
            "require_compliance": True,
            "options": [
                {
                    "id": "vendor-a",
                    "label": "供应商 A",
                    "price_cny": 118000,
                    "delivery_days": 9,
                    "quality_score": 0.90,
                    "compliance_score": 0.98,
                    "risk_score": 0.10,
                    "available": True,
                    "evidence_refs": ["quote://vendor-a", "policy://approved-vendors"],
                }
            ],
        },
    )

    assert result["recommended"]["id"] == "vendor-a"
    assert result["audit_trace"]["audit_event"]["operator_id"] == "explanation"
    assert [trace["operator_id"] for trace in result["operator_trace"]] == [
        "intent",
        "option_discovery",
        "normalization",
        "stakeholder",
        "optimization",
        "negotiation",
        "bias_audit",
        "explanation",
    ]
```

```python
def test_orchestrator_appends_operator_trace_summary_into_audit_payload() -> None:
    class InMemoryAuditStore:
        def __init__(self) -> None:
            self.events: list[dict[str, Any]] = []

        def append_event(
            self,
            session_id: str,
            step_name: str,
            operator_id: str,
            payload: dict[str, Any] | None = None,
        ) -> None:
            self.events.append(
                {
                    "session_id": session_id,
                    "step_name": step_name,
                    "operator_id": operator_id,
                    "payload": payload or {},
                }
            )

    audit_store = InMemoryAuditStore()
    orchestrator = VelarisBizOrchestrator(audit_store=audit_store)
    result = orchestrator.execute(
        query="比较三家供应商，预算不超过 130000，必须通过合规审计。",
        scenario="procurement",
        payload={
            "query": "比较三家供应商，预算不超过 130000，必须通过合规审计。",
            "budget_max": 130000,
            "require_compliance": True,
            "options": [
                {
                    "id": "vendor-a",
                    "label": "供应商 A",
                    "price_cny": 118000,
                    "delivery_days": 9,
                    "quality_score": 0.90,
                    "compliance_score": 0.98,
                    "risk_score": 0.10,
                    "available": True,
                    "evidence_refs": ["quote://vendor-a", "policy://approved-vendors"],
                }
            ],
        },
        constraints={"requires_audit": True},
        session_id="session-procurement-phase2",
    )

    assert result["audit_event_count"] == 2
    assert result["result"]["operator_trace"][0]["operator_id"] == "intent"
    assert result["result"]["audit_trace"]["audit_event"]["operator_id"] == "explanation"
    assert audit_store.events[1]["payload"]["operator_trace_summary"][0]["operator_id"] == "intent"
```

- [ ] **Step 2: 跑失败测试，确认 legacy adapter 还没接管**

Run:
```bash
./scripts/run_pytest.sh tests/test_biz/test_engine_operator_graph.py tests/test_biz/test_orchestrator.py -q
```

Expected:
- `KeyError: 'operator_trace'`
- 或 audit payload 中缺少 trace summary

- [ ] **Step 3: 把 `biz/engine.py` 改成兼容壳层**

```python
# src/velaris_agent/biz/engine.py
from velaris_agent.decision.graph import execute_decision_graph


def _build_procurement_option_from_graph(
    source: dict[str, Any],
    normalized_option: DecisionOptionSchema,
) -> ProcurementOption:
    return ProcurementOption(
        id=source["id"],
        label=source["label"],
        vendor=source.get("vendor"),
        price_cny=float(source["price_cny"]),
        delivery_days=float(source["delivery_days"]),
        quality_score=float(source["quality_score"]),
        compliance_score=float(source["compliance_score"]),
        risk_score=float(source["risk_score"]),
        total_score=normalized_option.metadata.get("total_score"),
        score_breakdown=normalized_option.metadata.get("score_breakdown", {}),
        reason=None,
        normalized_option=normalized_option,
        metadata={"evidence_refs": source.get("evidence_refs", [])},
    )


def _build_procurement_audit_from_graph(
    graph_result: DecisionGraphResult,
    payload: dict[str, Any],
    trace_id: str,
) -> ProcurementAuditTrace:
    last_trace = graph_result.operator_traces[-1] if graph_result.operator_traces else None
    return ProcurementAuditTrace(
        trace_id=trace_id,
        source_type=str(payload.get("source_type", "inline")),
        accepted_option_ids=graph_result.accepted_option_ids,
        recommended_option_id=graph_result.recommended_option_id,
        proposal_id=str(payload.get("proposal_id", "procurement-proposal-phase2")),
        summary=graph_result.explanation,
        created_at=_now_iso(),
        audit_event=DecisionAuditSchema(
            session_id=str(payload.get("session_id", "procurement-session-phase2")),
            decision_id=str(payload.get("proposal_id", "procurement-proposal-phase2")),
            step_name=f"{last_trace.operator_id}.completed" if last_trace is not None else "decision_graph.completed",
            operator_id=last_trace.operator_id if last_trace is not None else "decision_graph",
            operator_version=last_trace.operator_version if last_trace is not None else "v1",
            input_ref=f"decision://input/{payload.get('proposal_id', 'procurement-proposal-phase2')}",
            output_ref=f"decision://output/{payload.get('proposal_id', 'procurement-proposal-phase2')}",
            evidence_refs=last_trace.evidence_refs if last_trace is not None else [],
            confidence=last_trace.confidence if last_trace is not None else 0.0,
            trace_id=trace_id,
        ),
    )


def run_scenario(scenario: str, payload: dict[str, Any]) -> dict[str, Any]:
    if scenario == "procurement":
        trace_id = str(payload.get("trace_id", "") or f"procurement-trace-{uuid4().hex[:10]}")
        graph_result = execute_decision_graph(
            scenario=scenario,
            query=str(payload.get("query", "")),
            payload=payload,
            constraints={},
        )
        source_map = {
            str(item["id"]): item
            for item in payload.get("options", [])
        }
        ranked_options = [
            _build_procurement_option_from_graph(
                source=source_map[normalized_option.option_id],
                normalized_option=normalized_option,
            )
            for normalized_option in graph_result.ranked_options
            if normalized_option.option_id in source_map
        ]
        recommended = ranked_options[0] if ranked_options else None
        summary = (
            graph_result.explanation
            if ranked_options
            else "没有供应商同时满足预算、交付与合规约束。"
        )
        return ProcurementCompareResult(
            status=(
                ProcurementWorkflowStatus.PROPOSAL_READY
                if ranked_options
                else ProcurementWorkflowStatus.NO_MATCH
            ),
            query=str(payload.get("query", "")),
            session_id=str(payload.get("session_id", "procurement-session-phase2")),
            intent_slots=ProcurementIntentSlots(
                query=str(payload.get("query", "")),
                budget_max=payload.get("budget_max"),
                require_compliance=bool(payload.get("require_compliance", True)),
                max_delivery_days=payload.get("max_delivery_days"),
            ),
            options=ranked_options,
            recommended=recommended,
            accepted_option_ids=graph_result.accepted_option_ids,
            summary=summary,
            explanation=summary,
            proposal_id=str(payload.get("proposal_id", "procurement-proposal-phase2")),
            audit_trace=build_procurement_audit_from_graph(graph_result, payload, trace_id),
            operator_trace=[trace.__dict__ for trace in graph_result.operator_traces],
        ).model_dump(mode="json")
    if scenario == "travel":
        return _run_travel_scenario(payload)
    if scenario == "tokencost":
        return _run_tokencost_scenario(payload)
    if scenario == "robotclaw":
        return _run_robotclaw_scenario(payload)
    raise ValueError(f"Unsupported biz scenario: {scenario}")
```

- [ ] **Step 4: 把 trace 以附加字段注入协议与 orchestrator**

```python
# src/velaris_agent/scenarios/procurement/types.py
class ProcurementCompareResult(BaseModel):
    scenario: str = Field(default="procurement", description="场景标识")
    intent: str = Field(default="procurement_compare", description="统一工具意图")
    status: ProcurementWorkflowStatus = Field(description="当前工作流状态")
    query: str = Field(default="", description="用户原始请求")
    session_id: str = Field(description="会话 ID")
    intent_slots: ProcurementIntentSlots = Field(description="解析后的意图槽位")
    options: list[ProcurementOption] = Field(default_factory=list, description="候选方案")
    recommended: ProcurementOption | None = Field(default=None, description="推荐方案")
    accepted_option_ids: list[str] = Field(default_factory=list, description="通过约束过滤的候选项 ID")
    summary: str = Field(default="", description="简要摘要")
    explanation: str = Field(default="", description="推荐或失败说明")
    operator_trace: list[dict[str, Any]] = Field(default_factory=list, description="Phase 2 算子执行轨迹")
    proposal_id: str | None = Field(default=None, description="提案 ID")
    audit_trace: ProcurementAuditTrace = Field(description="审计轨迹")
```

```python
# src/velaris_agent/velaris/orchestrator.py
audit_payload = {
    "task_id": task.task_id,
    "scenario": plan["scenario"],
    "selected_strategy": routing.selected_strategy,
    "success": True,
    "summary": str(scenario_result.get("summary", "执行完成")),
    "operator_trace_summary": [
        {
            "operator_id": item["operator_id"],
            "operator_version": item["operator_version"],
            "confidence": item["confidence"],
        }
        for item in scenario_result.get("operator_trace", [])
    ],
}
```

- [ ] **Step 5: 跑兼容层回归**

Run:
```bash
./scripts/run_pytest.sh tests/test_biz/test_engine.py tests/test_biz/test_engine_procurement.py tests/test_biz/test_engine_operator_graph.py tests/test_biz/test_orchestrator.py -q
```

Expected:
- `all passed`
- `travel / tokencost / robotclaw` 旧协议测试不回退，且无需新增 protocol 字段改动

- [ ] **Step 6: 提交 Task 4**

```bash
git add src/velaris_agent/biz/engine.py src/velaris_agent/velaris/orchestrator.py src/velaris_agent/scenarios/procurement/types.py tests/test_biz/test_engine_operator_graph.py tests/test_biz/test_engine_procurement.py tests/test_biz/test_orchestrator.py
git commit -m "refactor: route biz engine through operator graph"
```

---

## Verification Matrix

按顺序执行以下验证，不要跳步：

```bash
./scripts/run_pytest.sh tests/test_decision/test_operator_registry.py tests/test_decision/test_operator_trace_contract.py tests/test_decision/test_procurement_operator_graph.py -q
./scripts/run_pytest.sh tests/test_biz/test_engine.py tests/test_biz/test_engine_procurement.py tests/test_biz/test_engine_operator_graph.py tests/test_biz/test_orchestrator.py -q
./scripts/run_pytest.sh tests/test_memory/test_decision_metrics_registry.py tests/test_memory/test_stakeholder_integration.py -q
```

Expected:
- 所有新增 decision tests 通过
- 现有 business flow tests 不回退
- `procurement` 与 shared metrics registry 保持兼容

## Out of Scope

- 不在 Phase 2 引入 `ParetoFrontierOp`、`FeasibilityOp`、`OperatingPointSelector`
- 不在 Phase 2 修改 CLI / UI / MCP 工具注册
- 不在 Phase 2 把 `bias` 信号写入新的持久化表

## Completion Criteria

- `biz/engine.py` 在 `procurement` 分支变成兼容壳层，其余场景继续走 legacy 路径
- operator graph 具备 `operator_id / operator_version / confidence / evidence_refs / warnings`
- procurement 结果与 orchestrator audit payload 都能携带可回放 trace 摘要
- procurement graph 明确保留 `accepted / rejected / rejection_reasons`，且无可行方案时仍能稳定返回 `NO_MATCH`
- legacy adapter 回填完整 `options / recommended / summary / audit_trace`，不丢失候选列表
- 所有验证命令通过，并且全部使用 `./scripts/run_pytest.sh`

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | 当前会话 scoped review | 实现边界、测试闭环、dirty workspace 下的 scoped diff 复核 | 1 | PASS | 0 个阻塞项；1 个残余风险：Phase 2 仍显式把 weighted-sum 留在 `OptimizationOp`，需在 Phase 3 再升级 Pareto |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | PASS WITH CHANGES | 已纳入 4 个阻塞修订：① Phase 2 范围收敛到 procurement；② registry 成为单一编排真相；③ accepted/rejected/reasons 进入 context/result contract；④ legacy adapter 保留完整 options 与动态 audit 元数据 |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**VERDICT:** READY FOR EXECUTION AFTER REVISION — 当前计划已收敛到 procurement 单场景迁移，补齐了 registry、硬约束 contract、legacy adapter 与验证闭环；可以据此开始 Phase 2 编码，不需要再修改 `travel / tokencost / robotclaw` 协议。
