# Velaris Agent Hotel Biztravel Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 把 `velaris-agent` 的酒店 / 商旅共享决策引擎升级成“多店推荐 + 需求推断 + 偏好回写提示”的可演示闭环，用户先看到多家候选店和 bundle，再在确认后把选择信号回写到偏好记忆，而不是写进知识库。

**Architecture:** 保持 `velaris-agent` 作为共享决策内核，不把 supplier 私有协议或平台编排逻辑下沉进来。引擎层负责把 `BundleDecisionResponse` 后处理成面向用户的展示结构：候选店摘要、bundle 摘要、低置信度需求推断、以及明确的 `save_decision` / `recall_preferences` 回写提示；持久化层只记录真实选择和可解释上下文，知识库仍然只收录显式稳定事实。

**Tech Stack:** Python 3.11, Pydantic 2, pytest, 现有 `velaris_agent` / `openharness` 工具链

---

## Scope Check

本计划只覆盖一个子系统：**酒店 / 商旅共享决策引擎的结果丰富化与偏好回写闭环**。虽然会同时改动 `biz`、`decision`、`memory` 和 `openharness` 工具，但它们都服务于同一个目标：让一次 query 的输出包含“推荐什么、为什么、猜测了什么、选择后往哪里写回”。

## File Structure

### Create

- `src/velaris_agent/biz/hotel_biztravel_inference.py`
- `tests/test_biz/test_hotel_biztravel_inference.py`

### Modify

- `src/velaris_agent/biz/engine.py`
- `src/velaris_agent/biz/__init__.py`
- `src/velaris_agent/decision/contracts.py`
- `src/velaris_agent/memory/types.py`
- `src/openharness/tools/save_decision_tool.py`
- `tests/test_biz/test_engine_hotel_biztravel.py`
- `tests/test_memory/test_decision_memory.py`
- `tests/test_tools/test_decision_tools.py`

## Task 1: 扩展共享决策响应契约

**Files:**
- Modify: `src/velaris_agent/decision/contracts.py`
- Test: `tests/test_biz/test_engine_hotel_biztravel.py`

- [x] **Step 1: 先写失败测试**

```python
def test_run_hotel_biztravel_domain_rank_returns_candidate_briefs_and_writeback_hints() -> None:
    result = run_scenario("hotel_biztravel", payload_with_flower_candidates)
    assert result["candidate_briefs"][0]["store_name"] == "机场店花束 A"
    assert result["inferred_user_needs"][0]["need_type"] == "flower_quantity"
    assert result["writeback_hints"]["preference_tool"] == "save_decision"
```

- [x] **Step 2: 跑测试确认当前会失败**

Run: `pytest tests/test_biz/test_engine_hotel_biztravel.py -q`

Expected: 失败，原因是 `candidate_briefs`、`inferred_user_needs`、`writeback_hints` 还没有进入 `BundleDecisionResponse`

- [x] **Step 3: 给 `BundleDecisionResponse` 增加结构化输出字段**

```python
class BundleDecisionResponse(BaseModel):
    candidate_briefs: list[dict[str, Any]] = Field(default_factory=list, description="候选店铺摘要")
    bundle_briefs: list[dict[str, Any]] = Field(default_factory=list, description="bundle 摘要")
    inferred_user_needs: list[dict[str, Any]] = Field(default_factory=list, description="低置信度需求推断")
    writeback_hints: dict[str, Any] = Field(default_factory=dict, description="偏好回写提示")
```

这一步只扩展契约，不改排序逻辑；目的是让引擎能把“展示信息”和“学习提示”一起返回给平台。

- [x] **Step 4: 跑测试确认契约字段已可序列化**

Run: `pytest tests/test_biz/test_engine_hotel_biztravel.py -q`

Expected: 测试仍然失败，但失败点从字段缺失变成引擎还没填充这些字段

- [x] **Step 5: 提交该步**

```bash
git add src/velaris_agent/decision/contracts.py tests/test_biz/test_engine_hotel_biztravel.py
git commit -m "feat(decision): 扩展共享决策展示字段"
```

