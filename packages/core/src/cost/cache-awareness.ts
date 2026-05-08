/**
 * Prompt Cache 感知系统
 * 参考 Claude Code 的 Prompt Cache 优化：
 * - 追踪 cache-break 向量
 * - 系统提示词变更追踪
 * - 缓存效率评分
 */

import type { EventBus } from '../network/event-bus.js';

/** Cache-break 向量类型 */
export type CacheBreakVector =
  | 'system_prompt_change'
  | 'user_context_change'
  | 'tool_definition_change'
  | 'memory_update'
  | 'config_change'
  | 'date_change'
  | 'session_state_change';

/** Cache-break 事件 */
export interface CacheBreakEvent {
  /** 时间戳 */
  timestamp: number;
  /** 向量类型 */
  vector: CacheBreakVector;
  /** 变更描述 */
  description: string;
  /** 影响范围（估算 token 数） */
  impactTokens: number;
  /** 来源 */
  source: string;
}

/** 系统提示词版本 */
export interface SystemPromptVersion {
  /** 版本 ID */
  id: string;
  /** 内容哈希 */
  hash: string;
  /** 时间戳 */
  timestamp: number;
  /** token 数 */
  tokens: number;
  /** 变更描述 */
  changeDescription?: string;
}

/** Cache 统计 */
export interface CacheStats {
  /** 总请求数 */
  totalRequests: number;
  /** 缓存命中数 */
  cacheHits: number;
  /** 缓存未命中数 */
  cacheMisses: number;
  /** 命中率 */
  hitRate: number;
  /** 节省的 token 数 */
  tokensSaved: number;
  /** 节省的成本 USD */
  costSavedUsd: number;
}

/** Cache 感知配置 */
export interface CacheAwarenessConfig {
  /** 是否启用 */
  enabled: boolean;
  /** 系统提示词变更检测 */
  trackSystemPrompt: boolean;
  /** 记忆变更检测 */
  trackMemoryUpdates: boolean;
  /** 最大历史记录数 */
  maxHistorySize: number;
}

const DEFAULT_CONFIG: CacheAwarenessConfig = {
  enabled: true,
  trackSystemPrompt: true,
  trackMemoryUpdates: true,
  maxHistorySize: 1000,
};

/**
 * Prompt Cache 感知管理器
 * 追踪影响缓存效率的因素
 */
export class CacheAwareness {
  private readonly config: CacheAwarenessConfig;
  private readonly sessionId: string;
  private readonly eventBus?: EventBus;

  /** Cache-break 事件历史 */
  private breakHistory: CacheBreakEvent[] = [];

  /** 系统提示词版本历史 */
  private systemPromptVersions: SystemPromptVersion[] = [];

  /** 当前系统提示词哈希 */
  private currentSystemPromptHash: string | null = null;

  /** Cache 统计 */
  private stats: CacheStats = {
    totalRequests: 0,
    cacheHits: 0,
    cacheMisses: 0,
    hitRate: 0,
    tokensSaved: 0,
    costSavedUsd: 0,
  };

  /** 上次缓存键 */
  private lastCacheKey: string | null = null;

  constructor(sessionId: string, config: Partial<CacheAwarenessConfig> = {}, eventBus?: EventBus) {
    this.sessionId = sessionId;
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.eventBus = eventBus;
  }

  /**
   * 记录 cache-break 事件
   */
  recordBreak(event: Omit<CacheBreakEvent, 'timestamp'>): void {
    if (!this.config.enabled) return;

    const fullEvent: CacheBreakEvent = {
      ...event,
      timestamp: Date.now(),
    };

    this.breakHistory.push(fullEvent);

    // 限制历史大小
    if (this.breakHistory.length > this.config.maxHistorySize) {
      this.breakHistory = this.breakHistory.slice(-this.config.maxHistorySize);
    }

    // 发射事件
    this.eventBus?.emit('cache:break', {
      sessionId: this.sessionId,
      reason: `cache-break: ${fullEvent.vector}`,
      cacheHitRate: this.getCacheHitRate(),
    });
  }

