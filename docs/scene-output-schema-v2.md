# Scene Output Schema v2

`scene_output_schema_v2` 是 `velaris-agent` 面向多场景的统一输出契约。

它的目标不是让核心内核理解“作文”“旅价”“采购”这些业务词，而是把所有场景的输出统一收敛到同一套中性骨架，再由场景适配器把这些中性槽位翻译回具体业务语言。

## 1. 设计原则

- 顶层字段中性化，不把场景词写死在字段名里。
- 语义下沉到条目级别的 `kind` 和 `payload`。
- 所有输出都要可解释、可回写、可落库。
- 每个条目都必须能追溯到证据。
- 默认只输出 1-3 条最重要内容，避免噪音。
- 旧 schema 可以保留 alias，但新场景统一使用 v2。

## 2. 顶层结构

```json
{
  "schema_id": "scene_output_schema_v2",
  "request_id": "req_123",
  "decision_id": "dec_456",
  "scenario": "writing",
  "decision_type": "weekly_review",
  "status": "ok",
  "summary": "本周优先补结构和开头。",
  "diagnostic_findings": [],
  "guidance": [],
  "suggestions": [],
  "next_actions": [],
  "roi_breakdown": {
    "benefit": 0.82,
    "cost": 0.28,
    "risk": 0.12,
    "learning_value": 0.85,
    "dependency_penalty": 0.08,
    "horizon_days": 14,
    "confidence": 0.77
  },
  "reason_codes": ["writing_structure_is_bottleneck"],
  "why_selected": ["结构问题对整体质量影响最大"],
  "why_not_others": [
    { "item_id": "act_language_polish", "reason": "语言润色收益次于结构修正" }
  ],
  "follow_up_questions": [],
  "writeback_hints": {
    "profile_state_updates": ["writing_primary_problem_tags_json"],
    "snapshot_updates": ["writing_review_summary"],
    "plan_table": true,
    "feedback_table": true
  },
  "trace": {
    "evaluated_rules": ["writing_review_v1"],
    "selected_rule": "writing_review_v1",
    "timestamp": "2026-05-09T16:40:00+08:00",
    "schema_version": "v2"
  }
}
```

## 3. 条目定义

### 3.1 `DiagnosticFinding`

承载问题、风险、约束、优势。

```json
{
  "finding_id": "df_001",
  "kind": "problem",
  "label": "开头弱",
  "severity": 0.8,
  "confidence": 0.9,
  "reason": "首段信息铺垫过长，主旨出现太晚",
  "evidence_refs": ["essay_20260509_01"],
  "payload": {
    "tag_id": "structure_opening_weak"
  }
}
```

### 3.2 `GuidanceItem`

承载训练方向、选择建议、行动指导。

```json
{
  "guidance_id": "g_001",
  "kind": "train",
  "label": "先补结构",
  "priority": 1,
  "why_now": "结构是当前最影响整体可读性的瓶颈",
  "steps": ["先写三段式提纲", "给开头补一个主旨句"],
  "success_criteria": ["三段内容清晰", "开头两句内点题"],
  "estimated_minutes": 10,
  "payload": {
    "dimension": "structure"
  }
}
```

### 3.3 `SuggestionItem`

承载资源建议、方案建议、补充建议。

```json
{
  "suggestion_id": "s_001",
  "kind": "reading",
  "label": "结构清晰的范文",
  "reason": "能直接提供段落组织模板",
  "evidence_refs": ["essay_20260509_01"],
  "payload": {
    "type": "chapter",
    "resource_id": "model_text_001"
  }
}
```

### 3.4 `NextAction`

承载下一步可执行动作。

```json
{
  "action_id": "a_001",
  "kind": "practice",
  "label": "先写提纲",
  "sequence": 1,
  "minutes": 5,
  "done_check": "能说清楚三段分别写什么",
  "source_id": "g_001",
  "payload": {
    "task_type": "outline"
  }
}
```

### 3.5 `WhyNotOther`

承载“为什么没有选其他项”的简短解释。

