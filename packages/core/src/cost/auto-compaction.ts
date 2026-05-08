/**
 * 自动上下文压缩（Auto-Compaction）
 * 参考 Claude Code 的压缩策略：
 * - Context 使用量 ~50% 时自动 LLM 摘要压缩
 * - 连续失败 3 次停止重试（防止无限循环）
 */

import type { LLMAdapter, LLMMessage, CostTracker } from '../types.js';
import type { EventBus } from '../network/event-bus.js';
import { ContextCompressor, type CompressionStrategy, type CompressionResult } from './compressor.js';

/** 压缩触发阈值（默认 50%） */
const DEFAULT_THRESHOLD = 0.5;

/** 最大连续失败次数 */
const MAX_CONSECUTIVE_FAILURES = 3;

/** 压缩事件 */
export interface CompactionEvent {
  /** 会话 ID */
  sessionId: string;
  /** 压缩前 token 数 */
  originalTokens: number;
  /** 压缩后 token 数 */
  compressedTokens: number;
  /** 压缩比 */
  compressionRatio: number;
  /** 使用的策略 */
  strategy: CompressionStrategy;
  /** 是否成功 */
  success: boolean;
  /** 错误信息 */
  error?: string;
}

/** 压缩状态 */
export interface CompactionState {
  /** 连续失败次数 */
  consecutiveFailures: number;
  /** 总压缩次数 */
  totalCompactions: number;
  /** 总节省 token 数 */
  totalTokensSaved: number;
  /** 上次压缩时间 */
  lastCompactionAt: number | null;
  /** 是否已禁用（连续失败过多） */
  disabled: boolean;
}

/**
 * 自动压缩器
 * 监控 context 使用量，自动触发压缩
 */
export class AutoCompaction {
  private readonly threshold: number;
  private readonly maxFailures: number;
  private readonly llm: LLMAdapter;
  private readonly model: string;
  private readonly costTracker?: CostTracker;
  private readonly eventBus?: EventBus;
  private state: CompactionState;
  private readonly sessionId: string;

  constructor(options: {
    sessionId: string;
    llm: LLMAdapter;
    model: string;
    threshold?: number;
    maxFailures?: number;
    costTracker?: CostTracker;
    eventBus?: EventBus;
  }) {
    this.sessionId = options.sessionId;
    this.llm = options.llm;
    this.model = options.model;
    this.threshold = options.threshold ?? DEFAULT_THRESHOLD;
    this.maxFailures = options.maxFailures ?? MAX_CONSECUTIVE_FAILURES;
    this.costTracker = options.costTracker;
    this.eventBus = options.eventBus;

    this.state = {
      consecutiveFailures: 0,
      totalCompactions: 0,
      totalTokensSaved: 0,
      lastCompactionAt: null,
      disabled: false,
    };
  }

  /**
   * 检查是否需要压缩
   * @param currentTokens 当前 token 数
   * @param maxTokens 最大 token 数
   */
  shouldCompact(currentTokens: number, maxTokens: number): boolean {
    if (this.state.disabled) return false;
    const usage = currentTokens / maxTokens;
    return usage >= this.threshold;
  }

  /**
   * 执行自动压缩
   * @param messages 当前消息列表
   * @param maxTokens 最大 token 数
   */
  async compact(messages: LLMMessage[], maxTokens: number): Promise<CompressionResult> {
    // 检查是否已禁用
    if (this.state.disabled) {
      return {
        messages,
        originalTokens: ContextCompressor.estimateMessagesTokens(messages),
        compressedTokens: ContextCompressor.estimateMessagesTokens(messages),
        strategy: 'truncate',
      };
    }

    const originalTokens = ContextCompressor.estimateMessagesTokens(messages);

    // 不需要压缩
    if (!this.shouldCompact(originalTokens, maxTokens)) {
      return {
        messages,
        originalTokens,
        compressedTokens: originalTokens,
        strategy: 'truncate',
      };
    }

    // 目标压缩到阈值的 80%
    const targetTokens = Math.floor(maxTokens * this.threshold * 0.8);

    try {
      // 尝试摘要压缩
      const result = await ContextCompressor.summarize(
        messages,
        targetTokens,
        this.llm,
        this.model
      );

      // 成功
      this.onSuccess(result);
      return result;
    } catch (err) {
      // 失败，尝试截断
      try {
        const result = ContextCompressor.truncate(messages, targetTokens);
        this.onSuccess(result);
        return result;
      } catch (fallbackErr) {
        // 完全失败
        this.onFailure(err);
        return {
          messages,
          originalTokens,
          compressedTokens: originalTokens,
          strategy: 'truncate',
        };
      }
    }
  }

