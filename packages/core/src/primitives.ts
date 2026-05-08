/**
 * 工具原语系统
 * 参考 Claude Code 的"笨框架"哲学：只提供 4 种能力原语
 * 模型可以通过这些原语组合出任意复杂的功能
 */

import { z } from 'zod';
import type { SkillDefinition } from './types.js';

// ─── 原语定义 ─────────────────────────────────────────

/** 四种工具原语 */
export type PrimitiveType = 'read' | 'write' | 'execute' | 'connect';

/** 原语能力接口 */
export interface PrimitiveCapability {
  type: PrimitiveType;
  name: string;
  description: string;
  maxTokens: number; // 预估 token 上限
}

// 原语能力注册表
export const PRIMITIVES: PrimitiveCapability[] = [
  {
    type: 'read',
    name: 'Read',
    description: '读取文件、搜索内容、浏览目录、获取系统信息',
    maxTokens: 50000,
  },
  {
    type: 'write',
    name: 'Write',
    description: '创建文件、编辑内容、修改代码、生成文档',
    maxTokens: 100000,
  },
  {
    type: 'execute',
    name: 'Bash',
    description: '执行命令、运行脚本、操作 git、安装依赖',
    maxTokens: 30000,
  },
  {
    type: 'connect',
    name: 'Connect',
    description: '调用 API、访问网络资源、连接 MCP 服务',
    maxTokens: 20000,
  },
];

// ─── 原语 Skill 工厂 ───────────────────────────────────

/**
 * 创建原语化 Skill
 * 将复杂的工具简化为 4 种原语的组合
 */

// Read 原语 - 封装所有读取能力
export const readPrimitive = definePrimitiveSkill({
  type: 'read',
  name: 'read',
  description: '读取文件、搜索代码、浏览目录',
  subActions: ['file_read', 'grep', 'glob', 'ls', 'status', 'git_status'],
});

// Write 原语 - 封装所有写入能力
export const writePrimitive = definePrimitiveSkill({
  type: 'write',
  name: 'write',
  description: '创建/编辑文件、执行代码修改',
  subActions: ['file_write', 'file_edit', 'create', 'replace'],
});

// Execute 原语 - 封装所有执行能力
export const executePrimitive = definePrimitiveSkill({
  type: 'execute',
  name: 'execute',
  description: '执行命令、运行脚本、git 操作',
  subActions: ['bash', 'npm', 'git', 'docker', 'python', 'node'],
});

// Connect 原语 - 封装所有连接能力
export const connectPrimitive = definePrimitiveSkill({
  type: 'connect',
  name: 'connect',
  description: 'API 调用、网络请求、MCP 服务',
  subActions: ['http_request', 'mcp_call', 'web_fetch', 'api_call'],
});

// ─── 内部实现 ─────────────────────────────────────────

interface PrimitiveOptions {
  type: PrimitiveType;
  name: string;
  description: string;
  subActions: string[];
}

function definePrimitiveSkill(options: PrimitiveOptions): SkillDefinition<{ action: string; payload: Record<string, unknown> }, { success: boolean; output: unknown; tokensUsed: number }> {
  return {
    name: `primitive_${options.type}`,
    description: `${options.name} 原语: ${options.description}. 可用操作: ${options.subActions.join(', ')}`,
    inputSchema: z.object({
      action: z.enum(options.subActions as [string, ...string[]]).describe('执行的动作'),
      payload: z.record(z.unknown()).describe('动作参数'),
    }),
    outputSchema: z.object({
      success: z.boolean(),
      output: z.unknown(),
      tokensUsed: z.number(),
    }) as z.ZodType<{ success: boolean; output: unknown; tokensUsed: number }>,
    estimatedCost: {
      inputTokens: 100,
      outputTokens: 500,
      totalUsd: 0.0001,
      model: 'builtin',
    },
    execute: async (input) => {
      // 原语执行 — 框架越笨越稳定，具体能力由宿主环境提供
      // Claude Code 哲学：只给 4 种原语，模型自己组合
      
      return {
        success: true,
        output: { type: options.type, action: input.action, payload: input.payload },
        tokensUsed: 0,
      };
    },
  };
}

// 导出所有原语
export const primitives = [readPrimitive, writePrimitive, executePrimitive, connectPrimitive];
