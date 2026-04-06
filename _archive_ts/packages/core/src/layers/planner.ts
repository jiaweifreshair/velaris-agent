/**
 * L2 Planner & Pipeline Composer - 规划编排层
 * 根据 Goal 选择合适的 Skill/Recipe，组装执行计划
 */

import type {
  Goal,
  ExecutionPlan,
  PlannedStep,
  RecipeDefinition,
  CostEstimate,
} from '../types.js';
import { SkillRegistry } from '../skills/registry.js';
import { generateId } from '@velaris/shared';
import type { Logger } from '@velaris/shared';

/**
 * 规划器
 * 根据 Goal 匹配 Recipe 或自动组合 Skill
 */
export class Planner {
  constructor(
    private readonly registry: SkillRegistry,
    private readonly recipes: RecipeDefinition[],
    private readonly logger: Logger,
  ) {}

  /** 根据 Goal 生成执行计划 */
  plan(goal: Goal): ExecutionPlan {
    this.logger.info('Planning execution', { goalType: goal.goalType });

    // 优先匹配 Recipe
    const recipe = this.findMatchingRecipe(goal);
    if (recipe) {
      return this.planFromRecipe(goal, recipe);
    }

    // 无匹配 Recipe 时，返回空计划（由上层处理）
    this.logger.warn('No matching recipe found, creating empty plan');
    return {
      planId: generateId('plan'),
      goal,
      steps: [],
      estimatedTotalCost: { inputTokens: 0, outputTokens: 0, totalUsd: 0, model: '' },
    };
  }

  /** 从 Recipe 创建执行计划 */
  private planFromRecipe(goal: Goal, recipe: RecipeDefinition): ExecutionPlan {
    this.logger.info('Planning from recipe', { recipe: recipe.name });

    const steps: PlannedStep[] = [];
    let totalCost: CostEstimate = { inputTokens: 0, outputTokens: 0, totalUsd: 0, model: '' };

    for (let i = 0; i < recipe.steps.length; i++) {
      const step = recipe.steps[i]!;

      // 检查 Skill 是否存在
      const skill = this.registry.find(step.skill);
      if (!skill) {
        this.logger.warn(`Skill not found in recipe step: ${step.skill}`);
        continue;
      }

      const plannedStep: PlannedStep = {
        index: i,
        skillName: step.skill,
        input: step.inputMap ?? {},
        isParallel: (step.parallel?.length ?? 0) > 0,
        parallelWith: step.parallel,
      };

      steps.push(plannedStep);

      // 累计预估成本
      totalCost = {
        inputTokens: totalCost.inputTokens + skill.estimatedCost.inputTokens,
        outputTokens: totalCost.outputTokens + skill.estimatedCost.outputTokens,
        totalUsd: totalCost.totalUsd + skill.estimatedCost.totalUsd,
        model: skill.estimatedCost.model || totalCost.model,
      };

      // 并行步骤的成本也要计入
      if (step.parallel) {
        for (const parallelSkillName of step.parallel) {
          const parallelSkill = this.registry.find(parallelSkillName);
          if (parallelSkill) {
            totalCost = {
              inputTokens: totalCost.inputTokens + parallelSkill.estimatedCost.inputTokens,
              outputTokens: totalCost.outputTokens + parallelSkill.estimatedCost.outputTokens,
              totalUsd: totalCost.totalUsd + parallelSkill.estimatedCost.totalUsd,
              model: parallelSkill.estimatedCost.model || totalCost.model,
            };
          }
        }
      }
    }

    return {
      planId: generateId('plan'),
      goal,
      recipeName: recipe.name,
      steps,
      estimatedTotalCost: totalCost,
    };
  }

  /** 查找匹配的 Recipe */
  private findMatchingRecipe(goal: Goal): RecipeDefinition | null {
    // 简单匹配：Recipe 名称包含 goalType
    // 未来可以扩展为基于 LLM 的智能匹配
    for (const recipe of this.recipes) {
      if (
        recipe.name.includes(goal.goalType) ||
        goal.goalType.includes(recipe.name)
      ) {
        return recipe;
      }
    }

    // 返回第一个 Recipe 作为默认（如果有的话）
    return this.recipes[0] ?? null;
  }
}
