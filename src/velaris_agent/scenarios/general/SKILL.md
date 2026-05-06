---
name: general
version: "1.0"
keywords: []
capabilities:
  - generic_analysis
  - option_score
weights:
  quality: 0.50
  cost: 0.30
  speed: 0.20
governance:
  requires_audit: false
  approval_mode: default
  stop_profile: balanced
risk_level: medium
recommended_tools:
  - biz_execute
  - biz_plan
  - biz_score
  - biz_run_scenario
---

# General Scenario

通用兜底场景，当无法匹配具体场景时使用。
