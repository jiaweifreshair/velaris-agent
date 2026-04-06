/**
 * Cost Tracker + Budget Manager 单元测试
 * 验证成本追踪、预算检查、超限策略
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { SessionCostTracker } from '../src/cost/tracker.js';
import { BudgetManager } from '../src/cost/budget.js';
import { EventBus } from '../src/network/event-bus.js';
import { MemoryStorage } from '../src/adapters/memory-storage.js';
import type { BudgetConfig } from '../src/types.js';

describe('SessionCostTracker', () => {
  let storage: MemoryStorage;
  let eventBus: EventBus;

  beforeEach(() => {
    storage = new MemoryStorage();
    eventBus = new EventBus();
  });

  it('应正确累计 token 和费用', () => {
    const tracker = new SessionCostTracker('sess_1', undefined, storage, eventBus);

    tracker.track({ layer: 'executor', eventType: 'llm_call', tokensUsed: 1000, costUsd: 0.01 });
    tracker.track({ layer: 'executor', eventType: 'llm_call', tokensUsed: 2000, costUsd: 0.02 });

    expect(tracker.getTotalTokens()).toBe(3000);
    expect(tracker.getTotalCostUsd()).toBeCloseTo(0.03);
  });

  it('无预算时 isBudgetExceeded 应返回 false', () => {
    const tracker = new SessionCostTracker('sess_1', undefined, storage, eventBus);
    tracker.track({ layer: 'executor', eventType: 'llm_call', tokensUsed: 999999, costUsd: 100 });
    expect(tracker.isBudgetExceeded()).toBe(false);
  });

  it('超过 token 预算时应返回 true', () => {
    const budget: BudgetConfig = {
      maxTokensPerSession: 5000,
      maxCostPerSession: 1.0,
      onBudgetExceeded: 'stop',
    };

    const tracker = new SessionCostTracker('sess_1', budget, storage, eventBus);
    tracker.track({ layer: 'executor', eventType: 'llm_call', tokensUsed: 5001, costUsd: 0.01 });
    expect(tracker.isBudgetExceeded()).toBe(true);
  });

  it('超过费用预算时应返回 true', () => {
    const budget: BudgetConfig = {
      maxTokensPerSession: 100000,
      maxCostPerSession: 0.5,
      onBudgetExceeded: 'stop',
    };

    const tracker = new SessionCostTracker('sess_1', budget, storage, eventBus);
    tracker.track({ layer: 'executor', eventType: 'llm_call', tokensUsed: 100, costUsd: 0.51 });
    expect(tracker.isBudgetExceeded()).toBe(true);
  });

  it('达到 80% 预算时应发射预警事件', () => {
    const budget: BudgetConfig = {
      maxTokensPerSession: 10000,
      maxCostPerSession: 1.0,
      onBudgetExceeded: 'stop',
    };

    const warnings: unknown[] = [];
    eventBus.on('budget:warning', (data) => warnings.push(data));

    const tracker = new SessionCostTracker('sess_1', budget, storage, eventBus);
    tracker.track({ layer: 'executor', eventType: 'llm_call', tokensUsed: 8500, costUsd: 0.01 });

    expect(warnings).toHaveLength(1);
  });

  it('getCostSummary 应返回按层分组的成本', () => {
    const tracker = new SessionCostTracker('sess_1', undefined, storage, eventBus);

    tracker.track({ layer: 'planner', eventType: 'llm_call', tokensUsed: 500, costUsd: 0.005 });
    tracker.track({ layer: 'executor', eventType: 'llm_call', tokensUsed: 1000, costUsd: 0.01 });
    tracker.track({ layer: 'executor', eventType: 'tool_call', tokensUsed: 200, costUsd: 0.002 });

    const summary = tracker.getSummary();
    expect(summary.totalTokens).toBe(1700);
    expect(summary.eventCount).toBe(3);
    expect(summary.costByLayer['planner']).toBeCloseTo(0.005);
    expect(summary.costByLayer['executor']).toBeCloseTo(0.012);
  });
});

describe('BudgetManager', () => {
  it('无预算配置时应允许所有操作', () => {
    const manager = new BudgetManager(undefined);
    const mockTracker = {
      getTotalTokens: () => 999999,
      getTotalCostUsd: () => 100,
      isBudgetExceeded: () => false,
      track: vi.fn(),
    };

    const result = manager.check(mockTracker);
    expect(result.allowed).toBe(true);
    expect(result.remainingTokens).toBe(Infinity);
  });

  it('未超限时应返回 continue', () => {
    const manager = new BudgetManager({
      maxTokensPerSession: 10000,
      maxCostPerSession: 1.0,
      onBudgetExceeded: 'stop',
    });

    const mockTracker = {
      getTotalTokens: () => 5000,
      getTotalCostUsd: () => 0.3,
      isBudgetExceeded: () => false,
      track: vi.fn(),
    };

    const result = manager.check(mockTracker);
    expect(result.allowed).toBe(true);
    expect(result.action).toBe('continue');
    expect(result.remainingTokens).toBe(5000);
  });

  it('stop 策略超限时应拒绝执行', () => {
    const manager = new BudgetManager({
      maxTokensPerSession: 10000,
      maxCostPerSession: 1.0,
      onBudgetExceeded: 'stop',
    });

    const mockTracker = {
      getTotalTokens: () => 11000,
      getTotalCostUsd: () => 0.3,
      isBudgetExceeded: () => true,
      track: vi.fn(),
    };

    const result = manager.check(mockTracker);
    expect(result.allowed).toBe(false);
    expect(result.action).toBe('stop');
  });

  it('compress 策略超限时应允许但标记降级', () => {
    const manager = new BudgetManager({
      maxTokensPerSession: 10000,
      maxCostPerSession: 1.0,
      onBudgetExceeded: 'compress',
    });

    const mockTracker = {
      getTotalTokens: () => 11000,
      getTotalCostUsd: () => 0.3,
      isBudgetExceeded: () => true,
      track: vi.fn(),
    };

    const result = manager.check(mockTracker);
    expect(result.allowed).toBe(true);
    expect(result.action).toBe('compress');
  });

  it('enforce 在 stop 策略超限时应抛出 BudgetExceededError', () => {
    const manager = new BudgetManager({
      maxTokensPerSession: 10000,
      maxCostPerSession: 1.0,
      onBudgetExceeded: 'stop',
    });

    const mockTracker = {
      getTotalTokens: () => 11000,
      getTotalCostUsd: () => 1.5,
      isBudgetExceeded: () => true,
      track: vi.fn(),
    };

    expect(() => manager.enforce(mockTracker)).toThrow('Budget exceeded');
  });
});