  /** 压缩成功处理 */
  private onSuccess(result: CompressionResult): void {
    const tokensSaved = result.originalTokens - result.compressedTokens;

    this.state.consecutiveFailures = 0;
    this.state.totalCompactions++;
    this.state.totalTokensSaved += tokensSaved;
    this.state.lastCompactionAt = Date.now();

    // 记录成本
    if (this.costTracker) {
      this.costTracker.track({
        layer: 'auto-compaction',
        eventType: 'compress',
        tokensUsed: result.compressedTokens,
        costUsd: 0, // 压缩本身的成本已在 LLM 调用中记录
        metadata: {
          originalTokens: result.originalTokens,
          compressedTokens: result.compressedTokens,
          strategy: result.strategy,
        },
      });
    }

    // 发射事件
    const event: CompactionEvent = {
      sessionId: this.sessionId,
      originalTokens: result.originalTokens,
      compressedTokens: result.compressedTokens,
      compressionRatio: result.compressedTokens / result.originalTokens,
      strategy: result.strategy,
      success: true,
    };
    this.eventBus?.emit('cost:compacted', event);
  }

  /** 压缩失败处理 */
  private onFailure(err: unknown): void {
    this.state.consecutiveFailures++;

    // 连续失败过多，禁用压缩
    if (this.state.consecutiveFailures >= this.maxFailures) {
      this.state.disabled = true;
    }

    // 发射事件
    const event: CompactionEvent = {
      sessionId: this.sessionId,
      originalTokens: 0,
      compressedTokens: 0,
      compressionRatio: 1,
      strategy: 'summarize',
      success: false,
      error: err instanceof Error ? err.message : String(err),
    };
    this.eventBus?.emit('cost:compacted', event);
  }

  /** 获取状态 */
  getState(): CompactionState {
    return { ...this.state };
  }

  /** 重置状态（重新启用压缩） */
  reset(): void {
    this.state = {
      consecutiveFailures: 0,
      totalCompactions: 0,
      totalTokensSaved: 0,
      lastCompactionAt: null,
      disabled: false,
    };
  }

  /** 重新启用压缩 */
  enable(): void {
    this.state.disabled = false;
    this.state.consecutiveFailures = 0;
  }

  /** 禁用压缩 */
  disable(): void {
    this.state.disabled = true;
  }

  /** 是否已禁用 */
  isDisabled(): boolean {
    return this.state.disabled;
  }

  /** 获取压缩统计 */
  getStats(): {
    totalCompactions: number;
    totalTokensSaved: number;
    averageCompressionRatio: number;
    disabled: boolean;
  } {
    return {
      totalCompactions: this.state.totalCompactions,
      totalTokensSaved: this.state.totalTokensSaved,
      averageCompressionRatio:
        this.state.totalCompactions > 0
          ? 1 - this.state.totalTokensSaved / (this.state.totalTokensSaved + 1)
          : 1,
      disabled: this.state.disabled,
    };
  }
}

/**
 * 批量压缩助手
 * 用于压缩多个消息块
 */
export class BatchCompaction {
  private readonly autoCompaction: AutoCompaction;

  constructor(autoCompaction: AutoCompaction) {
    this.autoCompaction = autoCompaction;
  }

  /**
   * 压缩多个消息块
   * @param blocks 消息块列表
   * @param maxTokensPerBlock 每块最大 token
   */
  async compactBlocks(
    blocks: LLMMessage[][],
    maxTokensPerBlock: number
  ): Promise<CompressionResult[]> {
    const results: CompressionResult[] = [];

    for (const block of blocks) {
      const result = await this.autoCompaction.compact(block, maxTokensPerBlock);
      results.push(result);
    }

    return results;
  }

  /**
   * 选择性压缩
   * 只压缩超过阈值的块
   */
  async compactIfNeeded(
    blocks: LLMMessage[][],
    maxTokensPerBlock: number
  ): Promise<{ index: number; result: CompressionResult }[]> {
    const results: { index: number; result: CompressionResult }[] = [];

    for (let i = 0; i < blocks.length; i++) {
      const block = blocks[i]!;
      const tokens = ContextCompressor.estimateMessagesTokens(block);

      if (this.autoCompaction.shouldCompact(tokens, maxTokensPerBlock)) {
        const result = await this.autoCompaction.compact(block, maxTokensPerBlock);
        results.push({ index: i, result });
      }
    }

    return results;
  }
}
