/**
 * Auto-Dream 记忆整理系统
 * 定向 → 收集 → 整合 → 修剪 四阶段整理
 */

import type { EventBus } from '../network/event-bus.js';
import type {
  MemoryConfig,
  MemoryEntry,
  AutoDreamState,
  AutoDreamEvent,
  MemoryType,
} from './types.js';
import { MemoryLoader } from './loader.js';
import { DEFAULT_MEMORY_CONFIG } from './types.js';

/** Auto-Dream 默认状态 */
const DEFAULT_STATE: AutoDreamState = {
  lastOrganizedAt: null,
  sessionCount: 0,
  phase: 'idle',
  history: [],
};

/**
 * Auto-Dream 记忆整理器
 * 参考 Claude Code 的 AutoDream 机制：
 * - 距上次整理 ≥ 24h 且期间 ≥ 5 个 session 时触发
 * - 分四个阶段：定向 → 收集 → 整合 → 修剪
 */
export class AutoDream {
  private readonly loader: MemoryLoader;
  private readonly config: MemoryConfig;
  private readonly eventBus?: EventBus;
  private state: AutoDreamState;
  private statePath: string;

  constructor(
    loader: MemoryLoader,
    config: Partial<MemoryConfig> = {},
    eventBus?: EventBus
  ) {
    this.loader = loader;
    this.config = { ...DEFAULT_MEMORY_CONFIG, ...config };
    this.eventBus = eventBus;
    this.state = { ...DEFAULT_STATE };
    this.statePath = `${this.config.memoryDir}/.autodream-state.json`;
  }

  /** 加载状态 */
  async loadState(): Promise<AutoDreamState> {
    try {
      const fs = await import('fs/promises');
      const content = await fs.readFile(this.statePath, 'utf-8');
      this.state = JSON.parse(content);
      return this.state;
    } catch {
      return this.state;
    }
  }

  /** 保存状态 */
  async saveState(): Promise<void> {
    try {
      const fs = await import('fs/promises');
      await fs.mkdir(this.config.memoryDir, { recursive: true });
      await fs.writeFile(this.statePath, JSON.stringify(this.state, null, 2), 'utf-8');
    } catch {
      // 忽略保存失败
    }
  }

  /** 记录 session 开始 */
  async recordSessionStart(): Promise<void> {
    await this.loadState();
    this.state.sessionCount++;
    await this.saveState();
  }

  /** 检查是否应该触发整理 */
  async shouldTrigger(): Promise<boolean> {
    if (!this.config.autoDream.enabled) {
      return false;
    }

    await this.loadState();

    // 从未整理过
    if (this.state.lastOrganizedAt === null) {
      return this.state.sessionCount >= this.config.autoDream.minSessionCount;
    }

    // 检查时间间隔
    const hoursSinceLast =
      (Date.now() - this.state.lastOrganizedAt) / (1000 * 60 * 60);

    return (
      hoursSinceLast >= this.config.autoDream.intervalHours &&
      this.state.sessionCount >= this.config.autoDream.minSessionCount
    );
  }

  /** 执行整理（如果满足条件） */
  async runIfNeeded(): Promise<AutoDreamEvent | null> {
    if (!(await this.shouldTrigger())) {
      return null;
    }
    return this.run();
  }

  /** 强制执行整理 */
  async run(): Promise<AutoDreamEvent> {
    await this.loadState();

    // 阶段 1: 定向（Orienting）
    this.state.phase = 'orienting';
    this.eventBus?.emit('memory:autodream:start', { sessionId: '', trigger: 'autodream', phase: 'orienting' });
    const memoriesToProcess = await this.orient();

    // 阶段 2: 收集（Collecting）
    this.state.phase = 'collecting';
    this.eventBus?.emit('memory:autodream:start', { sessionId: '', trigger: 'autodream', phase: 'collecting' });
    const collected = await this.collect(memoriesToProcess);

    // 阶段 3: 整合（Integrating）
    this.state.phase = 'integrating';
    this.eventBus?.emit('memory:autodream:start', { sessionId: '', trigger: 'autodream', phase: 'integrating' });
    const { added, merged } = await this.integrate(collected);

    // 阶段 4: 修剪（Pruning）
    this.state.phase = 'pruning';
    this.eventBus?.emit('memory:autodream:start', { sessionId: '', trigger: 'autodream', phase: 'pruning' });
    const removed = await this.prune();

    // 完成整理
    const event: AutoDreamEvent = {
      timestamp: Date.now(),
      phase: 'idle',
      memoriesProcessed: memoriesToProcess.length,
      memoriesAdded: added + merged,
      memoriesRemoved: removed,
    };

    this.state.phase = 'idle';
    this.state.lastOrganizedAt = Date.now();
    this.state.sessionCount = 0;
    this.state.history.push(event);

    // 保留最近 100 次历史
    if (this.state.history.length > 100) {
      this.state.history = this.state.history.slice(-100);
    }

    await this.saveState();

    this.eventBus?.emit('memory:autodream:complete', {
      sessionId: '',
      entriesProcessed: event.memoriesProcessed,
      entriesRemoved: event.memoriesRemoved,
      event: JSON.stringify(event),
    });

    return event;
  }

