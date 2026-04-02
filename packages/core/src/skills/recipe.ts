/**
 * Recipe 编排器
 * 将多个 Skill 按 RecipeDefinition 串联/并行执行
 */

import type {
  RecipeDefinition,
  RecipeStep,
  ExecutionContext,
  StepResult,
  CostEstimate,
} from '../types.js';
import { SkillRegistry } from './registry.js';

/** Recipe 执行结果 */
export interface RecipeExecutionResult {
  /** Recipe 名称 */
  recipeName: string;
  /** 各步骤结果 */
  stepResults: StepResult[];
  /** 最终输出（最后一步的输出） */
  finalOutput: unknown;
  /** 累计成本 */
  totalCost: CostEstimate;
  /** 总耗时 */
  totalLatencyMs: number;
}

/**
 * Recipe 执行器
 * 按照 RecipeDefinition 中的步骤定义，串行或并行执行 Skill
 */
export class RecipeExecutor {
  constructor(private readonly registry: SkillRegistry) {}

  /** 执行 Recipe */
  async execute(
    recipe: RecipeDefinition,
    initialInput: Record<string, unknown>,
    ctx: ExecutionContext,
  ): Promise<RecipeExecutionResult> {
    const stepResults: StepResult[] = [];
    const outputs: (Record<string, unknown> | null)[] = [];
    let totalCost: CostEstimate = { inputTokens: 0, outputTokens: 0, totalUsd: 0, model: '' };
    let totalLatencyMs = 0;

    // 将初始输入作为第一个输出供后续步骤引用
    outputs.push(initialInput);

    for (const step of recipe.steps) {
      // 条件检查
      if (step.condition && !this.evaluateCondition(step.condition, ctx, outputs)) {
        stepResults.push({
          skillName: step.skill,
          output: null,
          cost: { inputTokens: 0, outputTokens: 0, totalUsd: 0, model: '' },
          latencyMs: 0,
          success: true,
        });
        outputs.push(null);
        continue;
      }

      // 检查预算
      if (ctx.costTracker.isBudgetExceeded()) {
        ctx.logger.warn('Budget exceeded, stopping recipe execution');
        break;
      }

      // 并行执行
      if (step.parallel && step.parallel.length > 0) {
        const parallelResult = await this.executeParallel(step, ctx, outputs);
        stepResults.push(...parallelResult.results);
        outputs.push(parallelResult.mergedOutput);
        totalCost = this.mergeCosts(totalCost, ...parallelResult.results.map((r) => r.cost));
        totalLatencyMs += parallelResult.maxLatencyMs;
        continue;
      }

      // 串行执行
      const result = await this.executeStep(step, ctx, outputs);
      stepResults.push(result);
      outputs.push(result.output as Record<string, unknown> | null);
      totalCost = this.mergeCosts(totalCost, result.cost);
      totalLatencyMs += result.latencyMs;

      // 步骤失败则中止
      if (!result.success) {
        ctx.logger.error(`Step failed: ${step.skill}`, { error: result.error });
        break;
      }
    }

    // 最终输出取最后一个非 null 的步骤输出
    const finalOutput = outputs.filter((o) => o !== null).pop() ?? null;

    return {
      recipeName: recipe.name,
      stepResults,
      finalOutput,
      totalCost,
      totalLatencyMs,
    };
  }

  /** 执行单个步骤 */
  private async executeStep(
    step: RecipeStep,
    ctx: ExecutionContext,
    previousOutputs: (Record<string, unknown> | null)[],
  ): Promise<StepResult> {
    const skill = this.registry.get(step.skill);
    const input = this.resolveInput(step, previousOutputs);

    ctx.logger.info(`Executing skill: ${skill.name}`);
    ctx.eventBus?.emit?.('skill:start', { sessionId: ctx.sessionId, skillName: skill.name });

    const start = Date.now();

    try {
      const validatedInput = skill.inputSchema.parse(input);
      const output = await skill.execute(validatedInput, ctx);
      const validatedOutput = skill.outputSchema.parse(output);
      const latencyMs = Date.now() - start;

      ctx.eventBus?.emit?.('skill:complete', {
        sessionId: ctx.sessionId,
        skillName: skill.name,
        latencyMs,
      });

      return {
        skillName: skill.name,
        output: validatedOutput,
        cost: skill.estimatedCost,
        latencyMs,
        success: true,
      };
    } catch (err) {
      const latencyMs = Date.now() - start;
      const errorMsg = err instanceof Error ? err.message : String(err);

      ctx.eventBus?.emit?.('skill:error', {
        sessionId: ctx.sessionId,
        skillName: skill.name,
        error: errorMsg,
      });

      return {
        skillName: skill.name,
        output: null,
        cost: { inputTokens: 0, outputTokens: 0, totalUsd: 0, model: '' },
        latencyMs,
        success: false,
        error: errorMsg,
      };
    }
  }

