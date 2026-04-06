/**
 * 路由与治理骨架测试
 * 验证 OpenHarness 二开新增模块的基础行为。
 */

import { describe, it, expect } from 'vitest';
import { PolicyRouter } from '../src/policy/router.js';
import { defaultRoutingPolicy } from '../src/policy/default-routing-policy.js';
import { AuthorityService } from '../src/governance/authority.js';
import { TaskLedger } from '../src/control/task-ledger.js';
import { OutcomeStore } from '../src/eval/outcome-store.js';
import type { RoutingContext } from '../src/types.js';

function makeRoutingContext(overrides: Partial<RoutingContext> = {}): RoutingContext {
  return {
    requestId: 'req_1',
    timestamp: '2026-04-04T00:00:00.000Z',
    goal: {
      goalType: 'token_optimize',
      userId: 'u1',
      intent: '优化 token 成本',
      constraints: {},
      sessionId: 'sess_1',
    },
    risk: { level: 'low' },
    state: {
      taskComplexity: 'simple',
      evidenceConflict: false,
      toolHealth: 'healthy',
    },
    budgets: {
      remainingTokens: 50000,
      remainingCostUsd: 1,
      remainingLatencyMs: 30000,
    },
    capabilityDemand: {
      readCode: true,
      writeCode: false,
      execCommand: false,
      networkAccess: true,
      externalSideEffects: false,
    },
    governance: {
      requiresAuditTrail: false,
      approvalMode: 'none',
    },
    availableRuntimes: ['self', 'openclaw', 'claude_code', 'mixed'],
    ...overrides,
  };
}

describe('PolicyRouter', () => {
  it('低风险简单任务应命中本地闭环策略', () => {
    const router = new PolicyRouter(defaultRoutingPolicy);
    const result = router.route(makeRoutingContext());

    expect(result.selectedStrategy).toBe('local_closed_loop');
    expect(result.selectedRoute.runtime).toBe('self');
  });

  it('高风险任务应命中 delegated_openclaw', () => {
    const router = new PolicyRouter(defaultRoutingPolicy);
    const result = router.route(
      makeRoutingContext({
        risk: { level: 'high' },
      }),
    );

    expect(result.selectedStrategy).toBe('delegated_openclaw');
    expect(result.selectedRoute.runtime).toBe('openclaw');
  });
});

describe('AuthorityService', () => {
  it('strict 审批模式必须要求审批并签发令牌', () => {
    const authority = new AuthorityService();
    const plan = authority.issuePlan(['read', 'exec'], {
      requiresAuditTrail: true,
      approvalMode: 'strict',
    });

    expect(plan.approvalsRequired).toBe(true);
    expect(plan.capabilityTokens).toHaveLength(1);
    expect(plan.capabilityTokens[0]!.scope).toContain('exec');
  });
});

describe('TaskLedger & OutcomeStore', () => {
  it('应支持任务生命周期与 outcome 回写', () => {
    const ledger = new TaskLedger();
    const task = ledger.createTask({
      sessionId: 'sess_2',
      runtime: 'self',
      role: 'worker',
      objective: '执行测试任务',
    });

    ledger.updateStatus(task.taskId, 'running');
    ledger.updateStatus(task.taskId, 'completed');
    const sessionTasks = ledger.listBySession('sess_2');
    expect(sessionTasks).toHaveLength(1);
    expect(sessionTasks[0]!.status).toBe('completed');

    const store = new OutcomeStore();
    const outcome = store.record({
      sessionId: 'sess_2',
      selectedStrategy: 'local_closed_loop',
      qualityScore: 0.92,
      totalCostUsd: 0.03,
      totalLatencyMs: 1200,
      success: true,
    });
    expect(outcome.createdAt).toBeGreaterThan(0);
    expect(store.listBySession('sess_2')).toHaveLength(1);
  });
});
