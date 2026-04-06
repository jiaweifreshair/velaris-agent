/**
 * 默认路由策略（OpenHarness 二开版）
 * 作用：提供开箱即用的策略路由配置，避免用户首次接入时必须手写策略。
 */

import type { RoutingPolicy } from '../types.js';

/** 默认策略配置：与 config/routing-policy.yaml 保持同一语义。 */
export const defaultRoutingPolicy: RoutingPolicy = {
  version: 1,
  policyId: 'velaris-dual-mode-routing-v1',
  defaults: {
    strategy: 'local_closed_loop',
    stopProfile: 'balanced',
    reason: '默认本地闭环',
  },
  stopProfiles: {
    strict_approval: {
      description: '高风险任务优先安全，命中条件即停并升级处理',
      onMatch: 'stop',
      conditionIds: ['budget_exhausted', 'approval_timeout', 'authority_violation', 'high_risk_conflict'],
      maxRetries: 0,
      escalateTo: 'human',
    },
    balanced: {
      description: '平衡质量与成本，允许有限降级',
      onMatch: 'degrade',
      conditionIds: ['budget_exhausted', 'evidence_conflict', 'runtime_unhealthy'],
      maxRetries: 1,
      escalateTo: 'policy_engine',
    },
    fast_fail: {
      description: '低价值探索任务快速失败',
      onMatch: 'stop',
      conditionIds: ['latency_exhausted', 'runtime_unhealthy'],
      maxRetries: 0,
      escalateTo: 'none',
    },
  },
  strategies: {
    local_closed_loop: {
      mode: 'local',
      runtime: 'self',
      autonomy: 'auto',
      maxParallelWorkers: 2,
      requiredCapabilities: ['read', 'reason'],
    },
    delegated_openclaw: {
      mode: 'delegated',
      runtime: 'openclaw',
      autonomy: 'supervised',
      maxParallelWorkers: 4,
      requiredCapabilities: ['read', 'write', 'exec', 'audit'],
    },
    delegated_claude_code: {
      mode: 'delegated',
      runtime: 'claude_code',
      autonomy: 'accept_edits',
      maxParallelWorkers: 3,
      requiredCapabilities: ['read', 'write', 'exec'],
    },
    hybrid_openclaw_claudecode: {
      mode: 'hybrid',
      runtime: 'mixed',
      autonomy: 'supervised',
      maxParallelWorkers: 5,
      requiredCapabilities: ['read', 'write', 'exec', 'audit'],
    },
  },
  rules: [
    {
      id: 'R001_high_risk_go_openclaw',
      priority: 1000,
      when: {
        all: [{ field: 'risk.level', op: 'in', value: ['high', 'critical'] }],
      },
      route: {
        strategy: 'delegated_openclaw',
        stopProfile: 'strict_approval',
        reason: '高风险任务进入治理优先路径',
      },
    },
    {
      id: 'R002_code_heavy_go_claude_code',
      priority: 900,
      when: {
        all: [
          { field: 'capabilityDemand.writeCode', op: 'eq', value: true },
          { field: 'state.taskComplexity', op: 'in', value: ['medium', 'complex'] },
        ],
      },
      route: {
        strategy: 'delegated_claude_code',
        stopProfile: 'balanced',
        reason: '代码改动密集任务由 Claude Code 执行',
      },
    },
    {
      id: 'R003_audit_required_go_openclaw',
      priority: 850,
      when: {
        all: [{ field: 'governance.requiresAuditTrail', op: 'eq', value: true }],
      },
      route: {
        strategy: 'delegated_openclaw',
        stopProfile: 'strict_approval',
        reason: '审计要求任务进入 OpenClaw',
      },
    },
    {
      id: 'R004_cross_system_use_hybrid',
      priority: 950,
      when: {
        all: [
          { field: 'capabilityDemand.externalSideEffects', op: 'eq', value: true },
          { field: 'capabilityDemand.writeCode', op: 'eq', value: true },
        ],
      },
      route: {
        strategy: 'hybrid_openclaw_claudecode',
        stopProfile: 'strict_approval',
        reason: '跨系统副作用且写代码，进入混合路径',
      },
    },
    {
      id: 'R005_simple_local',
      priority: 300,
      when: {
        all: [
          { field: 'risk.level', op: 'in', value: ['low', 'medium'] },
          { field: 'state.taskComplexity', op: 'eq', value: 'simple' },
          { field: 'capabilityDemand.externalSideEffects', op: 'eq', value: false },
        ],
      },
      route: {
        strategy: 'local_closed_loop',
        stopProfile: 'fast_fail',
        reason: '低风险简单任务本地闭环',
      },
    },
  ],
  fallback: {
    strategy: 'local_closed_loop',
    stopProfile: 'balanced',
    reason: '无规则命中时回退到本地闭环',
  },
};
