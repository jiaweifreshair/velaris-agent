/**
 * @valeris/core - Valeris Agent AI Decision Runtime
 *
 * 主入口文件，导出核心 API
 */

import type { AgentConfig } from './types.js';
import { ValerisAgent } from './agent.js';

// ─── 核心工厂函数 ──────────────────────────────

/**
 * 创建 Valeris Agent 实例
 * 这是使用 Valeris Agent 的唯一入口
 *
 * @example
 * ```typescript
 * const agent = createAgent({
 *   productId: 'my-product',
 *   skills: [mySkill],
 *   recipes: [myRecipe],
 *   decisionWeights: { quality: 0.5, cost: 0.3, speed: 0.2 },
 *   storage: new MemoryStorage(),
 *   llm: new OpenAILLM({ apiKey: process.env.OPENAI_API_KEY }),
 * });
 *
 * const session = agent.createSession('user_123');
 * const result = await session.run('optimize my token cost');
 * ```
 */
export function createAgent(config: AgentConfig): ValerisAgent {
  return new ValerisAgent(config);
}

// ─── 类型导出 ───────────────────────────────────

export type {
  // 核心类型
  Goal,
  AgentConfig,
  DecisionResult,
  ScoredAction,
  DimensionScores,
  ModelRoute,
  CostEstimate,
  BudgetConfig,
  BudgetExceededStrategy,

  // Skill & Recipe
  SkillDefinition,
  RecipeDefinition,
  RecipeStep,

  // 执行相关
  ExecutionContext,
  ExecutionPlan,
  PlannedStep,
  ExecutionResult,
  StepResult,

  // 评估相关
  Evaluation,

  // Adapter 接口
  LLMAdapter,
  LLMChatRequest,
  LLMChatResponse,
  LLMMessage,
  StorageAdapter,
  SessionRecord,
  DecisionRecord,
  EvaluationRecord,
  CostEventRecord,
  CostTracker,

  // 事件
  ValerisEvents,
} from './types.js';

export { GoalSchema } from './types.js';

// ─── 类导出 ─────────────────────────────────────

export { ValerisAgent, ValerisSession } from './agent.js';

// 层级
export { GoalParser } from './layers/goal-parser.js';
export { Planner } from './layers/planner.js';
export { DecisionCore } from './layers/decision-core.js';
export type { Candidate, ConstraintFilter, DimensionScorer } from './layers/decision-core.js';
export { Executor } from './layers/executor.js';
export { Evaluator } from './layers/evaluator.js';

// 网络
export { EventBus } from './network/event-bus.js';
export { AgentNetwork } from './network/agent-network.js';
export { SubAgent } from './network/sub-agent.js';

// Skill
export { SkillRegistry } from './skills/registry.js';
export { defineSkill } from './skills/skill.js';
export { RecipeExecutor } from './skills/recipe.js';

// 内置 Skill
export { callLlmSkill } from './skills/builtins/call-llm.js';
export { scoreOptionsSkill } from './skills/builtins/score-options.js';
export { compressContextSkill } from './skills/builtins/compress-context.js';
export { fetchDataSkill } from './skills/builtins/fetch-data.js';

// 成本管控
export { SessionCostTracker } from './cost/tracker.js';
export { BudgetManager } from './cost/budget.js';
export { ContextCompressor } from './cost/compressor.js';
