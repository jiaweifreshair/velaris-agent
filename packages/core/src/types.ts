/**
 * Valeris Agent 核心类型定义
 * 所有 Zod Schema + TypeScript 接口
 */

import { z } from 'zod';

// ─── GoalSchema - 用户意图的结构化表达 ───────────────────

export const GoalSchema = z.object({
  /** 目标类型标识（如 token_optimize, charter_quote） */
  goalType: z.string(),
  /** 用户标识 */
  userId: z.string(),
  /** 自然语言意图描述 */
  intent: z.string(),
  /** 约束条件（领域相关，自由结构） */
  constraints: z.record(z.unknown()),
  /** 用户偏好（可选） */
  preferences: z.record(z.unknown()).optional(),
  /** 会话标识 */
  sessionId: z.string(),
  /** 预算约束 */
  budget: z
    .object({
      /** 最大 token 数 */
      maxTokens: z.number().optional(),
      /** 最大花费 USD */
      maxCostUsd: z.number().optional(),
      /** 最大延迟毫秒 */
      maxLatencyMs: z.number().optional(),
    })
    .optional(),
});

export type Goal = z.infer<typeof GoalSchema>;

// ─── 多维评分 ──────────────────────────────────────────

/** 各维度得分，key 为维度名（如 quality, cost, speed） */
export interface DimensionScores {
  [dimension: string]: number;
}

// ─── ScoredAction - 打分后的候选方案 ──────────────────

export interface ScoredAction {
  /** 动作类型标识 */
  actionType: string;
  /** 动作参数 */
  params: Record<string, unknown>;
  /** 0-1 综合得分 */
  score: number;
  /** 各维度明细得分 */
  scores: DimensionScores;
}

// ─── ModelRoute - 模型路由决策 ─────────────────────────

export interface ModelRoute {
  /** 选用的模型标识 */
  model: string;
  /** 选择理由 */
  reason: string;
  /** 模型能力等级（用于降级判断） */
  tier: 'high' | 'medium' | 'low';
}

// ─── CostEstimate - 成本预估 ──────────────────────────

export interface CostEstimate {
  /** 输入 token 数 */
  inputTokens: number;
  /** 输出 token 数 */
  outputTokens: number;
  /** 总花费 USD */
  totalUsd: number;
  /** 使用的模型 */
  model: string;
}

// ─── DecisionResult - 决策结果 ─────────────────────────

export interface DecisionResult {
  /** 最优方案 */
  selectedAction: ScoredAction;
  /** 备选方案 */
  alternatives: ScoredAction[];
  /** 模型路由决策 */
  modelRouting: ModelRoute;
  /** 成本预估 */
  costEstimate: CostEstimate;
  /** 决策推理（自然语言） */
  reasoning: string;
}

// ─── BudgetConfig - 预算配置 ──────────────────────────

/** 预算超限时的策略 */
export type BudgetExceededStrategy = 'compress' | 'downgrade' | 'stop';

export interface BudgetConfig {
  /** 单会话最大 token 数 */
  maxTokensPerSession: number;
  /** 单会话最大花费 USD */
  maxCostPerSession: number;
  /** 超限策略 */
  onBudgetExceeded: BudgetExceededStrategy;
}

// ─── Execution Context - 执行上下文 ──────────────────

export interface ExecutionContext {
  /** 当前会话 ID */
  sessionId: string;
  /** 当前 Goal */
  goal: Goal;
  /** LLM 适配器 */
  llm: LLMAdapter;
  /** 成本追踪器 */
  costTracker: CostTracker;
  /** 日志器 */
  logger: import('@valeris/shared').Logger;
  /** 前序步骤的输出数据 */
  previousOutputs: Record<string, unknown>;
}

// ─── Skill 定义 ──────────────────────────────────────

