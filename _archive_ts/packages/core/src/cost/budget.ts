/**
 * Token Budget 管理器
 * 管理预算分配、超限策略、降级决策
 */

import type { BudgetConfig, CostTracker } from '../types.js';
import { BudgetExceededError } from '@velaris/shared';

/** 预算检查结果 */
export interface BudgetCheckResult {
  /** 是否允许继续执行 */
  allowed: boolean;
  /** 需要执行的策略 */
  action: 'continue' | 'compress' | 'downgrade' | 'stop';
  /** 剩余 token 预算 */
  remainingTokens: number;
  /** 剩余费用预算 USD */
  remainingCostUsd: number;
  /** 当前使用率 0-1 */
  usageRatio: number;
}

/**
 * 预算管理器
 * 在每次 Skill 执行前检查预算，决定是否降级或终止
 */
export class BudgetManager {
  constructor(private readonly config: BudgetConfig | undefined) {}

  /** 执行前预算检查 */
  check(tracker: CostTracker): BudgetCheckResult {
    // 无预算限制，直接放行
    if (!this.config) {
      return {
        allowed: true,
        action: 'continue',
        remainingTokens: Infinity,
        remainingCostUsd: Infinity,
        usageRatio: 0,
      };
    }

    const remainingTokens = this.config.maxTokensPerSession - tracker.getTotalTokens();
    const remainingCostUsd = this.config.maxCostPerSession - tracker.getTotalCostUsd();

    const tokenRatio = tracker.getTotalTokens() / this.config.maxTokensPerSession;
    const costRatio = tracker.getTotalCostUsd() / this.config.maxCostPerSession;
    const usageRatio = Math.max(tokenRatio, costRatio);

    // 未超限
    if (usageRatio < 1.0) {
      return {
        allowed: true,
        action: 'continue',
        remainingTokens: Math.max(0, remainingTokens),
        remainingCostUsd: Math.max(0, remainingCostUsd),
        usageRatio,
      };
    }

    // 已超限，根据策略决定
    const action = this.config.onBudgetExceeded;

    if (action === 'stop') {
      return {
        allowed: false,
        action: 'stop',
        remainingTokens: 0,
        remainingCostUsd: 0,
        usageRatio,
      };
    }

    // compress 或 downgrade 仍允许继续，但标记需要降级
    return {
      allowed: true,
      action,
      remainingTokens: Math.max(0, remainingTokens),
      remainingCostUsd: Math.max(0, remainingCostUsd),
      usageRatio,
    };
  }

  /** 超限时抛出异常（用于 stop 策略） */
  enforce(tracker: CostTracker): void {
    const result = this.check(tracker);
    if (!result.allowed) {
      throw new BudgetExceededError(
        `Budget exceeded: ${tracker.getTotalTokens()} tokens, $${tracker.getTotalCostUsd().toFixed(4)}`,
        tracker.getTotalTokens(),
        tracker.getTotalCostUsd(),
      );
    }
  }
}