## Task 2: 增加酒店 / 商旅结果丰富化助手

**Files:**
- Create: `src/velaris_agent/biz/hotel_biztravel_inference.py`
- Modify: `src/velaris_agent/biz/engine.py`
- Modify: `src/velaris_agent/biz/__init__.py`

- [x] **Step 1: 先写失败测试**

```python
def test_enrich_hotel_biztravel_response_infers_need_and_writeback() -> None:
    request = BundleDecisionRequest(...)
    response = evaluate_bundle_decision(request)
    enriched = enrich_hotel_biztravel_response(request=request, response=response)
    assert enriched.candidate_briefs
    assert enriched.inferred_user_needs
    assert enriched.writeback_hints["knowledge_policy"] == "explicit-only"
```

- [x] **Step 2: 跑测试确认当前会失败**

Run: `pytest tests/test_biz/test_hotel_biztravel_inference.py -q`

Expected: 失败，原因是 helper 模块还不存在

- [x] **Step 3: 实现结果丰富化助手**

```python
def enrich_hotel_biztravel_response(
    *,
    request: BundleDecisionRequest,
    response: BundleDecisionResponse,
) -> BundleDecisionResponse:
    query = _extract_query(request)
    if response.decision_type == "domain_rank":
        candidate_briefs = _build_candidate_briefs(request, response)
        bundle_briefs = []
    else:
        candidate_briefs = []
        bundle_briefs = _build_bundle_briefs(request, response)
    inferred_user_needs = _infer_user_needs(query, request, response)
    writeback_hints = _build_writeback_hints(request, response)
    return response.model_copy(
        update={
            "candidate_briefs": candidate_briefs,
            "bundle_briefs": bundle_briefs,
            "inferred_user_needs": inferred_user_needs,
            "writeback_hints": writeback_hints,
        }
    )
```

助手内部要做三件事：

1. 从 `request_context` / `candidate_set.request_context` 提取 query；
2. 从候选元数据里抽取店名、机型、咖啡类型、花束数量等展示字段；
3. 明确告诉上层：`save_decision` 负责偏好回写，`KnowledgeBase` 只收显式稳定事实，不收本次推断。

- [x] **Step 4: 把引擎接到新的丰富化助手**

```python
def _run_hotel_biztravel_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    request = build_bundle_decision_request(payload)
    response = evaluate_bundle_decision(request)
    enriched = enrich_hotel_biztravel_response(request=request, response=response)
    return enriched.model_dump(mode="json")
```

同时把 `hotel_biztravel` 的推荐工具补成偏好闭环优先：

```python
"hotel_biztravel": [
    "recall_preferences",
    "recall_decisions",
    "biz_execute",
    "decision_score",
    "save_decision",
    "biz_plan",
    "biz_score",
]
```

- [x] **Step 5: 跑测试确认引擎开始输出丰富结构**

Run: `pytest tests/test_biz/test_engine_hotel_biztravel.py -q`

Expected: domain_rank / bundle_rank 都能返回丰富字段，且旧字段保持不变

- [x] **Step 6: 提交该步**

```bash
git add src/velaris_agent/biz/hotel_biztravel_inference.py src/velaris_agent/biz/engine.py src/velaris_agent/biz/__init__.py
git commit -m "feat(biz): 丰富酒店商旅决策输出"
```

## Task 3: 把回写信号落到决策记忆

**Files:**
- Modify: `src/velaris_agent/memory/types.py`
- Modify: `src/openharness/tools/save_decision_tool.py`
- Test: `tests/test_memory/test_decision_memory.py`
- Test: `tests/test_tools/test_decision_tools.py`

- [x] **Step 1: 先写失败测试**

```python
def test_save_decision_persists_inferred_needs_and_candidate_briefs(tmp_path: Path) -> None:
    record = DecisionRecord(..., inferred_user_needs=[...], candidate_briefs=[...], writeback_hints={...})
    mem.save(record)
    got = mem.get(record.decision_id)
    assert got.inferred_user_needs[0]["need_type"] == "coffee_type"
```

- [x] **Step 2: 跑测试确认当前会失败**