export interface SkillDefinition<TInput = unknown, TOutput = unknown> {
  /** Skill 名称（唯一标识） */
  name: string;
  /** Skill 描述 */
  description: string;
  /** 输入 Schema（Zod） */
  inputSchema: z.ZodType<TInput>;
  /** 输出 Schema（Zod） */
  outputSchema: z.ZodType<TOutput>;
  /** 预估成本 */
  estimatedCost: CostEstimate;
  /** 执行函数 */
  execute: (input: TInput, ctx: ExecutionContext) => Promise<TOutput>;
}

// ─── Recipe 定义 ─────────────────────────────────────

export interface RecipeStep {
  /** 引用的 Skill 名称 */
  skill: string;
  /** 输入映射：key = 本步输入字段，value = 数据来源表达式 */
  inputMap?: Record<string, string>;
  /** 并行执行的 Skill 列表 */
  parallel?: string[];
  /** 条件执行表达式（为 truthy 时执行） */
  condition?: string;
}

export interface RecipeDefinition {
  /** Recipe 名称 */
  name: string;
  /** Recipe 描述 */
  description: string;
  /** 执行步骤 */
  steps: RecipeStep[];
}

// ─── ExecutionPlan - 规划结果 ────────────────────────

export interface ExecutionPlan {
  /** 计划 ID */
  planId: string;
  /** 关联的 Goal */
  goal: Goal;
  /** 选用的 Recipe 名称（如果有） */
  recipeName?: string;
  /** 执行步骤 */
  steps: PlannedStep[];
  /** 预估总成本 */
  estimatedTotalCost: CostEstimate;
}

export interface PlannedStep {
  /** 步骤序号 */
  index: number;
  /** Skill 名称 */
  skillName: string;
  /** 输入数据（可能引用前序步骤输出） */
  input: Record<string, unknown>;
  /** 是否并行执行 */
  isParallel: boolean;
  /** 并行组内的其他 Skill */
  parallelWith?: string[];
}

// ─── ExecutionResult - 执行结果 ─────────────────────

export interface ExecutionResult {
  /** 会话 ID */
  sessionId: string;
  /** 最终输出 */
  output: unknown;
  /** 各步骤结果 */
  stepResults: StepResult[];
  /** 实际花费 */
  actualCost: CostEstimate;
  /** 总延迟（毫秒） */
  totalLatencyMs: number;
}

export interface StepResult {
  /** Skill 名称 */
  skillName: string;
  /** 输出数据 */
  output: unknown;
  /** 花费 */
  cost: CostEstimate;
  /** 延迟（毫秒） */
  latencyMs: number;
  /** 是否成功 */
  success: boolean;
  /** 错误信息（失败时） */
  error?: string;
}

// ─── Evaluation - 评估结果 ──────────────────────────

export interface Evaluation {
  /** 关联的决策 ID */
  decisionId: string;
  /** 质量评分 0-1 */
  qualityScore: number;
  /** 用户是否采纳 */
  userAccepted?: boolean;
  /** 用户反馈文本 */
  userFeedback?: string;
  /** 成本分析 */
  costAnalysis: {
    /** 实际总花费 */
    totalCostUsd: number;
    /** 各层花费明细 */
    costByLayer: Record<string, number>;
    /** 浪费点标注 */
    wastePoints: string[];
    /** 优化建议 */
    optimizationHints: string[];
  };
  /** 自定义指标 */
  metrics: Record<string, unknown>;
}

// ─── Adapter 接口 ───────────────────────────────────

/** LLM 适配器 - OpenAI-compatible 接口 */
export interface LLMAdapter {
  /** 调用 LLM 生成文本 */
  chat(request: LLMChatRequest): Promise<LLMChatResponse>;
  /** 获取可用模型列表 */
  listModels(): Promise<string[]>;
}

export interface LLMChatRequest {
  /** 模型标识 */
  model: string;
  /** 消息列表 */
  messages: LLMMessage[];
  /** 温度参数 */
  temperature?: number;
  /** 最大输出 token */
  maxTokens?: number;
  /** 结构化输出的 JSON Schema */
  responseFormat?: { type: 'json_object' | 'text' };
}

