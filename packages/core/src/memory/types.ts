/**
 * 记忆系统类型定义
 * 参考 Claude Code 的记忆六层架构
 */

import { z } from 'zod';

// ─── 记忆类型 ───────────────────────────────────────────

/** 四种核心记忆类型（参考 Claude Code memoryTypes.ts） */
export const MEMORY_TYPES = ['user', 'feedback', 'project', 'reference'] as const;
export type MemoryType = (typeof MEMORY_TYPES)[number];

/** 解析记忆类型 */
export function parseMemoryType(raw: unknown): MemoryType | undefined {
  if (typeof raw !== 'string') return undefined;
  return MEMORY_TYPES.find((t) => t === raw);
}

// ─── 记忆范围 ───────────────────────────────────────────

/** 记忆范围：私有或团队 */
export type MemoryScope = 'private' | 'team';

// ─── 记忆层级 ───────────────────────────────────────────

/**
 * 六层记忆层级
 * 公司策略 → 项目 CLAUDE.md → 用户偏好 → Auto-Memory → 会话上下文 → 子Agent记忆
 */
export const MEMORY_LAYERS = [
  'company',      // L0: 公司策略/规范
  'project',      // L1: 项目 CLAUDE.md
  'user',         // L2: 用户偏好
  'auto',         // L3: Auto-Memory（自动记忆）
  'session',      // L4: 会话上下文
  'subagent',     // L5: 子 Agent 记忆
] as const;

export type MemoryLayer = (typeof MEMORY_LAYERS)[number];

// ─── 记忆条目 ───────────────────────────────────────────

/** 记忆条目 Schema */
export const MemoryEntrySchema = z.object({
  /** 记忆 ID */
  id: z.string(),
  /** 记忆名称（用于索引显示） */
  name: z.string(),
  /** 记忆描述（一行摘要） */
  description: z.string(),
  /** 记忆类型 */
  type: z.enum(MEMORY_TYPES),
  /** 记忆范围 */
  scope: z.enum(['private', 'team'] as const).default('private'),
  /** 记忆内容 */
  content: z.string(),
  /** 所属层级 */
  layer: z.enum(MEMORY_LAYERS),
  /** 创建时间 */
  createdAt: z.number(),
  /** 更新时间 */
  updatedAt: z.number(),
  /** 关联的文件路径（可选） */
  filePath: z.string().optional(),
  /** 标签（用于检索） */
  tags: z.array(z.string()).optional(),
  /** 元数据 */
  metadata: z.record(z.unknown()).optional(),
});

export type MemoryEntry = z.infer<typeof MemoryEntrySchema>;

// ─── 记忆索引 ───────────────────────────────────────────

/** MEMORY.md 索引条目 */
export const MemoryIndexEntrySchema = z.object({
  /** 记忆文件名 */
  file: z.string(),
  /** 标题 */
  title: z.string(),
  /** 一行钩子（用于快速判断相关性） */
  hook: z.string(),
  /** 记忆类型 */
  type: z.enum(MEMORY_TYPES),
});

export type MemoryIndexEntry = z.infer<typeof MemoryIndexEntrySchema>;

// ─── 记忆配置 ───────────────────────────────────────────

/** 记忆系统配置 */
export interface MemoryConfig {
  /** 记忆目录路径 */
  memoryDir: string;
  /** MEMORY.md 索引最大行数 */
  maxIndexLines: number;
  /** MEMORY.md 最大字节数 */
  maxIndexBytes: number;
  /** 是否启用团队记忆 */
  enableTeamMemory: boolean;
  /** 团队记忆目录（如果启用） */
  teamMemoryDir?: string;
  /** Auto-Dream 配置 */
  autoDream: AutoDreamConfig;
}

/** Auto-Dream 配置 */
export interface AutoDreamConfig {
  /** 是否启用 */
  enabled: boolean;
  /** 触发间隔（小时） */
  intervalHours: number;
  /** 最小 session 数 */
  minSessionCount: number;
}

// ─── 默认配置 ───────────────────────────────────────────

export const DEFAULT_MEMORY_CONFIG: MemoryConfig = {
  memoryDir: './memory',
  maxIndexLines: 200,
  maxIndexBytes: 25_000,
  enableTeamMemory: false,
  autoDream: {
    enabled: true,
    intervalHours: 24,
    minSessionCount: 5,
  },
};

// ─── 记忆加载结果 ───────────────────────────────────────

/** 记忆加载结果 */
export interface MemoryLoadResult {
  /** 加载的记忆条目 */
  entries: MemoryEntry[];
  /** 按层级分组 */
  byLayer: Record<MemoryLayer, MemoryEntry[]>;
  /** MEMORY.md 索引内容 */
  indexContent: string;
  /** 是否被截断 */
  wasTruncated: boolean;
  /** 截断原因 */
  truncationReason?: string;
}

// ─── Auto-Dream 状态 ────────────────────────────────────

/** Auto-Dream 状态 */
export interface AutoDreamState {
  /** 上次整理时间 */
  lastOrganizedAt: number | null;
  /** 期间的 session 数 */
  sessionCount: number;
  /** 当前阶段 */
  phase: 'idle' | 'orienting' | 'collecting' | 'integrating' | 'pruning';
  /** 整理历史 */
  history: AutoDreamEvent[];
}

/** Auto-Dream 事件 */
export interface AutoDreamEvent {
  /** 时间戳 */
  timestamp: number;
  /** 阶段 */
  phase: AutoDreamState['phase'];
  /** 处理的记忆数 */
  memoriesProcessed: number;
  /** 新增的记忆数 */
  memoriesAdded: number;
  /** 删除的记忆数 */
  memoriesRemoved: number;
}

// ─── 记忆检索参数 ───────────────────────────────────────

/** 记忆检索参数 */
export interface MemorySearchParams {
  /** 关键词 */
  query?: string;
  /** 记忆类型过滤 */
  types?: MemoryType[];
  /** 层级过滤 */
  layers?: MemoryLayer[];
  /** 范围过滤 */
  scope?: MemoryScope;
  /** 标签过滤 */
  tags?: string[];
  /** 最大结果数 */
  limit?: number;
}

// ─── 记忆事件 ───────────────────────────────────────────

/** 记忆系统事件 */
export interface MemoryEvents {
  'memory:loaded': { entries: number; layers: MemoryLayer[] };
  'memory:saved': { entry: MemoryEntry };
  'memory:deleted': { id: string };
  'memory:autodream:start': { phase: AutoDreamState['phase'] };
  'memory:autodream:complete': { event: AutoDreamEvent };
}
