/**
 * 内置 Skill: call-llm
 * 通用 LLM 调用，带模型路由和成本追踪
 */

import { z } from 'zod';
import { defineSkill } from '../skill.js';

/** call-llm 输入 Schema */
const CallLLMInput = z.object({
  /** 系统提示词 */
  systemPrompt: z.string().optional(),
  /** 用户消息 */
  userMessage: z.string(),
  /** 指定模型（不指定则由框架路由） */
  model: z.string().optional(),
  /** 温度参数 */
  temperature: z.number().min(0).max(2).optional(),
  /** 最大输出 token */
  maxTokens: z.number().optional(),
  /** 是否要求 JSON 输出 */
  jsonMode: z.boolean().optional(),
});

/** call-llm 输出 Schema */
const CallLLMOutput = z.object({
  /** LLM 生成的内容 */
  content: z.string(),
  /** 使用的模型 */
  model: z.string(),
  /** token 用量 */
  usage: z.object({
    inputTokens: z.number(),
    outputTokens: z.number(),
  }),
});

export const callLlmSkill = defineSkill({
  name: 'call-llm',
  description: '通用 LLM 调用，支持模型路由和成本追踪',
  inputSchema: CallLLMInput,
  outputSchema: CallLLMOutput,
  estimatedCost: { inputTokens: 1000, outputTokens: 500, totalUsd: 0.005, model: 'auto' },

  async execute(input, ctx) {
    const messages = [
      ...(input.systemPrompt ? [{ role: 'system' as const, content: input.systemPrompt }] : []),
      { role: 'user' as const, content: input.userMessage },
    ];

    const response = await ctx.llm.chat({
      model: input.model ?? 'gpt-4o-mini',
      messages,
      temperature: input.temperature ?? 0.7,
      maxTokens: input.maxTokens,
      responseFormat: input.jsonMode ? { type: 'json_object' } : undefined,
    });

    // 追踪成本
    const costPerInputToken = 0.00000015; // gpt-4o-mini 估算
    const costPerOutputToken = 0.0000006;
    const costUsd =
      response.usage.inputTokens * costPerInputToken +
      response.usage.outputTokens * costPerOutputToken;

    ctx.costTracker.track({
      layer: 'executor',
      eventType: 'llm_call',
      tokensUsed: response.usage.inputTokens + response.usage.outputTokens,
      costUsd,
      metadata: { model: response.model, skill: 'call-llm' },
    });

    return {
      content: response.content,
      model: response.model,
      usage: response.usage,
    };
  },
});
