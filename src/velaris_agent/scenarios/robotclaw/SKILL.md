---
name: robotclaw
version: "1.0"
entry_point: "velaris_agent.biz.engine:_run_robotclaw_scenario"
fallback_scenario: general
keywords:
  - robotclaw
  - dispatch
  - robotaxi
  - vehicle
  - proposal
  - 派单
  - 运力
  - 合约
  - 车端
capabilities:
  - intent_order
  - vehicle_match
  - proposal_score
  - contract_form
weights:
  safety: 0.40
  eta: 0.25
  cost: 0.20
  compliance: 0.15
governance:
  requires_audit: true
  approval_mode: strict
  stop_profile: strict_approval
risk_level: high
recommended_tools:
  - biz_execute
  - robotclaw_dispatch
  - biz_plan
  - biz_score
---

# RobotClaw Scenario

Robotaxi 派单与运力合约场景，高安全+合规要求，需审计追踪。
