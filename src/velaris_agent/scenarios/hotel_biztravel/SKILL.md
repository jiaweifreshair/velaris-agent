---
name: hotel_biztravel
version: "1.0"
keywords:
  - hotel_biztravel
  - 商旅礼宾
  - 酒店礼宾
  - 联合决策
  - bundle
capabilities:
  - intent_parse
  - candidate_normalize
  - bundle_planning
  - feasibility_filter
  - joint_ranking
  - need_inference
  - preference_writeback
  - decision_explanation
  - memory_recall
weights:
  price: 0.20
  eta: 0.30
  detour_cost: 0.20
  preference_match: 0.20
  experience_value: 0.10
governance:
  requires_audit: false
  approval_mode: default
  stop_profile: balanced
risk_level: medium
recommended_tools:
  - recall_preferences
  - recall_decisions
  - biz_execute
  - decision_score
  - save_decision
  - biz_plan
  - biz_score
---

# Hotel BizTravel Scenario

商旅礼宾联合决策场景，酒店+机票组合推荐，偏好推断与回写。