export interface LLMMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface LLMChatResponse {
  /** 生成的文本内容 */
  content: string;
  /** 使用的模型 */
  model: string;
  /** token 用量 */
  usage: {
    inputTokens: number;
    outputTokens: number;
  };
  /** 完成原因 */
  finishReason: 'stop' | 'length' | 'error';
}

/** 存储适配器 - 持久化接口 */
export interface StorageAdapter {
  /** 保存会话 */
  saveSession(session: SessionRecord): Promise<void>;
  /** 获取会话 */
  getSession(sessionId: string): Promise<SessionRecord | null>;
  /** 更新会话状态 */
  updateSessionStatus(sessionId: string, status: string): Promise<void>;
  /** 保存决策记录 */
  saveDecision(decision: DecisionRecord): Promise<number>;
  /** 保存评估记录 */
  saveEvaluation(evaluation: EvaluationRecord): Promise<void>;
  /** 保存成本事件 */
  saveCostEvent(event: CostEventRecord): Promise<void>;
  /** 查询会话的所有成本事件 */
  getCostEvents(sessionId: string): Promise<CostEventRecord[]>;
}

// ─── 数据库记录类型 ─────────────────────────────────

export interface SessionRecord {
  sessionId: string;
  userId: string;
  productId: string;
  goalJson: string;
  budgetJson?: string;
  status: 'active' | 'completed' | 'exceeded';
  createdAt: number;
}

export interface DecisionRecord {
  sessionId: string;
  actionType: string;
  decisionJson: string;
  modelUsed?: string;
  inputTokens?: number;
  outputTokens?: number;
  costUsd?: number;
  latencyMs?: number;
  createdAt: number;
}

export interface EvaluationRecord {
  decisionId: number;
  qualityScore?: number;
  userAccepted?: boolean;
  userFeedback?: string;
  metricsJson?: string;
  createdAt: number;
}

export interface CostEventRecord {
  sessionId: string;
  layer: string;
  eventType: string;
  tokensUsed?: number;
  costUsd?: number;
  metadataJson?: string;
  createdAt: number;
}

// ─── CostTracker 接口 ──────────────────────────────

/** 成本追踪器接口（供 ExecutionContext 使用） */
export interface CostTracker {
  /** 记录一次 token 消耗 */
  track(event: {
    layer: string;
    eventType: string;
    tokensUsed: number;
    costUsd: number;
    metadata?: Record<string, unknown>;
  }): void;
  /** 获取当前会话累计 token 数 */
  getTotalTokens(): number;
  /** 获取当前会话累计花费 */
  getTotalCostUsd(): number;
  /** 检查是否超预算 */
  isBudgetExceeded(): boolean;
}

// ─── AgentConfig - 开发者传入的配置 ─────────────────

export interface AgentConfig {
  /** 产品标识 */
  productId: string;
  /** 注册的 Skill 列表 */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- 接受任意泛型参数的 Skill
  skills: SkillDefinition<any, any>[];
  /** 注册的 Recipe 列表 */
  recipes: RecipeDefinition[];
  /** 决策维度权重 */
  decisionWeights: DimensionScores;
  /** 存储适配器 */
  storage: StorageAdapter;
  /** LLM 适配器 */
  llm: LLMAdapter;
  /** 预算配置 */
  budget?: BudgetConfig;
}

// ─── Event 类型 ─────────────────────────────────────

/** 框架事件类型定义 */
export interface ValerisEvents {
  'session:created': { sessionId: string; userId: string };
  'session:completed': { sessionId: string };
  'goal:parsed': { sessionId: string; goal: Goal };
  'plan:created': { sessionId: string; plan: ExecutionPlan };
  'decision:made': { sessionId: string; result: DecisionResult };
  'skill:start': { sessionId: string; skillName: string };
  'skill:complete': { sessionId: string; skillName: string; latencyMs: number };
  'skill:error': { sessionId: string; skillName: string; error: string };
  'cost:tracked': { sessionId: string; layer: string; costUsd: number };
  'budget:warning': { sessionId: string; usage: number; limit: number };
  'budget:exceeded': { sessionId: string; strategy: BudgetExceededStrategy };
}