  /**
   * 检测系统提示词变更
   * 参考 Claude Code 的 DANGEROUS_uncachedSystemPromptSection() 命名规范
   */
  detectSystemPromptChange(
    prompt: string,
    source: string
  ): SystemPromptVersion | null {
    if (!this.config.enabled || !this.config.trackSystemPrompt) {
      return null;
    }

    const hash = this.hashString(prompt);
    const tokens = this.estimateTokens(prompt);

    // 无变更
    if (hash === this.currentSystemPromptHash) {
      return null;
    }

    // 创建新版本
    const version: SystemPromptVersion = {
      id: `sp_${Date.now()}`,
      hash,
      timestamp: Date.now(),
      tokens,
      changeDescription: this.currentSystemPromptHash
        ? 'System prompt changed'
        : 'Initial system prompt',
    };

    // 记录变更
    this.systemPromptVersions.push(version);
    this.currentSystemPromptHash = hash;

    // 记录 cache-break
    this.recordBreak({
      vector: 'system_prompt_change',
      description: version.changeDescription ?? 'System prompt change',
      impactTokens: tokens,
      source,
    });

    return version;
  }

  /**
   * 标记危险区域（不缓存的系统提示词部分）
   * 命名参考 Claude Code 的 DANGEROUS_uncachedSystemPromptSection
   */
  DANGEROUS_uncachedSystemPromptSection(
    section: string,
    reason: string
  ): { section: string; reason: string; tokens: number } {
    const tokens = this.estimateTokens(section);
    this.recordBreak({
      vector: 'system_prompt_change',
      description: `Uncached section: ${reason}`,
      impactTokens: tokens,
      source: 'DANGEROUS_uncachedSystemPromptSection',
    });

    return { section, reason, tokens };
  }

  /**
   * 记录记忆更新
   */
  recordMemoryUpdate(description: string, impactTokens: number): void {
    if (!this.config.enabled || !this.config.trackMemoryUpdates) return;

    this.recordBreak({
      vector: 'memory_update',
      description,
      impactTokens,
      source: 'memory',
    });
  }

  /**
   * 记录缓存请求结果
   */
  recordCacheRequest(hit: boolean, tokensCached: number, costPerToken: number): void {
    if (!this.config.enabled) return;

    this.stats.totalRequests++;

    if (hit) {
      this.stats.cacheHits++;
      this.stats.tokensSaved += tokensCached;
      this.stats.costSavedUsd += tokensCached * costPerToken;
    } else {
      this.stats.cacheMisses++;
    }

    this.stats.hitRate = this.stats.cacheHits / this.stats.totalRequests;
  }

