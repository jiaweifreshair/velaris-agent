/**
 * 记忆系统统一导出
 */

// 类型
export {
  MEMORY_TYPES,
  MEMORY_LAYERS,
  DEFAULT_MEMORY_CONFIG,
  parseMemoryType,
} from './types.js';

export type {
  MemoryType,
  MemoryScope,
  MemoryLayer,
  MemoryEntry,
  MemoryIndexEntry,
  MemoryConfig,
  AutoDreamConfig,
  MemoryLoadResult,
  AutoDreamState,
  AutoDreamEvent,
  MemorySearchParams,
  MemoryEvents,
} from './types.js';

export { MemoryEntrySchema, MemoryIndexEntrySchema } from './types.js';

// 存储
export { MemoryStorage, ENTRYPOINT_NAME } from './storage.js';

// 加载器
export { MemoryLoader } from './loader.js';

// Auto-Dream
export { AutoDream } from './auto-dream.js';
