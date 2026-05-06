---
name: procurement
version: "1.0"
keywords:
  - procurement
  - supplier
  - vendor
  - rfq
  - rfp
  - 采购
  - 供应商
  - 比价
  - 询价
  - 招标
  - 审计
  - 合规
  - 合同
  - 履约
capabilities:
  - intent_parse
  - supplier_compare
  - compliance_review
  - multi_dim_score
  - recommendation
weights:
  cost: 0.28
  quality: 0.24
  delivery: 0.16
  compliance: 0.22
  risk: 0.10
governance:
  requires_audit: true
  approval_mode: strict
  stop_profile: strict_approval
risk_level: high
recommended_tools:
  - biz_execute
  - biz_run_scenario
  - biz_plan
  - biz_score
---

# Procurement Scenario

企业采购场景，供应商比价、合规审计、多维度评分推荐。
