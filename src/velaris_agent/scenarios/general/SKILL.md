---
name: general
version: "1.0"
entry_point: "velaris_agent.biz.engine:_run_general_scenario"
fallback_scenario: general
keywords: []
capabilities:
  - generic_analysis
  - option_score
  - fallback_recommendation
weights:
  quality: 0.50
  cost: 0.30
  speed: 0.20
governance:
  requires_audit: false
  approval_mode: default
  stop_profile: balanced
risk_level: low
recommended_tools:
  - biz_execute
  - biz_plan
  - biz_score
  - biz_run_scenario
---

# General Scenario

通用兜底场景，当无法匹配具体场景时使用。提供通用评分、排序和推荐能力。
