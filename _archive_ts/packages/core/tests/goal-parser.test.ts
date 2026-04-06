/**
 * L1 Goal Parser 单元测试
 * 验证结构化解析和 Zod 校验
 */

import { describe, it, expect } from 'vitest';
import { GoalParser } from '../src/layers/goal-parser.js';
import type { LLMAdapter } from '../src/types.js';
import { createLogger } from '@velaris/shared';

const logger = createLogger({ level: 'error' });

/** Mock LLM - 返回预设的 JSON */
function makeMockLLM(response: Record<string, unknown>): LLMAdapter {
  return {
    async chat() {
      return {
        content: JSON.stringify(response),
        model: 'mock',
        usage: { inputTokens: 100, outputTokens: 50 },
        finishReason: 'stop' as const,
      };
    },
    async listModels() {
      return ['mock'];
    },
  };
}

describe('GoalParser', () => {
  describe('parseStructured', () => {
    it('应正确解析合法的结构化 Goal', () => {
      const llm = makeMockLLM({});
      const parser = new GoalParser(llm, logger);

      const goal = parser.parseStructured({
        goalType: 'token_optimize',
        userId: 'u1',
        intent: 'reduce cost',
        constraints: { targetCost: 800 },
        sessionId: 'sess_1',
      });

      expect(goal.goalType).toBe('token_optimize');
      expect(goal.userId).toBe('u1');
      expect(goal.constraints['targetCost']).toBe(800);
    });

    it('应正确解析带 budget 的 Goal', () => {
      const parser = new GoalParser(makeMockLLM({}), logger);

      const goal = parser.parseStructured({
        goalType: 'test',
        userId: 'u1',
        intent: 'test',
        constraints: {},
        sessionId: 'sess_1',
        budget: { maxTokens: 10000, maxCostUsd: 0.5 },
      });

      expect(goal.budget?.maxTokens).toBe(10000);
      expect(goal.budget?.maxCostUsd).toBe(0.5);
    });

    it('缺少必填字段时应抛出 GoalParseError', () => {
      const parser = new GoalParser(makeMockLLM({}), logger);

      expect(() =>
        parser.parseStructured({
          goalType: 'test',
          // 缺少 userId, intent, constraints, sessionId
        }),
      ).toThrow('Invalid goal structure');
    });

    it('字段类型错误时应抛出 GoalParseError', () => {
      const parser = new GoalParser(makeMockLLM({}), logger);

      expect(() =>
        parser.parseStructured({
          goalType: 123, // 应为 string
          userId: 'u1',
          intent: 'test',
          constraints: {},
          sessionId: 'sess_1',
        }),
      ).toThrow('Invalid goal structure');
    });
  });

  describe('parseNaturalLanguage', () => {
    it('应通过 LLM 解析自然语言为 Goal', async () => {
      const mockLLM = makeMockLLM({
        goalType: 'token_optimize',
        constraints: { currentCost: 2000, targetCost: 800 },
        preferences: { providers: ['openai', 'anthropic'] },
      });

      const parser = new GoalParser(mockLLM, logger);
      const goal = await parser.parseNaturalLanguage(
        '我每月 OpenAI 花费 $2000，想降到 $800',
        'u1',
        'sess_1',
        ['token_optimize', 'charter_quote'],
      );

      expect(goal.goalType).toBe('token_optimize');
      expect(goal.userId).toBe('u1');
      expect(goal.sessionId).toBe('sess_1');
      expect(goal.constraints['currentCost']).toBe(2000);
    });

    it('LLM 返回无效 JSON 时应抛出 GoalParseError', async () => {
      const brokenLLM: LLMAdapter = {
        async chat() {
          return {
            content: 'not json',
            model: 'mock',
            usage: { inputTokens: 0, outputTokens: 0 },
            finishReason: 'stop' as const,
          };
        },
        async listModels() {
          return [];
        },
      };

      const parser = new GoalParser(brokenLLM, logger);
      await expect(
        parser.parseNaturalLanguage('test', 'u1', 'sess_1', []),
      ).rejects.toThrow('Failed to parse natural language goal');
    });
  });
});
