/**
 * L3 Decision Core - 决策核心层 *
 * 多维加权打分、约束过滤、模型路由决策
 * 这是 Velaris Agent 的核心壁垒模块
 */

import type {
  Goal,
  ScoredAction,
  DecisionResult,
  DimensionScores,
  ModelRoute,
  CostEstimate,
} from '../types.js';
import { DecisionError } from '@velaris/shared';
import type { Logger } from '@velaris/shared';

/** 候选方案（Decision Core 输入） */
export interface Candidate {
  /** 动作类型 */
  actionType: string;
  /** 动作参数 */
  params: Record<string, unknown>;
  /** 各维度原始分数（0-1） */
  rawScores: DimensionScores;
}

/** 约束过滤器 */
export interface ConstraintFilter {
  /** 过滤器名称 */
  name: string;
  /** 过滤函数，返回 true 表示通过 */
  filter: (candidate: Candidate, goal: Goal) => boolean;
}

/** 自定义打分器 */
export interface DimensionScorer {
  /** 维度名称 */
  dimension: string;
  /** 打分函数，返回 0-1 分数 */
  score: (candidate: Candidate, goal: Goal) => number;
}

/** 模型价格配置 */
interface ModelPricing {
  inputPer1M: number;
  outputPer1M: number;
  tier: 'high' | 'medium' | 'low';
}

/** 默认模型价格表 */
const DEFAULT_MODEL_PRICING: Record<string, ModelPricing> = {
  'gpt-4o': { inputPer1M: 2.5, outputPer1M: 10.0, tier: 'high' },
  'gpt-4o-mini': { inputPer1M: 0.15, outputPer1M: 0.6, tier: 'medium' },
  'gpt-4.1-mini': { inputPer1M: 0.4, outputPer1M: 1.6, tier: 'medium' },
  'gpt-4.1-nano': { inputPer1M: 0.1, outputPer1M: 0.4, tier: 'low' },
  'claude-sonnet-4': { inputPer1M: 3.0, outputPer1M: 15.0, tier: 'high' },
  'claude-haiku-3.5': { inputPer1M: 0.8, outputPer1M: 4.0, tier: 'medium' },
  'gemini-2.0-flash': { inputPer1M: 0.1, outputPer1M: 0.4, tier: 'low' },
};

/**
 * 决策引擎
 * 核心职责：候选生成 -> 约束过滤 -> 多维打分 -> 模型路由
 */
export class DecisionCore {
  private readonly constraintFilters: ConstraintFilter[] = [];
  private readonly customScorers: DimensionScorer[] = [];

  constructor(
    private readonly weights: DimensionScores,
    private readonly logger: Logger,
    private readonly modelPricing: Record<string, ModelPricing> = DEFAULT_MODEL_PRICING,
  ) {}

  /** 注册约束过滤器 */
  addFilter(filter: ConstraintFilter): void {
    this.constraintFilters.push(filter);
  }

  /** 注册自定义打分器 */
  addScorer(scorer: DimensionScorer): void {
    this.customScorers.push(scorer);
  }

  /**
   * 执行决策
   * 1. 约束过滤
   * 2. 多维打分
   * 3. 排序选优
   * 4. 模型路由
   */
  decide(candidates: Candidate[], goal: Goal): DecisionResult {
    this.logger.info('Decision Core processing', {
      candidateCount: candidates.length,
      goalType: goal.goalType,
    });

    if (candidates.length === 0) {
      throw new DecisionError('No candidates provided for decision');
    }

    // Step 1: 约束过滤
    const filtered = this.applyFilters(candidates, goal);
    if (filtered.length === 0) {
      throw new DecisionError(
        'All candidates were filtered out by constraints',
        { sessionId: goal.sessionId },
      );
    }

    this.logger.info('Candidates after filtering', {
      before: candidates.length,
      after: filtered.length,
    });

    // Step 2: 应用自定义打分器
    const enhanced = this.applyCustomScorers(filtered, goal);

    // Step 3: 多维加权打分
    const scored = this.scoreCandidates(enhanced);

    // Step 4: 排序
    scored.sort((a, b) => b.score - a.score);

    // Step 5: 模型路由决策
    const modelRouting = this.routeModel(goal);

    // Step 6: 成本预估
    const costEstimate = this.estimateCost(modelRouting.model);

    const selected = scored[0]!;
    const alternatives = scored.slice(1);

    // 生成决策推理
    const reasoning = this.generateReasoning(selected, alternatives, goal);

    this.logger.info('Decision made', {
      selectedAction: selected.actionType,
      score: selected.score,
      alternativeCount: alternatives.length,
    });

    return {
      selectedAction: selected,
      alternatives,
      modelRouting,
      costEstimate,
      reasoning,
    };
  }

