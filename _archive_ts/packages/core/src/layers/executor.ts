/**
 * L4 Execution Runtime - 执行运行时
 * 按 ExecutionPlan 执行 Skill，管理重试/降级/成本追踪
 */

import type {
  ExecutionPlan,
  ExecutionResult,
  ExecutionContext,
  StepResult,
  CostEstimate,
  RecipeDefinition,
} from '../types.js';
import { SkillRegistry } from '../skills/registry.js';
import { RecipeExecutor } from '../skills/recipe.js';
import { BudgetManager } from '../cost/budget.js';
import type { Logger } from '@velaris/shared';

/**
 * 执行器
 * 根据 ExecutionPlan 编排 Skill 执行，处理异常和预算管控
 */
export class Executor {
  private readonly recipeExecutor: RecipeExecutor;
  private readonly budgetManager: BudgetManager;

  constructor(
    private readonly registry: SkillRegistry,
    private readonly recipes: RecipeDefinition[],
    private readonly logger: Logger,
    budgetManager: BudgetManager,
  ) {
    this.recipeExecutor = new RecipeExecutor(registry);
    this.budgetManager = budgetManager;
  }

  /** 执行计划 */
  async execute(
    plan: ExecutionPlan,
    ctx: ExecutionContext,
  ): Promise<ExecutionResult> {
    const start = Date.now();
    this.logger.info('Executor starting', {
      planId: plan.planId,
      stepCount: plan.steps.length,
      recipe: plan.recipeName,
    });

    // 如果有匹配的 Recipe，使用 RecipeExecutor
    if (plan.recipeName) {
      const recipe = this.recipes.find((r) => r.name === plan.recipeName);
      if (recipe) {
        return this.executeRecipe(recipe, plan, ctx, start);
      }
    }

    // 否则逐步执行
    return this.executeSteps(plan, ctx, start);
  }

  /** 通过 Recipe 执行 */
  private async executeRecipe(
    recipe: RecipeDefinition,
    plan: ExecutionPlan,
    ctx: ExecutionContext,
    startTime: number,
  ): Promise<ExecutionResult> {
    // 预算检查
    this.budgetManager.enforce(ctx.costTracker);

    const result = await this.recipeExecutor.execute(
      recipe,
      plan.goal.constraints as Record<string, unknown>,
      ctx,
    );

    return {
      sessionId: ctx.sessionId,
      output: result.finalOutput,
      stepResults: result.stepResults,
      actualCost: result.totalCost,
      totalLatencyMs: Date.now() - startTime,
    };
  }

  /** 逐步执行 */
  private async executeSteps(
    plan: ExecutionPlan,
    ctx: ExecutionContext,
    startTime: number,
  ): Promise<ExecutionResult> {
    const stepResults: StepResult[] = [];
    let totalCost: CostEstimate = { inputTokens: 0, outputTokens: 0, totalUsd: 0, model: '' };

    for (const step of plan.steps) {
      // 预算检查
      const budgetCheck = this.budgetManager.check(ctx.costTracker);
      if (!budgetCheck.allowed) {
        this.logger.warn('Budget exceeded, stopping execution');
        break;
      }

      const skill = this.registry.get(step.skillName);
      const skillStart = Date.now();

      try {
        const input = step.input;
        const validatedInput = skill.inputSchema.parse(input);
        const output = await skill.execute(validatedInput, ctx);
        const validatedOutput = skill.outputSchema.parse(output);

        const result: StepResult = {
          skillName: step.skillName,
          output: validatedOutput,
          cost: skill.estimatedCost,
          latencyMs: Date.now() - skillStart,
          success: true,
        };

        stepResults.push(result);
        totalCost = this.addCosts(totalCost, result.cost);

        // 更新上下文中的前序输出
        ctx.previousOutputs[step.skillName] = validatedOutput;
      } catch (err) {
        const result: StepResult = {
          skillName: step.skillName,
          output: null,
          cost: { inputTokens: 0, outputTokens: 0, totalUsd: 0, model: '' },
          latencyMs: Date.now() - skillStart,
          success: false,
          error: err instanceof Error ? err.message : String(err),
        };

        stepResults.push(result);
        this.logger.error(`Step failed: ${step.skillName}`, { error: result.error });

        // 步骤失败则中止
        break;
      }
    }

    return {
      sessionId: ctx.sessionId,
      output: stepResults[stepResults.length - 1]?.output ?? null,
      stepResults,
      actualCost: totalCost,
      totalLatencyMs: Date.now() - startTime,
    };
  }

  /** 累加成本 */
  private addCosts(a: CostEstimate, b: CostEstimate): CostEstimate {
    return {
      inputTokens: a.inputTokens + b.inputTokens,
      outputTokens: a.outputTokens + b.outputTokens,
      totalUsd: a.totalUsd + b.totalUsd,
      model: b.model || a.model,
    };
  }
}
