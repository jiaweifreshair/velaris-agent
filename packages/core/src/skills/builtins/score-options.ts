/**
 * 内置 Skill: score-options
 * 多维加权打分，对候选方案进行排序
 */

import { z } from 'zod';
import { defineSkill } from '../skill.js';

/** 候选方案 */
const CandidateSchema = z.object({
  /** 方案标识 */
  id: z.string(),
  /** 方案类型 */
  actionType: z.string(),
  /** 方案参数 */
  params: z.record(z.unknown()),
  /** 各维度原始分数（0-1） */
  rawScores: z.record(z.number()),
});

/** score-options 输入 */
const ScoreOptionsInput = z.object({
  /** 候选方案列表 */
  candidates: z.array(CandidateSchema),
  /** 维度权重（key=维度名, value=权重, 所有权重之和应为 1） */
  weights: z.record(z.number()),
});

/** score-options 输出 */
const ScoreOptionsOutput = z.object({
  /** 排序后的方案列表（得分从高到低） */
  ranked: z.array(
    z.object({
      id: z.string(),
      actionType: z.string(),
      params: z.record(z.unknown()),
      score: z.number(),
      scores: z.record(z.number()),
    }),
  ),
});

export const scoreOptionsSkill = defineSkill({
  name: 'score-options',
  description: '多维加权打分，对候选方案排序',
  inputSchema: ScoreOptionsInput,
  outputSchema: ScoreOptionsOutput,

  async execute(input, _ctx) {
    // 归一化权重
    const totalWeight = Object.values(input.weights).reduce((sum, w) => sum + w, 0);
    const normalizedWeights: Record<string, number> = {};
    for (const [dim, w] of Object.entries(input.weights)) {
      normalizedWeights[dim] = totalWeight > 0 ? w / totalWeight : 0;
    }

    // 对每个候选方案计算加权得分
    const scored = input.candidates.map((candidate) => {
      const scores: Record<string, number> = {};
      let totalScore = 0;

      for (const [dim, weight] of Object.entries(normalizedWeights)) {
        const rawScore = candidate.rawScores[dim] ?? 0;
        const clampedScore = Math.max(0, Math.min(1, rawScore));
        scores[dim] = clampedScore;
        totalScore += clampedScore * weight;
      }

      return {
        id: candidate.id,
        actionType: candidate.actionType,
        params: candidate.params,
        score: Math.round(totalScore * 1000) / 1000, // 保留 3 位小数
        scores,
      };
    });

    // 按总分降序排列
    scored.sort((a, b) => b.score - a.score);

    return { ranked: scored };
  },
});
