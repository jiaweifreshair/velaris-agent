/**
 * L3 Decision Core 单元测试
 * 验证多维打分、约束过滤、模型路由
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { DecisionCore } from '../src/layers/decision-core.js';
import type { Candidate } from '../src/layers/decision-core.js';
import type { Goal } from '../src/types.js';
import { createLogger } from '@velaris/shared';

const logger = createLogger({ level: 'error' });

/** 测试用 Goal */
function makeGoal(overrides: Partial<Goal> = {}): Goal {
  return {
    goalType: 'test',
    userId: 'u1',
    intent: 'test intent',
    constraints: {},
    sessionId: 'sess_test',
    ...overrides,
  };
}

describe('DecisionCore', () => {
  let core: DecisionCore;

  beforeEach(() => {
    core = new DecisionCore({ quality: 0.5, cost: 0.3, speed: 0.2 }, logger);
  });

  describe('多维加权打分', () => {
    it('应根据权重正确计算综合得分', () => {
      const candidates: Candidate[] = [
        {
          actionType: 'plan_a',
          params: {},
          rawScores: { quality: 0.9, cost: 0.3, speed: 0.5 },
        },
        {
          actionType: 'plan_b',
          params: {},
          rawScores: { quality: 0.5, cost: 0.9, speed: 0.8 },
        },
      ];

      const result = core.decide(candidates, makeGoal());

      // plan_a: 0.9*0.5 + 0.3*0.3 + 0.5*0.2 = 0.45+0.09+0.10 = 0.64
      // plan_b: 0.5*0.5 + 0.9*0.3 + 0.8*0.2 = 0.25+0.27+0.16 = 0.68
      expect(result.selectedAction.actionType).toBe('plan_b');
      expect(result.selectedAction.score).toBeCloseTo(0.68, 2);
      expect(result.alternatives).toHaveLength(1);
      expect(result.alternatives[0]!.actionType).toBe('plan_a');
    });

    it('应将分数限制在 0-1 范围内', () => {
      const candidates: Candidate[] = [
        {
          actionType: 'overflow',
          params: {},
          rawScores: { quality: 1.5, cost: -0.2, speed: 0.5 },
        },
      ];

      const result = core.decide(candidates, makeGoal());
      // quality 被 clamp 到 1.0, cost 被 clamp 到 0
      // 1.0*0.5 + 0*0.3 + 0.5*0.2 = 0.6
      expect(result.selectedAction.score).toBeCloseTo(0.6, 2);
    });

    it('当所有权重为 0 时，得分应为 0', () => {
      const zeroCore = new DecisionCore({ quality: 0, cost: 0, speed: 0 }, logger);
      const candidates: Candidate[] = [
        { actionType: 'a', params: {}, rawScores: { quality: 1, cost: 1, speed: 1 } },
      ];
      const result = zeroCore.decide(candidates, makeGoal());
      expect(result.selectedAction.score).toBe(0);
    });
  });

  describe('约束过滤', () => {
    it('应过滤不满足约束的候选方案', () => {
      core.addFilter({
        name: 'budget_filter',
        filter: (c) => (c.params['price'] as number) <= 100,
      });

      const candidates: Candidate[] = [
        { actionType: 'cheap', params: { price: 50 }, rawScores: { quality: 0.6, cost: 0.9, speed: 0.7 } },
        { actionType: 'expensive', params: { price: 200 }, rawScores: { quality: 0.9, cost: 0.1, speed: 0.5 } },
      ];

      const result = core.decide(candidates, makeGoal());
      expect(result.selectedAction.actionType).toBe('cheap');
      expect(result.alternatives).toHaveLength(0);
    });

    it('所有候选被过滤时应抛出 DecisionError', () => {
      core.addFilter({
        name: 'reject_all',
        filter: () => false,
      });

      const candidates: Candidate[] = [
        { actionType: 'a', params: {}, rawScores: { quality: 1, cost: 1, speed: 1 } },
      ];

      expect(() => core.decide(candidates, makeGoal())).toThrow('All candidates were filtered out');
    });
  });

  describe('自定义打分器', () => {
    it('应应用自定义打分器覆盖原始分数', () => {
      core.addScorer({
        dimension: 'quality',
        score: (_candidate, _goal) => 1.0, // 强制所有候选 quality=1
      });

      const candidates: Candidate[] = [
        { actionType: 'a', params: {}, rawScores: { quality: 0.1, cost: 0.5, speed: 0.5 } },
        { actionType: 'b', params: {}, rawScores: { quality: 0.1, cost: 0.5, speed: 0.5 } },
      ];

      const result = core.decide(candidates, makeGoal());
      // quality 被覆盖为 1.0: 1.0*0.5 + 0.5*0.3 + 0.5*0.2 = 0.75
      expect(result.selectedAction.score).toBeCloseTo(0.75, 2);
    });
  });

  describe('模型路由', () => {
    it('无预算限制时应选择高端模型', () => {
      const candidates: Candidate[] = [
        { actionType: 'a', params: {}, rawScores: { quality: 0.8, cost: 0.8, speed: 0.8 } },
      ];
      const result = core.decide(candidates, makeGoal());
      expect(result.modelRouting.tier).toBe('high');
    });

    it('低预算时应选择经济模型', () => {
      const candidates: Candidate[] = [
        { actionType: 'a', params: {}, rawScores: { quality: 0.8, cost: 0.8, speed: 0.8 } },
      ];
      const goal = makeGoal({ budget: { maxCostUsd: 0.05 } });
      const result = core.decide(candidates, goal);
      expect(result.modelRouting.tier).toBe('low');
    });
  });

  describe('空输入', () => {
    it('无候选方案时应抛出 DecisionError', () => {
      expect(() => core.decide([], makeGoal())).toThrow('No candidates provided');
    });
  });

  describe('决策推理', () => {
    it('应生成包含得分信息的推理文本', () => {
      const candidates: Candidate[] = [
        { actionType: 'best', params: {}, rawScores: { quality: 0.9, cost: 0.8, speed: 0.7 } },
        { actionType: 'second', params: {}, rawScores: { quality: 0.7, cost: 0.6, speed: 0.5 } },
      ];
      const result = core.decide(candidates, makeGoal());
      expect(result.reasoning).toContain('best');
      expect(result.reasoning).toContain('second');
    });
  });
});