  /** 约束过滤 */
  private applyFilters(candidates: Candidate[], goal: Goal): Candidate[] {
    let result = candidates;
    for (const filter of this.constraintFilters) {
      result = result.filter((c) => filter.filter(c, goal));
    }
    return result;
  }

  /** 应用自定义打分器 */
  private applyCustomScorers(candidates: Candidate[], goal: Goal): Candidate[] {
    return candidates.map((candidate) => {
      const enhancedScores = { ...candidate.rawScores };
      for (const scorer of this.customScorers) {
        enhancedScores[scorer.dimension] = scorer.score(candidate, goal);
      }
      return { ...candidate, rawScores: enhancedScores };
    });
  }

  /** 多维加权打分 */
  private scoreCandidates(candidates: Candidate[]): ScoredAction[] {
    // 归一化权重
    const totalWeight = Object.values(this.weights).reduce((sum, w) => sum + w, 0);
    const normalized: DimensionScores = {};
    for (const [dim, w] of Object.entries(this.weights)) {
      normalized[dim] = totalWeight > 0 ? w / totalWeight : 0;
    }

    return candidates.map((candidate) => {
      const scores: DimensionScores = {};
      let totalScore = 0;

      for (const [dim, weight] of Object.entries(normalized)) {
        const raw = candidate.rawScores[dim] ?? 0;
        const clamped = Math.max(0, Math.min(1, raw));
        scores[dim] = clamped;
        totalScore += clamped * weight;
      }

      return {
        actionType: candidate.actionType,
        params: candidate.params,
        score: Math.round(totalScore * 1000) / 1000,
        scores,
      };
    });
  }

  /** 模型路由：根据预算和质量要求选择模型 */
  private routeModel(goal: Goal): ModelRoute {
    const budgetCost = goal.budget?.maxCostUsd;

    // 无预算限制，使用高端模型
    if (!budgetCost || budgetCost >= 1.0) {
      return { model: 'gpt-4o', reason: 'No budget constraint, using high-quality model', tier: 'high' };
    }

    // 低预算，使用经济模型
    if (budgetCost < 0.1) {
      return { model: 'gpt-4.1-nano', reason: 'Low budget, using economy model', tier: 'low' };
    }

    // 中等预算
    return { model: 'gpt-4o-mini', reason: 'Moderate budget, using balanced model', tier: 'medium' };
  }

  /** 预估成本 */
  private estimateCost(model: string): CostEstimate {
    const pricing = this.modelPricing[model] ?? { inputPer1M: 0.15, outputPer1M: 0.6 };
    const estimatedInputTokens = 2000;
    const estimatedOutputTokens = 1000;

    return {
      inputTokens: estimatedInputTokens,
      outputTokens: estimatedOutputTokens,
      totalUsd:
        (estimatedInputTokens * pricing.inputPer1M) / 1_000_000 +
        (estimatedOutputTokens * pricing.outputPer1M) / 1_000_000,
      model,
    };
  }

  /** 生成决策推理文本 */
  private generateReasoning(
    selected: ScoredAction,
    alternatives: ScoredAction[],
    _goal: Goal,
  ): string {
    const topScores = Object.entries(selected.scores)
      .sort(([, a], [, b]) => b - a)
      .map(([dim, score]) => `${dim}: ${(score * 100).toFixed(0)}%`)
      .join(', ');

    let reasoning = `Selected "${selected.actionType}" (score: ${selected.score}) based on: ${topScores}.`;

    if (alternatives.length > 0) {
      const alt = alternatives[0]!;
      reasoning += ` Next best: "${alt.actionType}" (score: ${alt.score}).`;
    }

    return reasoning;
  }
}