  /** 并行执行多个 Skill */
  private async executeParallel(
    step: RecipeStep,
    ctx: ExecutionContext,
    previousOutputs: (Record<string, unknown> | null)[],
  ): Promise<{
    results: StepResult[];
    mergedOutput: Record<string, unknown>;
    maxLatencyMs: number;
  }> {
    const skillNames = [step.skill, ...(step.parallel ?? [])];
    const promises = skillNames.map((name) =>
      this.executeStep({ skill: name, inputMap: step.inputMap }, ctx, previousOutputs),
    );

    const results = await Promise.all(promises);
    const maxLatencyMs = Math.max(...results.map((r) => r.latencyMs));

    // 合并并行结果为一个对象
    const mergedOutput: Record<string, unknown> = {};
    for (const result of results) {
      mergedOutput[result.skillName] = result.output;
    }

    return { results, mergedOutput, maxLatencyMs };
  }

  /** 解析步骤输入：根据 inputMap 从前序输出中提取数据 */
  private resolveInput(
    step: RecipeStep,
    previousOutputs: (Record<string, unknown> | null)[],
  ): Record<string, unknown> {
    if (!step.inputMap) {
      // 无映射时，传入上一步的完整输出
      return (previousOutputs[previousOutputs.length - 1] ?? {}) as Record<string, unknown>;
    }

    const input: Record<string, unknown> = {};
    for (const [key, expr] of Object.entries(step.inputMap)) {
      input[key] = this.resolveExpression(expr, previousOutputs);
    }
    return input;
  }

  /** 解析表达式，支持 prev.field 和 steps[n].field 语法 */
  private resolveExpression(
    expr: string,
    previousOutputs: (Record<string, unknown> | null)[],
  ): unknown {
    // prev.xxx -> 上一步输出的 xxx 字段
    if (expr.startsWith('prev.')) {
      const field = expr.substring(5);
      const prev = previousOutputs[previousOutputs.length - 1];
      return this.getNestedValue(prev, field);
    }

    // steps[n].output -> 第 n 步输出
    const stepsMatch = expr.match(/^steps\[(\d+)\]\.(.+)$/);
    if (stepsMatch) {
      const index = parseInt(stepsMatch[1]!, 10);
      const field = stepsMatch[2]!;
      // +1 因为 outputs[0] 是初始输入
      const stepOutput = previousOutputs[index + 1];
      return this.getNestedValue(stepOutput, field);
    }

    // 原样返回
    return expr;
  }

  /** 获取嵌套字段值 */
  private getNestedValue(obj: unknown, path: string): unknown {
    const parts = path.split('.');
    let current = obj;
    for (const part of parts) {
      if (current == null || typeof current !== 'object') return undefined;
      current = (current as Record<string, unknown>)[part];
    }
    return current;
  }

  /** 评估条件表达式（简单实现） */
  private evaluateCondition(
    condition: string,
    ctx: ExecutionContext,
    _outputs: (Record<string, unknown> | null)[],
  ): boolean {
    // 简单的条件评估：支持 goal.constraints.xxx !== yyy 等基本表达式
    try {
      if (condition.includes('goal.constraints.')) {
        const match = condition.match(/goal\.constraints\.(\w+)\s*(!==|===|!=|==)\s*(.+)/);
        if (match) {
          const [, field, op, value] = match;
          const actual = ctx.goal.constraints[field!];
          const expected = value!.replace(/['"]/g, '');
          switch (op) {
            case '!=':
            case '!==':
              return String(actual) !== expected;
            case '==':
            case '===':
              return String(actual) === expected;
          }
        }
      }
      return true; // 默认执行
    } catch {
      return true;
    }
  }

  /** 合并多个成本估算 */
  private mergeCosts(...costs: CostEstimate[]): CostEstimate {
    return costs.reduce(
      (acc, c) => ({
        inputTokens: acc.inputTokens + c.inputTokens,
        outputTokens: acc.outputTokens + c.outputTokens,
        totalUsd: acc.totalUsd + c.totalUsd,
        model: c.model || acc.model,
      }),
      { inputTokens: 0, outputTokens: 0, totalUsd: 0, model: '' },
    );
  }
}

// 扩展 ExecutionContext 以包含可选的 eventBus
declare module '../types.js' {
  interface ExecutionContext {
    eventBus?: import('../network/event-bus.js').EventBus;
  }
}
