/**
 * Valeris Agent 结构化日志
 * JSON 格式输出，支持层级标注和会话追踪
 */

/** 日志级别 */
export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

/** 日志级别优先级映射 */
const LOG_LEVEL_PRIORITY: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

/** 结构化日志条目 */
export interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  layer?: string;
  sessionId?: string;
  data?: Record<string, unknown>;
}

/** 日志器配置 */
export interface LoggerConfig {
  /** 最低日志级别，低于此级别的日志不输出 */
  level: LogLevel;
  /** 日志所属层级标识 */
  layer?: string;
  /** 自定义输出函数，默认输出到 stderr */
  output?: (entry: LogEntry) => void;
}

/** 默认输出：JSON 格式写入 stderr */
function defaultOutput(entry: LogEntry): void {
  const line = JSON.stringify(entry);
  process.stderr.write(line + '\n');
}

/**
 * 创建结构化日志器
 * 支持层级标注、会话追踪、JSON 格式输出
 */
export function createLogger(config: LoggerConfig): Logger {
  return new Logger(config);
}

export class Logger {
  private readonly minPriority: number;
  private readonly layer?: string;
  private readonly output: (entry: LogEntry) => void;

  constructor(config: LoggerConfig) {
    this.minPriority = LOG_LEVEL_PRIORITY[config.level];
    this.layer = config.layer;
    this.output = config.output ?? defaultOutput;
  }

  /** 创建带会话上下文的子日志器 */
  child(context: { sessionId?: string; layer?: string }): Logger {
    const childLogger = new Logger({
      level: this.levelFromPriority(),
      layer: context.layer ?? this.layer,
      output: this.output,
    });
    // 绑定 sessionId 到子日志器
    if (context.sessionId) {
      return new SessionLogger(childLogger, context.sessionId);
    }
    return childLogger;
  }

  debug(message: string, data?: Record<string, unknown>): void {
    this.log('debug', message, data);
  }

  info(message: string, data?: Record<string, unknown>): void {
    this.log('info', message, data);
  }

  warn(message: string, data?: Record<string, unknown>): void {
    this.log('warn', message, data);
  }

  error(message: string, data?: Record<string, unknown>): void {
    this.log('error', message, data);
  }

  protected log(
    level: LogLevel,
    message: string,
    data?: Record<string, unknown>,
    sessionId?: string,
  ): void {
    if (LOG_LEVEL_PRIORITY[level] < this.minPriority) return;

    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      ...(this.layer && { layer: this.layer }),
      ...(sessionId && { sessionId }),
      ...(data && { data }),
    };

    this.output(entry);
  }

  private levelFromPriority(): LogLevel {
    const entries = Object.entries(LOG_LEVEL_PRIORITY) as [LogLevel, number][];
    return entries.find(([_, p]) => p === this.minPriority)?.[0] ?? 'info';
  }
}

/** 带会话绑定的日志器 */
class SessionLogger extends Logger {
  private readonly sessionId: string;
  private readonly parent: Logger;

  constructor(parent: Logger, sessionId: string) {
    super({ level: 'debug', output: () => {} }); // 占位，实际委托 parent
    this.parent = parent;
    this.sessionId = sessionId;
  }

  override debug(message: string, data?: Record<string, unknown>): void {
    (this.parent as unknown as { log: Logger['log'] }).log('debug', message, data, this.sessionId);
  }

  override info(message: string, data?: Record<string, unknown>): void {
    (this.parent as unknown as { log: Logger['log'] }).log('info', message, data, this.sessionId);
  }

  override warn(message: string, data?: Record<string, unknown>): void {
    (this.parent as unknown as { log: Logger['log'] }).log('warn', message, data, this.sessionId);
  }

  override error(message: string, data?: Record<string, unknown>): void {
    (this.parent as unknown as { log: Logger['log'] }).log('error', message, data, this.sessionId);
  }
}
