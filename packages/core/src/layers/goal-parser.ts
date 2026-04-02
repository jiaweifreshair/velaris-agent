/**
 * L1 Goal Parser - 目标解析层
 * 将自然语言意图解析为结构化 GoalSchema
 */

import type { Goal, LLMAdapter } from '../types.js';
import { GoalSchema } from '../types.js';
import { GoalParseError } from '@valeris/shared';
import type { Logger } from '@valeris/shared';

/** 意图分类结果 */
export interface IntentClassification {
  /** 目标类型 */
  goalType: string;
  /** 置信度 0-1 */
  confidence: number;
}

/**
 * 目标解析器
 * 支持两种模式：
 * 1. 直接传入结构化 Goal（跳过 LLM 解析）
 * 2. 传入自然语言，由 LLM 解析为 Goal
 */
export class GoalParser {
  constructor(
    private readonly llm: LLMAdapter,
    private readonly logger: Logger,
  ) {}

  /** 从结构化输入解析 Goal（Zod 校验） */
  parseStructured(input: unknown): Goal {
    const result = GoalSchema.safeParse(input);
    if (!result.success) {
      throw new GoalParseError(
        `Invalid goal structure: ${result.error.issues.map((i) => i.message).join(', ')}`,
      );
    }
    this.logger.info('Goal parsed from structured input', { goalType: result.data.goalType });
    return result.data;
  }

  /** 从自然语言解析 Goal */
  async parseNaturalLanguage(
    intent: string,
    userId: string,
    sessionId: string,
    knownGoalTypes: string[],
  ): Promise<Goal> {
    this.logger.info('Parsing goal from natural language', { intent: intent.substring(0, 100) });

    const systemPrompt = `You are a goal parser. Extract a structured goal from the user's intent.
Available goal types: ${knownGoalTypes.join(', ')}

Output a JSON object with these fields:
- goalType: one of the available goal types
- intent: the original user intent
- constraints: key constraints extracted from the intent (as key-value pairs)
- preferences: optional user preferences (as key-value pairs)

Output only valid JSON, no explanation.`;

    try {
      const response = await this.llm.chat({
        model: 'gpt-4o-mini',
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: intent },
        ],
        temperature: 0.1,
        responseFormat: { type: 'json_object' },
      });

      const parsed = JSON.parse(response.content) as Record<string, unknown>;

      const goal: Goal = {
        goalType: String(parsed['goalType'] ?? 'unknown'),
        userId,
        intent,
        constraints: (parsed['constraints'] ?? {}) as Record<string, unknown>,
        preferences: parsed['preferences'] as Record<string, unknown> | undefined,
        sessionId,
      };

      // Zod 校验
      const validated = GoalSchema.parse(goal);
      this.logger.info('Goal parsed from NL', { goalType: validated.goalType });
      return validated;
    } catch (err) {
      if (err instanceof GoalParseError) throw err;
      throw new GoalParseError(
        `Failed to parse natural language goal: ${err instanceof Error ? err.message : String(err)}`,
        { cause: err },
      );
    }
  }
}
