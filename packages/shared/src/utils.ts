/**
 * Valeris Agent 通用工具函数
 */

/** 生成带前缀的唯一 ID */
export function generateId(prefix: string = 'v'): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).substring(2, 8);
  return `${prefix}_${timestamp}_${random}`;
}

/** 获取当前 Unix 时间戳（毫秒） */
export function now(): number {
  return Date.now();
}

/** 安全的 JSON 解析，失败返回 null */
export function safeJsonParse<T = unknown>(text: string): T | null {
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

/** 深拷贝（结构化克隆） */
export function deepClone<T>(value: T): T {
  return structuredClone(value);
}

/** 延迟指定毫秒 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 带超时的 Promise 包装 */
export function withTimeout<T>(promise: Promise<T>, ms: number, message?: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(message ?? `Operation timed out after ${ms}ms`));
    }, ms);

    promise
      .then((value) => {
        clearTimeout(timer);
        resolve(value);
      })
      .catch((err: unknown) => {
        clearTimeout(timer);
        reject(err);
      });
  });
}

/** 带重试的异步函数执行 */
export async function withRetry<T>(
  fn: () => Promise<T>,
  options: { maxRetries?: number; delayMs?: number; backoff?: number } = {},
): Promise<T> {
  const { maxRetries = 3, delayMs = 1000, backoff = 2 } = options;
  let lastError: unknown;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err;
      if (attempt < maxRetries) {
        await sleep(delayMs * Math.pow(backoff, attempt));
      }
    }
  }

  throw lastError;
}

/** 将对象转为 JSON 字符串（处理循环引用） */
export function toJson(value: unknown): string {
  const seen = new WeakSet();
  return JSON.stringify(value, (_key, val: unknown) => {
    if (typeof val === 'object' && val !== null) {
      if (seen.has(val)) return '[Circular]';
      seen.add(val);
    }
    return val;
  });
}

/** 截断字符串到指定长度 */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.substring(0, maxLength - 3) + '...';
}
