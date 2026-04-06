/**
 * Recipe + SkillRegistry 单元测试
 * 验证 pipeline 步骤串联、并行执行、score-options
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { SkillRegistry } from '../src/skills/registry.js';
import { RecipeExecutor } from '../src/skills/recipe.js';
import { scoreOptionsSkill } from '../src/skills/builtins/score-options.js';
import { defineSkill } from '../src/skills/skill.js';
import { z } from 'zod';
import type { ExecutionContext, RecipeDefinition } from '../src/types.js';
import { createLogger } from '@velaris/shared';

/** 创建测试用 ExecutionContext */
function makeCtx(): ExecutionContext {
  return {
    sessionId: 'sess_test',
    goal: {
      goalType: 'test',
      userId: 'u1',
      intent: 'test',
      constraints: {},
      sessionId: 'sess_test',
    },
    llm: {
      async chat() {
        return { content: '{}', model: 'mock', usage: { inputTokens: 0, outputTokens: 0 }, finishReason: 'stop' as const };
      },
      async listModels() { return []; },
    },
    costTracker: {
      track: () => {},
      getTotalTokens: () => 0,
      getTotalCostUsd: () => 0,
      isBudgetExceeded: () => false,
    },
    logger: createLogger({ level: 'error' }),
    previousOutputs: {},
  };
}

describe('SkillRegistry', () => {
  it('应正确注册和检索 Skill', () => {
    const registry = new SkillRegistry();
    registry.register(scoreOptionsSkill);

    expect(registry.has('score-options')).toBe(true);
    expect(registry.get('score-options').name).toBe('score-options');
    expect(registry.size).toBe(1);
  });

  it('重复注册同名 Skill 应抛出错误', () => {
    const registry = new SkillRegistry();
    registry.register(scoreOptionsSkill);
    expect(() => registry.register(scoreOptionsSkill)).toThrow('already registered');
  });

  it('查找不存在的 Skill 应抛出 SkillNotFoundError', () => {
    const registry = new SkillRegistry();
    expect(() => registry.get('nonexistent')).toThrow('Skill not found');
  });

  it('find 不存在的 Skill 应返回 null', () => {
    const registry = new SkillRegistry();
    expect(registry.find('nonexistent')).toBeNull();
  });

  it('listNames 应返回所有注册名称', () => {
    const registry = new SkillRegistry();
    registry.register(scoreOptionsSkill);
    expect(registry.listNames()).toEqual(['score-options']);
  });
});

describe('score-options Skill', () => {
  it('应正确按权重打分排序', async () => {
    const input = {
      candidates: [
        { id: 'a', actionType: 'plan_a', params: {}, rawScores: { quality: 0.9, cost: 0.3 } },
        { id: 'b', actionType: 'plan_b', params: {}, rawScores: { quality: 0.5, cost: 0.9 } },
      ],
      weights: { quality: 0.6, cost: 0.4 },
    };

    const result = await scoreOptionsSkill.execute(input, makeCtx());

    // a: 0.9*0.6 + 0.3*0.4 = 0.54+0.12 = 0.66
    // b: 0.5*0.6 + 0.9*0.4 = 0.30+0.36 = 0.66
    // 相同得分保持原序
    expect(result.ranked).toHaveLength(2);
    expect(result.ranked[0]!.score).toBeCloseTo(0.66, 2);
  });

  it('空候选列表应返回空', async () => {
    const result = await scoreOptionsSkill.execute(
      { candidates: [], weights: { quality: 1 } },
      makeCtx(),
    );
    expect(result.ranked).toHaveLength(0);
  });
});

