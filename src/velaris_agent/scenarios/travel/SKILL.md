---
name: travel
version: "1.0"
entry_point: "velaris_agent.biz.engine:_run_travel_scenario"
fallback_scenario: general
keywords:
  - travel
  - flight
  - hotel
  - trip
  - 商旅
  - 出差
  - 机票
  - 酒店
capabilities:
  - intent_parse
  - inventory_search
  - option_score
  - itinerary_recommend
weights:
  price: 0.40
  time: 0.35
  comfort: 0.25
governance:
  requires_audit: false
  approval_mode: default
  stop_profile: balanced
risk_level: medium
recommended_tools:
  - biz_execute
  - travel_recommend
  - travel_compare
  - biz_plan
  - biz_score
---

# Travel Scenario

商旅对比与推荐场景，支持机票搜索、行程规划、多维度评分排序。
