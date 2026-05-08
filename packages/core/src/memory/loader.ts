/**
 * 记忆六层加载器
 * 公司策略 → 项目 CLAUDE.md → 用户偏好 → Auto-Memory → 会话上下文 → 子Agent记忆
 */

import type { EventBus } from '../network/event-bus.js';
import type {
  MemoryConfig,
  MemoryEntry,
  MemoryLoadResult,
  MemoryLayer,
  MemorySearchParams,
} from './types.js';
import { MemoryStorage } from './storage.js';
import { DEFAULT_MEMORY_CONFIG, MEMORY_LAYERS } from './types.js';

/** 层级优先级（数字越小优先级越高） */
const LAYER_PRIORITY: Record<MemoryLayer, number> = {
  company: 0,
  project: 1,
  user: 2,
  auto: 3,
  session: 4,
  subagent: 5,
};

/** 层级加载器接口 */
interface LayerLoader {
  layer: MemoryLayer;
  load(): Promise<MemoryEntry[]>;
  isAvailable(): boolean;
}

/**
 * 记忆六层加载器
 * 按优先级顺序加载各层记忆，支持增量加载和缓存
 */
export class MemoryLoader {
  private readonly storage: MemoryStorage;
  private readonly config: MemoryConfig;
  private readonly eventBus?: EventBus;
  private readonly layerLoaders: Map<MemoryLayer, LayerLoader> = new Map();
  private cache: MemoryLoadResult | null = null;
  private cacheTime = 0;
  private readonly cacheTtlMs = 60_000; // 缓存 1 分钟

  constructor(config: Partial<MemoryConfig> = {}, eventBus?: EventBus) {
    this.config = { ...DEFAULT_MEMORY_CONFIG, ...config };
    this.storage = new MemoryStorage(this.config);
    this.eventBus = eventBus;

    // 注册默认层级加载器
    this.registerDefaultLoaders();
  }

  /** 注册默认层级加载器 */
  private registerDefaultLoaders(): void {
    // 公司策略层
    this.registerLoader({
      layer: 'company',
      isAvailable: () => false, // 默认不可用，需要外部配置
      load: async () => [],
    });

    // 项目层（CLAUDE.md）
    this.registerLoader({
      layer: 'project',
      isAvailable: () => false, // 由外部 CLAUDE.md 处理
      load: async () => [],
    });

    // 用户偏好层
    this.registerLoader({
      layer: 'user',
      isAvailable: () => true,
      load: async () => {
        const entries = await this.storage.loadAll();
        return entries.entries.filter((e) => e.type === 'user');
      },
    });

    // Auto-Memory 层
    this.registerLoader({
      layer: 'auto',
      isAvailable: () => true,
      load: async () => {
        const entries = await this.storage.loadAll();
        return entries.entries.filter((e) => e.layer === 'auto');
      },
    });

    // 会话上下文层
    this.registerLoader({
      layer: 'session',
      isAvailable: () => true,
      load: async () => [], // 会话记忆由外部管理
    });

    // 子 Agent 层
    this.registerLoader({
      layer: 'subagent',
      isAvailable: () => true,
      load: async () => [], // 子 Agent 记忆由外部管理
    });
  }

  /** 注册层级加载器 */
  registerLoader(loader: LayerLoader): void {
    this.layerLoaders.set(loader.layer, loader);
  }

  /** 加载所有层级的记忆 */
  async loadAll(forceRefresh = false): Promise<MemoryLoadResult> {
    // 检查缓存
    if (!forceRefresh && this.cache && Date.now() - this.cacheTime < this.cacheTtlMs) {
      return this.cache;
    }

    const entries: MemoryEntry[] = [];
    const byLayer: Record<MemoryLayer, MemoryEntry[]> = {
      company: [],
      project: [],
      user: [],
      auto: [],
      session: [],
      subagent: [],
    };

    // 按优先级顺序加载
    const sortedLayers = [...MEMORY_LAYERS].sort(
      (a, b) => LAYER_PRIORITY[a] - LAYER_PRIORITY[b]
    );

    for (const layer of sortedLayers) {
      const loader = this.layerLoaders.get(layer);
      if (loader?.isAvailable()) {
        const layerEntries = await loader.load();
        entries.push(...layerEntries);
        byLayer[layer] = layerEntries;
      }
    }

    // 获取索引内容
    const indexContent = await this.storage.readIndex();

    // 构建结果
    const result: MemoryLoadResult = {
      entries,
      byLayer,
      indexContent,
      wasTruncated: false,
    };

    // 更新缓存
    this.cache = result;
    this.cacheTime = Date.now();

    // 发射事件
    this.eventBus?.emit('memory:loaded', {
      sessionId: '',
      entryCount: entries.length,
      entries,
    });

    return result;
  }

  /** 加载指定层级 */
  async loadLayer(layer: MemoryLayer): Promise<MemoryEntry[]> {
    const loader = this.layerLoaders.get(layer);
    if (!loader?.isAvailable()) {
      return [];
    }
    return loader.load();
  }

  /** 搜索记忆 */
  async search(params: MemorySearchParams): Promise<MemoryEntry[]> {
    const { entries } = await this.loadAll();
    let results = [...entries];

    // 类型过滤
    if (params.types?.length) {
      results = results.filter((e) => params.types!.includes(e.type));
    }

    // 层级过滤
    if (params.layers?.length) {
      results = results.filter((e) => params.layers!.includes(e.layer));
    }

    // 范围过滤
    if (params.scope) {
      results = results.filter((e) => e.scope === params.scope);
    }

    // 标签过滤
    if (params.tags?.length) {
      results = results.filter((e) =>
        e.tags?.some((t) => params.tags!.includes(t))
      );
    }

    // 关键词搜索
    if (params.query) {
      const query = params.query.toLowerCase();
      results = results.filter((e) => {
        const text = `${e.name} ${e.description} ${e.content}`.toLowerCase();
        return text.includes(query);
      });
    }

    // 限制结果数
    if (params.limit) {
      results = results.slice(0, params.limit);
    }

    return results;
  }

  /** 保存记忆 */
  async save(entry: MemoryEntry): Promise<void> {
    await this.storage.writeMemoryFile(entry);

    // 清除缓存
    this.cache = null;

    // 发射事件
    this.eventBus?.emit('memory:saved', { sessionId: '', entry });
  }

  /** 删除记忆 */
  async delete(id: string, filePath?: string): Promise<void> {
    if (filePath) {
      await this.storage.deleteMemoryFile(filePath);
    }

    // 清除缓存
    this.cache = null;

    // 发射事件
    this.eventBus?.emit('memory:deleted', { sessionId: '', id });
  }

  /** 获取存储实例 */
  getStorage(): MemoryStorage {
    return this.storage;
  }

  /** 清除缓存 */
  clearCache(): void {
    this.cache = null;
    this.cacheTime = 0;
  }

  /** 获取记忆统计 */
  async getStats(): Promise<{
    totalCount: number;
    byLayer: Record<MemoryLayer, number>;
    byType: Record<string, number>;
  }> {
    const { entries, byLayer } = await this.loadAll();

    const byType: Record<string, number> = {};
    for (const entry of entries) {
      byType[entry.type] = (byType[entry.type] ?? 0) + 1;
    }

    return {
      totalCount: entries.length,
      byLayer: {
        company: byLayer.company.length,
        project: byLayer.project.length,
        user: byLayer.user.length,
        auto: byLayer.auto.length,
        session: byLayer.session.length,
        subagent: byLayer.subagent.length,
      },
      byType,
    };
  }
}
