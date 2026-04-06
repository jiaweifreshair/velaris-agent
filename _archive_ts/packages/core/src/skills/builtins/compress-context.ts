/**
 * 内置 Skill: compress-context
 * 上下文压缩，在 token 预算紧张时使用
 */

import { z } from 'zod';
import { defineSkill } from '../skill.js';
import { ContextCompressor } from '../../cost/compressor.js';

/** compress-context 输入 */
const CompressContextInput = z.object({
  /** 要压缩的文本内容 */
  text: z.string(),
  /** 目标最大 token 数 */
  maxTokens: z.number(),
  /** 压缩策略 */
  strategy: z.enum(['truncate', 'summarize']).default('truncate'),
});

/** compress-context 输出 */
const CompressContextOutput = z.object({
  /** 压缩后的文本 */
  compressed: z.string(),
  /** 原始 token 数估算 */
  originalTokens: z.number(),
  /** 压缩后 token 数估算 */
  compressedTokens: z.number(),
  /** 压缩比 */
  ratio: z.number(),
});

export const compressContextSkill = defineSkill({
  name: 'compress-context',
  description: '上下文压缩，在 token 预算紧张时使用',
  inputSchema: CompressContextInput,
  outputSchema: CompressContextOutput,

  async execute(input, ctx) {
    const originalTokens = ContextCompressor.estimateTokens(input.text);

    if (originalTokens <= input.maxTokens) {
      return {
        compressed: input.text,
        originalTokens,
        compressedTokens: originalTokens,
        ratio: 1.0,
      };
    }

    if (input.strategy === 'summarize') {
      // 用 LLM 摘要
      const response = await ctx.llm.chat({
        model: 'gpt-4o-mini',
        messages: [
          {
            role: 'system',
            content: `Compress the following text to fit within approximately ${input.maxTokens} tokens. Preserve key information, decisions, and data points. Output only the compressed text.`,
          },
          { role: 'user', content: input.text },
        ],
        maxTokens: Math.floor(input.maxTokens * 0.8),
      });

      const compressedTokens = ContextCompressor.estimateTokens(response.content);

      // 追踪压缩消耗的成本
      ctx.costTracker.track({
        layer: 'executor',
        eventType: 'compress',
        tokensUsed: response.usage.inputTokens + response.usage.outputTokens,
        costUsd: response.usage.inputTokens * 0.00000015 + response.usage.outputTokens * 0.0000006,
        metadata: { skill: 'compress-context', strategy: 'summarize' },
      });

      return {
        compressed: response.content,
        originalTokens,
        compressedTokens,
        ratio: compressedTokens / originalTokens,
      };
    }

    // 截断策略
    const charLimit = input.maxTokens * 4; // 粗略估算
    const compressed = input.text.substring(0, charLimit);
    const compressedTokens = ContextCompressor.estimateTokens(compressed);

    return {
      compressed,
      originalTokens,
      compressedTokens,
      ratio: compressedTokens / originalTokens,
    };
  },
});
