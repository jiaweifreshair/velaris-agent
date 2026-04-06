/**
 * @velaris/shared - Velaris Agent 共享工具包
 */

export {
  VelarisError,
  GoalParseError,
  DecisionError,
  BudgetExceededError,
  SkillExecutionError,
  SkillNotFoundError,
  LLMError,
  StorageError,
} from './errors.js';

export { createLogger, Logger } from './logger.js';
export type { LogLevel, LogEntry, LoggerConfig } from './logger.js';

export {
  generateId,
  now,
  safeJsonParse,
  deepClone,
  sleep,
  withTimeout,
  withRetry,
  toJson,
  truncate,
} from './utils.js';
