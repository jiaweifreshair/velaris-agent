/**
 * 内置 Skill: fetch-data
 * 通用数据获取，支持 HTTP 请求和 JSON 解析
 */

import { z } from 'zod';
import { defineSkill } from '../skill.js';

/** fetch-data 输入 */
const FetchDataInput = z.object({
  /** 请求 URL */
  url: z.string().url(),
  /** HTTP 方法 */
  method: z.enum(['GET', 'POST']).default('GET'),
  /** 请求头 */
  headers: z.record(z.string()).optional(),
  /** 请求体（POST 时使用） */
  body: z.unknown().optional(),
  /** 超时毫秒数 */
  timeoutMs: z.number().default(10000),
});

/** fetch-data 输出 */
const FetchDataOutput = z.object({
  /** HTTP 状态码 */
  status: z.number(),
  /** 响应数据 */
  data: z.unknown(),
  /** 是否成功 (2xx) */
  ok: z.boolean(),
  /** 响应耗时毫秒 */
  latencyMs: z.number(),
});

export const fetchDataSkill = defineSkill({
  name: 'fetch-data',
  description: '通用 HTTP 数据获取',
  inputSchema: FetchDataInput,
  outputSchema: FetchDataOutput,

  async execute(input, _ctx) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), input.timeoutMs);
    const start = Date.now();

    try {
      const response = await fetch(input.url, {
        method: input.method,
        headers: input.headers,
        body: input.body ? JSON.stringify(input.body) : undefined,
        signal: controller.signal,
      });

      const latencyMs = Date.now() - start;
      let data: unknown;

      const contentType = response.headers.get('content-type') ?? '';
      if (contentType.includes('application/json')) {
        data = await response.json();
      } else {
        data = await response.text();
      }

      return {
        status: response.status,
        data,
        ok: response.ok,
        latencyMs,
      };
    } finally {
      clearTimeout(timeout);
    }
  },
});
