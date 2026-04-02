/**
 * 实时成本追踪器
 * 记录每次 LLM 调用/工具调用的 token 消耗和费用
 */

import type { BudgetConfig, CostEventRecord, CostTracker, StorageAdapter } from '../types.js';
import { EventBus } from '../network/event-bus.js';

/** 成本追踪事件 */
interface TrackEvent {
  layer: string;
  eventType: string;
  tokensUsed: number;
  costUsd: number;
  metadata?: Record<string, unknown>;
}

/**
 * 会话级成本追踪器
 * 实时累计 token 和费用，超预算时触发事件
 */
export class SessionCostTracker implements CostTracker {
  private totalTokens = 0;
  private totalCostUsd = 0;
  private readonly events: CostEventRecord[] = [];

  constructor(
    private readonly sessionId: string,
    private readonly budget: BudgetConfig | undefined,
    private readonly storage: StorageAdapter,
    private readonly eventBus: EventBus,
  ) {}

  /** 记录一次成本事件 */
  track(event: TrackEvent): void {
    this.totalTokens += event.tokensUsed;
    this.totalCostUsd += event.costUsd;

    const record: CostEventRecord = {
      sessionId: this.sessionId,
      layer: event.layer,
      eventType: event.eventType,
      tokensUsed: event.tokensUsed,
      costUsd: event.costUsd,
      metadataJson: event.metadata ? JSON.stringify(event.metadata) : undefined,
      createdAt: Date.now(),
    };

    this.events.push(record);

    // 异步保存，不阻塞主流程
    void this.storage.saveCostEvent(record);

    // 发射成本事件
    this.eventBus.emit('cost:tracked', {
      sessionId: this.sessionId,
      layer: event.layer,
      costUsd: event.costUsd,
    });

    // 检查预算预警（80% 阈值）
    if (this.budget) {
      const tokenUsage = this.totalTokens / this.budget.maxTokensPerSession;
      const costUsage = this.totalCostUsd / this.budget.maxCostPerSession;
      const maxUsage = Math.max(tokenUsage, costUsage);

      if (maxUsage >= 0.8 && maxUsage < 1.0) {
        this.eventBus.emit('budget:warning', {
          sessionId: this.sessionId,
          usage: maxUsage,
          limit: 1.0,
        });
      }
    }
  }

  /** 获取累计 token 数 */
  getTotalTokens(): number {
    return this.totalTokens;
  }

  /** 获取累计花费 USD */
  getTotalCostUsd(): number {
    return this.totalCostUsd;
  }

  /** 检查是否超预算 */
  isBudgetExceeded(): boolean {
    if (!this.budget) return false;
    return (
      this.totalTokens >= this.budget.maxTokensPerSession ||
      this.totalCostUsd >= this.budget.maxCostPerSession
    );
  }

  /** 获取超预算策略 */
  getExceededStrategy(): BudgetConfig['onBudgetExceeded'] | null {
    if (!this.budget || !this.isBudgetExceeded()) return null;
    return this.budget.onBudgetExceeded;
  }

  /** 获取成本摘要 */
  getSummary(): {
    totalTokens: number;
    totalCostUsd: number;
    eventCount: number;
    costByLayer: Record<string, number>;
  } {
    const costByLayer: Record<string, number> = {};
    for (const event of this.events) {
      costByLayer[event.layer] = (costByLayer[event.layer] ?? 0) + (event.costUsd ?? 0);
    }

    return {
      totalTokens: this.totalTokens,
      totalCostUsd: this.totalCostUsd,
      eventCount: this.events.length,
      costByLayer,
    };
  }
}