describe('RecipeExecutor', () => {
  let registry: SkillRegistry;

  /** 简单的自增 Skill */
  const addOneSkill = defineSkill({
    name: 'add-one',
    description: 'Add 1 to value',
    inputSchema: z.object({ value: z.number() }),
    outputSchema: z.object({ value: z.number() }),
    async execute(input) {
      return { value: input.value + 1 };
    },
  });

  /** 乘 2 Skill */
  const doubleSkill = defineSkill({
    name: 'double',
    description: 'Double value',
    inputSchema: z.object({ value: z.number() }),
    outputSchema: z.object({ value: z.number() }),
    async execute(input) {
      return { value: input.value * 2 };
    },
  });

  beforeEach(() => {
    registry = new SkillRegistry();
    registry.register(addOneSkill);
    registry.register(doubleSkill);
  });

  it('应按顺序串行执行 Recipe 步骤', async () => {
    const recipe: RecipeDefinition = {
      name: 'test-serial',
      description: 'test',
      steps: [
        { skill: 'add-one' },
        { skill: 'double' },
      ],
    };

    const executor = new RecipeExecutor(registry);
    const result = await executor.execute(recipe, { value: 5 }, makeCtx());

    // add-one: 5 -> 6, double: 6 -> 12
    expect(result.stepResults).toHaveLength(2);
    expect(result.stepResults[0]!.success).toBe(true);
    expect(result.stepResults[1]!.success).toBe(true);
    expect((result.finalOutput as { value: number }).value).toBe(12);
  });

  it('步骤失败时应中止执行', async () => {
    const failSkill = defineSkill({
      name: 'fail',
      description: 'Always fails',
      inputSchema: z.object({ value: z.number() }),
      outputSchema: z.object({ value: z.number() }),
      async execute() {
        throw new Error('intentional failure');
      },
    });
    registry.register(failSkill);

    const recipe: RecipeDefinition = {
      name: 'test-fail',
      description: 'test',
      steps: [
        { skill: 'fail' },
        { skill: 'double' }, // 不应执行
      ],
    };

    const executor = new RecipeExecutor(registry);
    const result = await executor.execute(recipe, { value: 5 }, makeCtx());

    expect(result.stepResults).toHaveLength(1);
    expect(result.stepResults[0]!.success).toBe(false);
    expect(result.stepResults[0]!.error).toContain('intentional failure');
  });

  it('应支持并行执行 Skill', async () => {
    const recipe: RecipeDefinition = {
      name: 'test-parallel',
      description: 'test',
      steps: [
        { skill: 'add-one', parallel: ['double'] },
      ],
    };

    const executor = new RecipeExecutor(registry);
    const result = await executor.execute(recipe, { value: 5 }, makeCtx());

    // 并行: add-one(5)=6, double(5)=10
    expect(result.stepResults).toHaveLength(2);
    expect(result.stepResults.every((s) => s.success)).toBe(true);
  });
});

describe('EventBus', () => {
  it('应正确发布和订阅事件', async () => {
    const { EventBus } = await import('../src/network/event-bus.js');
    const bus = new EventBus();

    const received: unknown[] = [];
    bus.on('session:created', (data) => received.push(data));

    bus.emit('session:created', { sessionId: 'test', userId: 'u1' });

    expect(received).toHaveLength(1);
    expect((received[0] as { sessionId: string }).sessionId).toBe('test');
  });

  it('once 只应触发一次', async () => {
    const { EventBus } = await import('../src/network/event-bus.js');
    const bus = new EventBus();

    let count = 0;
    bus.once('session:created', () => { count++; });

    bus.emit('session:created', { sessionId: 'a', userId: 'u1' });
    bus.emit('session:created', { sessionId: 'b', userId: 'u1' });

    expect(count).toBe(1);
  });

  it('removeAll 应清除所有监听器', async () => {
    const { EventBus } = await import('../src/network/event-bus.js');
    const bus = new EventBus();

    bus.on('session:created', () => {});
    bus.on('session:completed', () => {});
    bus.removeAll();

    expect(bus.listenerCount('session:created')).toBe(0);
    expect(bus.listenerCount('session:completed')).toBe(0);
  });
});