```json
{
  "item_id": "act_language_polish",
  "reason": "语言润色收益次于结构修正"
}
```

### 3.6 `RoiBreakdown`

承载收益、成本、风险、学习价值等 ROI 解释。

```json
{
  "benefit": 0.82,
  "cost": 0.28,
  "risk": 0.12,
  "learning_value": 0.85,
  "dependency_penalty": 0.08,
  "horizon_days": 14,
  "confidence": 0.77
}
```

### 3.7 `WritebackHints`

承载落库提示。

```json
{
  "profile_state_updates": ["writing_primary_problem_tags_json"],
  "snapshot_updates": ["writing_review_summary"],
  "plan_table": true,
  "feedback_table": true
}
```

### 3.8 `DecisionTrace`

承载决策过程追踪信息。

```json
{
  "evaluated_rules": ["writing_review_v1", "weekly_plan_v1"],
  "selected_rule": "writing_review_v1",
  "timestamp": "2026-05-09T16:40:00+08:00",
  "schema_version": "v2",
  "model_version": "velaris-agent-1.0"
}
```

## 4. JSON Schema

下面给出可直接落地的 JSON Schema 草案。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://velaris-agent.local/contracts/scene-output-schema-v2.json",
  "title": "Velaris Scene Output Schema v2",
  "type": "object",
  "required": [
    "schema_id",
    "request_id",
    "decision_id",
    "scenario",
    "decision_type",
    "status",
    "diagnostic_findings",
    "guidance",
    "suggestions",
    "next_actions",
    "reason_codes",
    "why_selected",
    "why_not_others",
    "follow_up_questions",
    "writeback_hints",
    "trace"
  ],
  "properties": {
    "schema_id": {
      "type": "string",
      "const": "scene_output_schema_v2"
    },
    "request_id": { "type": "string", "minLength": 1 },
    "decision_id": { "type": "string", "minLength": 1 },
    "scenario": { "type": "string", "minLength": 1 },
    "decision_type": { "type": "string", "minLength": 1 },
    "status": {
      "type": "string",
      "enum": ["ok", "need_more_input", "blocked", "degraded", "error"]
    },
    "summary": { "type": "string" },
    "diagnostic_findings": {
      "type": "array",
      "minItems": 0,
      "items": { "$ref": "#/$defs/DiagnosticFinding" }
    },
    "guidance": {
      "type": "array",
      "minItems": 0,
      "items": { "$ref": "#/$defs/GuidanceItem" }
    },
    "suggestions": {
      "type": "array",
      "minItems": 0,
      "items": { "$ref": "#/$defs/SuggestionItem" }
    },
    "next_actions": {
      "type": "array",
      "minItems": 0,
      "items": { "$ref": "#/$defs/NextAction" }
    },
    "roi_breakdown": { "$ref": "#/$defs/RoiBreakdown" },
    "reason_codes": {
      "type": "array",
      "items": { "type": "string" }
    },
    "why_selected": {
      "type": "array",
      "items": { "type": "string" }
    },
    "why_not_others": {
      "type": "array",
      "items": { "$ref": "#/$defs/WhyNotOther" }
    },
    "follow_up_questions": {
      "type": "array",
      "items": { "type": "string" }
    },
    "writeback_hints": { "$ref": "#/$defs/WritebackHints" },
    "trace": { "$ref": "#/$defs/DecisionTrace" }
  },
  "additionalProperties": false,
  "$defs": {
    "DiagnosticFinding": {
      "type": "object",
      "required": ["finding_id", "kind", "label", "reason", "evidence_refs"],
      "properties": {
        "finding_id": { "type": "string" },
        "kind": {
          "type": "string",
          "enum": ["problem", "risk", "constraint", "strength"]
        },
        "label": { "type": "string" },
        "severity": { "type": "number", "minimum": 0, "maximum": 1 },
        "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
        "reason": { "type": "string" },
        "evidence_refs": {
          "type": "array",
          "items": { "type": "string" }
        },
        "payload": {
          "type": "object",
          "additionalProperties": true
        }
      },
      "additionalProperties": false
    },
    "GuidanceItem": {
      "type": "object",
      "required": ["guidance_id", "kind", "label", "priority", "why_now", "steps"],
      "properties": {
        "guidance_id": { "type": "string" },
        "kind": {
          "type": "string",
          "enum": ["train", "choose", "plan", "review", "adjust"]
        },
        "label": { "type": "string" },
        "priority": { "type": "integer", "minimum": 1 },
        "why_now": { "type": "string" },
        "steps": {
          "type": "array",
          "items": { "type": "string" }
        },
        "success_criteria": {
          "type": "array",
          "items": { "type": "string" }
        },
        "estimated_minutes": { "type": "integer", "minimum": 1 },
        "payload": {
          "type": "object",
          "additionalProperties": true
        }
      },
      "additionalProperties": false
    },
    "SuggestionItem": {
      "type": "object",
      "required": ["suggestion_id", "kind", "label", "reason", "evidence_refs"],
      "properties": {
        "suggestion_id": { "type": "string" },
        "kind": {
          "type": "string",
          "enum": ["reading", "practice", "option", "resource", "reminder", "adjustment"]
        },
        "label": { "type": "string" },
        "reason": { "type": "string" },
        "evidence_refs": {
          "type": "array",
          "items": { "type": "string" }
        },
        "payload": {
          "type": "object",
          "additionalProperties": true
        }
      },
      "additionalProperties": false
    },
    "NextAction": {
      "type": "object",
      "required": ["action_id", "kind", "label", "sequence", "done_check"],
      "properties": {
        "action_id": { "type": "string" },
        "kind": {
          "type": "string",
          "enum": ["practice", "read", "compare", "confirm", "revise", "follow_up"]
        },
        "label": { "type": "string" },
        "sequence": { "type": "integer", "minimum": 1 },
        "minutes": { "type": "integer", "minimum": 1 },
        "done_check": { "type": "string" },
        "source_id": { "type": "string" },
        "payload": {
          "type": "object",
          "additionalProperties": true
        }
      },
      "additionalProperties": false
    },
    "WhyNotOther": {
      "type": "object",
      "required": ["item_id", "reason"],
      "properties": {
        "item_id": { "type": "string" },
        "reason": { "type": "string" }
      },
      "additionalProperties": false
    },
    "RoiBreakdown": {
      "type": "object",
      "required": ["benefit", "cost", "risk", "learning_value", "dependency_penalty", "confidence"],
      "properties": {
        "benefit": { "type": "number", "minimum": 0, "maximum": 1 },
        "cost": { "type": "number", "minimum": 0, "maximum": 1 },
        "risk": { "type": "number", "minimum": 0, "maximum": 1 },
        "learning_value": { "type": "number", "minimum": 0, "maximum": 1 },
        "dependency_penalty": { "type": "number", "minimum": 0, "maximum": 1 },
        "horizon_days": { "type": "integer", "minimum": 0 },
        "confidence": { "type": "number", "minimum": 0, "maximum": 1 }
      },
      "additionalProperties": false
    },
    "WritebackHints": {
      "type": "object",
      "required": ["profile_state_updates"],
      "properties": {
        "profile_state_updates": {
          "type": "array",
          "items": { "type": "string" }
        },
        "snapshot_updates": {
          "type": "array",
          "items": { "type": "string" }
        },
        "plan_table": { "type": "boolean" },
        "feedback_table": { "type": "boolean" }
      },
      "additionalProperties": false
    },
    "DecisionTrace": {
      "type": "object",
      "required": ["evaluated_rules", "selected_rule", "timestamp"],
      "properties": {
        "evaluated_rules": {
          "type": "array",
          "items": { "type": "string" }
        },
        "selected_rule": { "type": "string" },
        "timestamp": { "type": "string", "format": "date-time" },
        "schema_version": { "type": "string" },
        "model_version": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

## 5. Pydantic model 草图

下面是和 JSON Schema 一致的 Python 模型草图。

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ConfigDict


DiagnosticKind = Literal["problem", "risk", "constraint", "strength"]
GuidanceKind = Literal["train", "choose", "plan", "review", "adjust"]
SuggestionKind = Literal["reading", "practice", "option", "resource", "reminder", "adjustment"]
NextActionKind = Literal["practice", "read", "compare", "confirm", "revise", "follow_up"]


class DiagnosticFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str
    kind: DiagnosticKind
    label: str
    severity: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class GuidanceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guidance_id: str
    kind: GuidanceKind
    label: str
    priority: int = Field(ge=1)
    why_now: str
    steps: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    estimated_minutes: int | None = Field(default=None, ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class SuggestionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_id: str
    kind: SuggestionKind
    label: str
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class NextAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    kind: NextActionKind
    label: str
    sequence: int = Field(ge=1)
    minutes: int | None = Field(default=None, ge=1)
    done_check: str
    source_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class WhyNotOther(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    reason: str


class RoiBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benefit: float = Field(ge=0, le=1)
    cost: float = Field(ge=0, le=1)
    risk: float = Field(ge=0, le=1)
    learning_value: float = Field(ge=0, le=1)
    dependency_penalty: float = Field(ge=0, le=1)
    horizon_days: int | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)


class WritebackHints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_state_updates: list[str] = Field(default_factory=list)
    snapshot_updates: list[str] = Field(default_factory=list)
    plan_table: bool = False
    feedback_table: bool = False


class DecisionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluated_rules: list[str] = Field(default_factory=list)
    selected_rule: str
    timestamp: str
    schema_version: str | None = None
    model_version: str | None = None


class SceneOutputV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["scene_output_schema_v2"] = "scene_output_schema_v2"
    request_id: str
    decision_id: str
    scenario: str
    decision_type: str
    status: Literal["ok", "need_more_input", "blocked", "degraded", "error"]
    summary: str | None = None
    diagnostic_findings: list[DiagnosticFinding] = Field(default_factory=list)
    guidance: list[GuidanceItem] = Field(default_factory=list)
    suggestions: list[SuggestionItem] = Field(default_factory=list)
    next_actions: list[NextAction] = Field(default_factory=list)
    roi_breakdown: RoiBreakdown | None = None
    reason_codes: list[str] = Field(default_factory=list)
    why_selected: list[str] = Field(default_factory=list)
    why_not_others: list[WhyNotOther] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    writeback_hints: WritebackHints
    trace: DecisionTrace
```

## 6. 写作场景映射示例

### 6.1 写作

- `diagnostic_findings`
  - 问题、风险、优势、约束
- `guidance`
  - 训练方向、复盘重点、补强策略
- `suggestions`
  - 书籍、篇目、范文、素材
- `next_actions`
  - 写提纲、改开头、读范文、做模仿练习

### 6.2 旅价

- `diagnostic_findings`
  - 预算约束、时效约束、风险点
- `guidance`
  - 取舍建议、优先级建议、降本建议
- `suggestions`
  - 候选方案、备选方案、补充约束建议
- `next_actions`
  - 确认方案、放宽约束、继续比选

### 6.3 采购

- `diagnostic_findings`
  - 合规风险、履约风险、预算约束
- `guidance`
  - 谈判策略、选择策略、风险缓解策略
- `suggestions`
  - 供应商建议、替代方案、采购组合建议
- `next_actions`
  - 发起审批、补充条款、继续比选

## 7. 兼容与迁移

- 新场景一律按 `scene_output_schema_v2` 输出。
- 旧字段可以保留 alias，但不再作为新 schema 的扩展点。
- 场景差异只保留在：
  - `scenario`
  - `decision_type`
  - `item.kind`
  - `item.payload`
- `saibo_yanling` 负责把业务语言翻译成这些中性槽位。
- `velaris-agent` 负责把中性槽位映射为 ROI 决策和可解释输出。

## 8. 最小输出规则

- `diagnostic_findings`: 1-3 条
- `guidance`: 1-3 条
- `suggestions`: 1-3 条
- `next_actions`: 1-3 条

证据不足时：

- `status = "need_more_input"`
- 返回 `follow_up_questions`
- 不强行生成结论