  /** 阶段 1: 定向 - 确定需要整理的记忆范围 */
  private async orient(): Promise<MemoryEntry[]> {
    const { entries } = await this.loader.loadAll();

    // 选择需要整理的记忆：
    // - 超过 7 天未更新的 user 类型
    // - 所有 feedback 类型
    // - 超过 30 天未更新的 project 类型
    const now = Date.now();
    const sevenDays = 7 * 24 * 60 * 60 * 1000;
    const thirtyDays = 30 * 24 * 60 * 60 * 1000;

    return entries.filter((e) => {
      if (e.type === 'user' && now - e.updatedAt > sevenDays) {
        return true;
      }
      if (e.type === 'feedback') {
        return true;
      }
      if (e.type === 'project' && now - e.updatedAt > thirtyDays) {
        return true;
      }
      return false;
    });
  }

  /** 阶段 2: 收集 - 收集相关记忆 */
  private async collect(entries: MemoryEntry[]): Promise<Map<MemoryType, MemoryEntry[]>> {
    const grouped = new Map<MemoryType, MemoryEntry[]>();

    for (const entry of entries) {
      const existing = grouped.get(entry.type) ?? [];
      existing.push(entry);
      grouped.set(entry.type, existing);
    }

    return grouped;
  }

  /** 阶段 3: 整合 - 合并相似记忆 */
  private async integrate(
    grouped: Map<MemoryType, MemoryEntry[]>
  ): Promise<{ added: number; merged: number }> {
    let added = 0;
    let merged = 0;

    for (const [type, entries] of grouped) {
      if (entries.length < 2) continue;

      // 检测相似记忆（简单关键词重叠）
      const similarPairs: [MemoryEntry, MemoryEntry][] = [];
      for (let i = 0; i < entries.length; i++) {
        for (let j = i + 1; j < entries.length; j++) {
          if (this.areSimilar(entries[i]!, entries[j]!)) {
            similarPairs.push([entries[i]!, entries[j]!]);
          }
        }
      }

      // 合并相似记忆
      for (const [a, b] of similarPairs) {
        const mergedEntry: MemoryEntry = {
          id: `${a.id}_${b.id}`,
          name: `Merged: ${a.name}`,
          description: a.description || b.description,
          type,
          scope: a.scope,
          content: `${a.content}\n\n---\n\n${b.content}`,
          layer: a.layer,
          createdAt: Math.min(a.createdAt, b.createdAt),
          updatedAt: Date.now(),
          tags: [...new Set([...(a.tags ?? []), ...(b.tags ?? [])])],
        };

        await this.loader.save(mergedEntry);
        await this.loader.delete(a.id, a.filePath);
        await this.loader.delete(b.id, b.filePath);

        merged++;
      }

      // 为未合并的记忆添加标签
      for (const entry of entries) {
        if (!entry.tags?.includes('autodream-processed')) {
          entry.tags = [...(entry.tags ?? []), 'autodream-processed'];
          entry.updatedAt = Date.now();
          await this.loader.save(entry);
          added++;
        }
      }
    }

    return { added, merged };
  }

  /** 阶段 4: 修剪 - 删除过时或冗余记忆 */
  private async prune(): Promise<number> {
    const { entries } = await this.loader.loadAll();
    let removed = 0;

    const now = Date.now();
    const ninetyDays = 90 * 24 * 60 * 60 * 1000;

    for (const entry of entries) {
      // 删除超过 90 天未更新且标记为过时的记忆
      if (entry.tags?.includes('outdated') && now - entry.updatedAt > ninetyDays) {
        await this.loader.delete(entry.id, entry.filePath);
        removed++;
        continue;
      }

      // 删除空的记忆
      if (!entry.content.trim()) {
        await this.loader.delete(entry.id, entry.filePath);
        removed++;
      }
    }

    return removed;
  }

  /** 检测两个记忆是否相似 */
  private areSimilar(a: MemoryEntry, b: MemoryEntry): boolean {
    // 简单的关键词重叠检测
    const wordsA = new Set(
      a.content.toLowerCase().split(/\s+/).filter((w) => w.length > 3)
    );
    const wordsB = new Set(
      b.content.toLowerCase().split(/\s+/).filter((w) => w.length > 3)
    );

    // Jaccard 相似度
    const intersection = new Set([...wordsA].filter((x) => wordsB.has(x)));
    const union = new Set([...wordsA, ...wordsB]);

    if (union.size === 0) return false;

    const similarity = intersection.size / union.size;
    return similarity > 0.5; // 50% 相似度阈值
  }

  /** 获取当前状态 */
  getState(): AutoDreamState {
    return { ...this.state };
  }

  /** 重置状态 */
  async reset(): Promise<void> {
    this.state = { ...DEFAULT_STATE };
    await this.saveState();
  }
}