Run: `pytest tests/test_memory/test_decision_memory.py tests/test_tools/test_decision_tools.py -q`

Expected: 失败，原因是 `DecisionRecord` 和 `SaveDecisionInput` 还没有这几个新字段

- [x] **Step 3: 扩展决策记录与保存工具**

```python
class DecisionRecord(BaseModel):
    candidate_briefs: list[dict[str, Any]] = Field(default_factory=list, description="候选店铺摘要")
    inferred_user_needs: list[dict[str, Any]] = Field(default_factory=list, description="推断需求")
    writeback_hints: dict[str, Any] = Field(default_factory=dict, description="偏好回写提示")
```

```python
class SaveDecisionInput(BaseModel):
    candidate_briefs: list[dict[str, Any]] = Field(default_factory=list, description="候选店铺摘要")
    inferred_user_needs: list[dict[str, Any]] = Field(default_factory=list, description="推断需求")
    writeback_hints: dict[str, Any] = Field(default_factory=dict, description="偏好回写提示")
```

`save_decision_tool.py` 里创建 `DecisionRecord` 时要把这三个字段一起写进去，这样偏好回写信号会进入本地记忆，而不是进入知识库。

- [x] **Step 4: 跑测试确认回写持久化可用**

Run: `pytest tests/test_memory/test_decision_memory.py tests/test_tools/test_decision_tools.py -q`

Expected: 通过，且新增字段可往返保存

- [x] **Step 5: 提交该步**

```bash
git add src/velaris_agent/memory/types.py src/openharness/tools/save_decision_tool.py tests/test_memory/test_decision_memory.py tests/test_tools/test_decision_tools.py
git commit -m "feat(memory): 记录商旅偏好回写信号"
```

## Task 4: 三个 demo 场景验证并输出报告

**Files:**
- Modify: `tests/test_biz/test_engine_hotel_biztravel.py`
- Create: `/Users/apus/Documents/UGit/smart-travel-workspace/output/velaris-agent-hotel-biztravel-demo-report.md`

- [x] **Step 1: 写三个 demo case**

```python
cases = [
    ("flower", payload_for_flower_bundle),
    ("coffee", payload_for_coffee_bundle),
    ("bundle", payload_for_travel_hotel_bundle),
]
```

每个 case 都要验证：

1. 返回多家候选店；
2. 返回至少一个低置信度需求推断；
3. 返回偏好回写提示；
4. 用户选中后，`selected_candidate_id` 或 `selected_bundle_id` 能回填到记忆层。

- [x] **Step 2: 跑测试确认三个 case 都通过**

Run: `pytest tests/test_biz/test_engine_hotel_biztravel.py -q`

Expected: 3 个 demo case 全部通过，且不影响现有 travel / tokencost / robotclaw 回归

- [x] **Step 3: 生成 demo 报告**

```markdown
# Velaris Agent Hotel Biztravel Demo Report

## Case 1: Flower bundle
## Case 2: Coffee choice
## Case 3: Travel + hotel bundle
```

报告里要记录：

- query
- 候选店列表
- 推断出的需求
- 用户最终选择
- writeback_hints
- 是否建议回写到 DecisionMemory / PreferenceLearner

- [x] **Step 4: 提交该步**

```bash
git add tests/test_biz/test_engine_hotel_biztravel.py /Users/apus/Documents/UGit/smart-travel-workspace/output/velaris-agent-hotel-biztravel-demo-report.md
git commit -m "test(biz): 验证酒店商旅三场景 demo"
```

## Self-Review Checklist

- [x] 每个新增字段都有中文注释，说明“是什么 / 做什么 / 为什么”
- [x] `DecisionRecord` 与 `SaveDecisionInput` 字段保持一致
- [x] `KnowledgeBase` 没有接收隐式推断结果
- [x] `save_decision` 只记录选择与偏好信号，不记录供应商私有协议
- [x] 三个 demo 场景分别覆盖花店、咖啡、航班 / 酒店 bundle
- [x] 旧的 `travel` / `tokencost` / `robotclaw` 路径没有回归
