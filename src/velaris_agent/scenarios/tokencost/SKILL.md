---
name: tokencost
version: "1.0"
entry_point: "velaris_agent.biz.engine:_run_tokencost_scenario"
fallback_scenario: general
keywords:
  - tokencost
  - token
  - openai
  - anthropic
  - 模型成本
  - 降本
  - api 花费
  - 成本优化
capabilities:
  - usage_analyze
  - model_compare
  - saving_estimate
  - optimization_recommend
weights:
  cost: 0.50
  quality: 0.35
  speed: 0.15
governance:
  requires_audit: false
  approval_mode: default
  stop_profile: balanced
risk_level: low
recommended_tools:
  - biz_execute
  - tokencost_analyze
  - biz_plan
  - biz_score
---

# Token Cost Scenario

AI 模型成本分析场景，用量统计、模型对比、降本建议。