  /**
   * 生成缓存键
   * 基于当前状态生成稳定的缓存键
   */
  generateCacheKey(components: Record<string, string | number | boolean>): string {
    const sorted = Object.entries(components)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${k}=${v}`)
      .join('&');

    return this.hashString(sorted);
  }

  /**
   * 检查是否可以复用上次缓存
   */
  canReuseLastCache(newKey: string): boolean {
    return this.lastCacheKey === newKey;
  }

  /**
   * 更新缓存键
   */
  updateCacheKey(key: string): void {
    this.lastCacheKey = key;
  }

  /**
   * 获取缓存效率评分
   * 0-100 分，越高越好
   */
  getEfficiencyScore(): number {
    if (this.stats.totalRequests === 0) return 100;

    // 命中率权重 60%
    const hitRateScore = this.stats.hitRate * 60;

    // cache-break 频率权重 40%（越少越好）
    const recentBreaks = this.breakHistory.filter(
      (e) => Date.now() - e.timestamp < 60 * 60 * 1000 // 最近 1 小时
    ).length;
    const breakScore = Math.max(0, 40 - recentBreaks);

    return Math.min(100, hitRateScore + breakScore);
  }

  /**
   * 获取统计信息
   */
  getStats(): CacheStats {
    return { ...this.stats };
  }

  /** 计算缓存命中率（基于 break 历史） */
  getCacheHitRate(): number {
    if (this.stats.totalRequests === 0) return 1.0;
    return this.stats.hitRate;
  }

  /**
   * 获取 cache-break 历史
   */
  getBreakHistory(limit = 100): CacheBreakEvent[] {
    return this.breakHistory.slice(-limit);
  }

  /**
   * 获取系统提示词版本历史
   */
  getSystemPromptHistory(limit = 10): SystemPromptVersion[] {
    return this.systemPromptVersions.slice(-limit);
  }

  /**
   * 获取最近的 cache-break 向量
   */
  getRecentBreakVectors(timeWindowMs = 60 * 60 * 1000): CacheBreakVector[] {
    const now = Date.now();
    const vectors = new Set<CacheBreakVector>();

    for (const event of this.breakHistory) {
      if (now - event.timestamp <= timeWindowMs) {
        vectors.add(event.vector);
      }
    }

    return [...vectors];
  }

  /**
   * 分析缓存效率问题
   */
  analyzeEfficiencyIssues(): string[] {
    const issues: string[] = [];
    const score = this.getEfficiencyScore();

    if (score < 50) {
      issues.push('Cache efficiency is critically low. Consider reviewing system prompt stability.');
    }

    // 检查频繁的 cache-break
    const recentBreaks = this.getBreakHistory(100);
    const breakCounts = new Map<CacheBreakVector, number>();

    for (const event of recentBreaks) {
      breakCounts.set(event.vector, (breakCounts.get(event.vector) ?? 0) + 1);
    }

    for (const [vector, count] of breakCounts) {
      if (count > 10) {
        issues.push(`Frequent ${vector} events (${count} in recent history). Consider stabilizing.`);
      }
    }

    // 检查系统提示词变更
    const promptHistory = this.getSystemPromptHistory();
    if (promptHistory.length > 5) {
      issues.push('System prompt changes frequently. Consider using stable sections with dynamic injection.');
    }

    return issues;
  }

  /**
   * 重置统计
   */
  reset(): void {
    this.breakHistory = [];
    this.systemPromptVersions = [];
    this.stats = {
      totalRequests: 0,
      cacheHits: 0,
      cacheMisses: 0,
      hitRate: 0,
      tokensSaved: 0,
      costSavedUsd: 0,
    };
    this.lastCacheKey = null;
  }

  // ─── 私有方法 ───────────────────────────────────────────

  /** 简单字符串哈希 */
  private hashString(str: string): string {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = (hash << 5) - hash + char;
      hash = hash & hash; // Convert to 32bit integer
    }
    return hash.toString(16);
  }

  /** 估算 token 数 */
  private estimateTokens(text: string): number {
    // 简单估算：英文约 4 字符/token
    return Math.ceil(text.length / 4);
  }
}

/**
 * 创建 cache 感知的系统提示词构建器
 */
export class CacheAwarePromptBuilder {
  private readonly cacheAwareness: CacheAwareness;
  private readonly stableSections: Map<string, string> = new Map();
  private readonly dynamicSections: Map<string, () => string> = new Map();

  constructor(cacheAwareness: CacheAwareness) {
    this.cacheAwareness = cacheAwareness;
  }

  /**
   * 注册稳定部分（可缓存）
   */
  registerStableSection(name: string, content: string): void {
    this.stableSections.set(name, content);
  }

  /**
   * 注册动态部分（不缓存）
   * 使用 DANGEROUS_ 前缀标记
   */
  DANGEROUS_registerDynamicSection(name: string, generator: () => string): void {
    this.dynamicSections.set(name, generator);
  }

  /**
   * 构建完整提示词
   */
  build(): { prompt: string; stableTokens: number; dynamicTokens: number } {
    const stableParts: string[] = [];
    const dynamicParts: string[] = [];

    // 收集稳定部分
    for (const [name, content] of this.stableSections) {
      stableParts.push(`<!-- stable: ${name} -->\n${content}`);
    }

    // 收集动态部分
    for (const [name, generator] of this.dynamicSections) {
      const content = generator();
      dynamicParts.push(`<!-- dynamic: ${name} -->\n${content}`);

      // 记录危险区域
      this.cacheAwareness.DANGEROUS_uncachedSystemPromptSection(
        content,
        `Dynamic section: ${name}`
      );
    }

    const stableContent = stableParts.join('\n\n');
    const dynamicContent = dynamicParts.join('\n\n');
    const prompt = `${stableContent}\n\n${dynamicContent}`;

    // 检测变更
    this.cacheAwareness.detectSystemPromptChange(prompt, 'CacheAwarePromptBuilder');

    return {
      prompt,
      stableTokens: this.cacheAwareness['estimateTokens'](stableContent),
      dynamicTokens: this.cacheAwareness['estimateTokens'](dynamicContent),
    };
  }
}
