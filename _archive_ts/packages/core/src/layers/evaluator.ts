/**
 * L5 Evaluator & Optimizer - 评估反馈层
 * 质量评分、成本分析、反馈收集
 */

import type {
  ExecutionResult,
  DecisionResult,
  Evaluation,
  StorageAdapter,
  CostEventRecord,
} from '../types.js';
import type { SessionCostTracker } from '../cost/tracker.js';
import type { Logger } from '@velaris/shared';

/**
 * 评估器
 * 收集执行结果，生成质量评分和成本分析
 */
export class Evaluator {
  constructor(
    private readonly storage: StorageAdapter,
    private readonly logger: Logger,
  ) {}

  /** 评估一次决策执行的结果 */
  async evaluate(
    decisionResult: DecisionResult,
    executionResult: ExecutionResult,
    costTracker: SessionCostTracker,
  ): Promise<Evaluation> {
    this.logger.info('Evaluating execution result', {
      sessionId: executionResult.sessionId,
    });

    // 计算质量评分
    const qualityScore = this.calculateQualityScore(executionResult);

    // 成本分析
    const costSummary = costTracker.getSummary();
    const costEvents = await this.storage.getCostEvents(executionResult.sessionId);
    const costAnalysis = this.analyzeCosts(costSummary, costEvents);

    // 保存决策记录
    const decisionId = await this.storage.saveDecision({
      sessionId: executionResult.sessionId,
      actionType: decisionResult.selectedAction.actionType,
      decisionJson: JSON.stringify(decisionResult),
      modelUsed: decisionResult.modelRouting.model,
      inputTokens: executionResult.actualCost.inputTokens,
      outputTokens: executionResult.actualCost.outputTokens,
      costUsd: executionResult.actualCost.totalUsd,
      latencyMs: executionResult.totalLatencyMs,
      createdAt: Date.now(),
    });

    const evaluation: Evaluation = {
      decisionId: String(decisionId),
      qualityScore,
      costAnalysis,
      metrics: {
        totalSteps: executionResult.stepResults.length,
        successfulSteps: executionResult.stepResults.filter((s) => s.success).length,
        totalLatencyMs: executionResult.totalLatencyMs,
        modelUsed: decisionResult.modelRouting.model,
      },
    };

    // 保存评估记录
    await this.storage.saveEvaluation({
      decisionId,
      qualityScore,
      metricsJson: JSON.stringify(evaluation.metrics),
      createdAt: Date.now(),
    });

    this.logger.info('Evaluation complete', {
      qualityScore,
      totalCostUsd: costSummary.totalCostUsd,
    });

    return evaluation;
  }

  /** 记录用户反馈 */
  async recordFeedback(
    decisionId: string,
    accepted: boolean,
    feedback?: string,
  ): Promise<void> {
    await this.storage.saveEvaluation({
      decisionId: parseInt(decisionId, 10),
      userAccepted: accepted,
      userFeedback: feedback,
      createdAt: Date.now(),
    });

    this.logger.info('User feedback recorded', { decisionId, accepted });
  }

  /** 计算质量评分 */
  private calculateQualityScore(result: ExecutionResult): number {
    const totalSteps = result.stepResults.length;
    if (totalSteps === 0) return 0;

    const successfulSteps = result.stepResults.filter((s) => s.success).length;
    const successRate = successfulSteps / totalSteps;

    // 延迟惩罚：超过 30s 开始扣分
    const latencyPenalty = Math.max(0, (result.totalLatencyMs - 30000) / 60000);
    const latencyScore = Math.max(0, 1 - latencyPenalty);

    // 综合评分：成功率 70% + 延迟 30%
    return Math.round((successRate * 0.7 + latencyScore * 0.3) * 1000) / 1000;
  }

  /** 成本分析 */
  private analyzeCosts(
    summary: { totalCostUsd: number; costByLayer: Record<string, number> },
    costEvents: CostEventRecord[],
  ): Evaluation['costAnalysis'] {
    const wastePoints: string[] = [];
    const optimizationHints: string[] = [];

    // 分析浪费点
    const compressEvents = costEvents.filter((e) => e.eventType === 'compress');
    if (compressEvents.length > 2) {
      wastePoints.push('Frequent context compression indicates prompt may be too long');
    }

    const downgradeEvents = costEvents.filter((e) => e.eventType === 'downgrade');
    if (downgradeEvents.length > 0) {
      wastePoints.push('Model downgrade occurred, initial model selection may be too aggressive');
    }

    // 优化建议
    if (summary.totalCostUsd > 0.5) {
      optimizationHints.push('Consider using lower-tier models for non-critical steps');
    }

    const executorCost = summary.costByLayer['executor'] ?? 0;
    if (executorCost > summary.totalCostUsd * 0.8) {
      optimizationHints.push('Executor layer dominates cost, consider caching or prompt optimization');
    }

    return {
      totalCostUsd: summary.totalCostUsd,
      costByLayer: summary.costByLayer,
      wastePoints,
      optimizationHints,
    };
  }
}
