/**
 * Skill 定义辅助函数
 * 提供类型安全的 Skill 创建方式
 */

import { z } from 'zod';
import type { SkillDefinition, CostEstimate, ExecutionContext } from '../types.js';

/** defineSkill 的参数类型 */
interface DefineSkillOptions<TInput, TOutput> {
  name: string;
  description: string;
  inputSchema: z.ZodType<TInput>;
  outputSchema: z.ZodType<TOutput>;
  estimatedCost?: Partial<CostEstimate>;
  execute: (input: TInput, ctx: ExecutionContext) => Promise<TOutput>;
}

/** 零成本默认值 */
const ZERO_COST: CostEstimate = {
  inputTokens: 0,
  outputTokens: 0,
  totalUsd: 0,
  model: 'none',
};

/**
 * 创建类型安全的 Skill 定义
 * 输入输出类型由 Zod Schema 自动推导
 */
export function defineSkill<TInput, TOutput>(
  options: DefineSkillOptions<TInput, TOutput>,
): SkillDefinition<TInput, TOutput> {
  return {
    name: options.name,
    description: options.description,
    inputSchema: options.inputSchema,
    outputSchema: options.outputSchema,
    estimatedCost: { ...ZERO_COST, ...options.estimatedCost },
    execute: options.execute,
  };
}
