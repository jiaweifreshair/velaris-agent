/**
 * Velaris Agent 核心类型定义
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
  /** 可选：策略路由结果（OpenHarness 二开治理链路） */
  routing?: RoutingDecision;
  /** 可选：能力签发计划（最小权限令牌） */
  authorityPlan?: AuthorityPlan;
}

// ─── 路由治理（OpenHarness 二开）───────────────────────

/** 风险等级，用于策略路由。 */
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

/** 任务复杂度，供路由规则匹配。 */
export type TaskComplexity = 'simple' | 'medium' | 'complex';

/** 路由目标运行时。 */
export type RuntimeTarget = 'self' | 'openclaw' | 'claude_code' | 'mixed';

/** 路由模式。 */
export type RouteMode = 'local' | 'delegated' | 'hybrid';

/** 自治等级，与执行风险策略联动。 */
export type AutonomyLevel = 'supervised' | 'plan' | 'auto' | 'accept_edits' | 'bypass';

/** 停止条件命中后的动作。 */
export type StopAction = 'stop' | 'degrade' | 'retry' | 'escalate';

/** 路由规则支持的比较操作符。 */
export type PolicyOperator = 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'in' | 'not_in';

/** 路由上下文中的预算快照。 */
export interface RoutingBudgets {
  /** 剩余 token 预算。 */
  remainingTokens: number;
  /** 剩余美元预算。 */
  remainingCostUsd: number;
  /** 剩余时延预算（毫秒）。 */
  remainingLatencyMs: number;
}

/** 路由上下文中的能力需求。 */
export interface CapabilityDemand {
  /** 是否需要读取代码或文件。 */
  readCode: boolean;
  /** 是否需要写代码或配置。 */
  writeCode: boolean;
  /** 是否需要执行命令。 */
  execCommand: boolean;
  /** 是否需要访问网络。 */
  networkAccess: boolean;
  /** 是否有外部副作用（通知/落库/调用外部系统）。 */
  externalSideEffects: boolean;
}

/** 路由上下文中的治理要求。 */
export interface GovernanceDemand {
  /** 是否要求完整审计链路。 */
  requiresAuditTrail: boolean;
  /** 审批模式。 */
  approvalMode: 'none' | 'ask' | 'strict';
}

/** 路由上下文中的运行状态。 */
export interface RoutingState {
  /** 任务复杂度标签。 */
  taskComplexity: TaskComplexity;
  /** 证据是否冲突。 */
  evidenceConflict: boolean;
  /** 工具健康状态。 */
  toolHealth: 'healthy' | 'degraded' | 'unhealthy';
}

/** 路由输入上下文。 */
export interface RoutingContext {
  /** 请求唯一标识。 */
  requestId: string;
  /** 请求时间戳。 */
  timestamp: string;
  /** 目标对象。 */
  goal: Goal;
  /** 风险信息。 */
  risk: { level: RiskLevel; score?: number };
  /** 运行状态。 */
  state: RoutingState;
  /** 预算快照。 */
  budgets: RoutingBudgets;
  /** 能力需求。 */
  capabilityDemand: CapabilityDemand;
  /** 治理需求。 */
  governance: GovernanceDemand;
  /** 当前可用运行时。 */
  availableRuntimes: RuntimeTarget[];
}

/** 路由规则中的叶子条件。 */
export interface PolicyLeafCondition {
  /** 字段路径，支持点号访问，例如 risk.level。 */
  field: string;
  /** 比较操作符。 */
  op: PolicyOperator;
  /** 比较值。 */
  value: unknown;
}

/** 路由规则中的组合条件。 */
export interface PolicyConditionGroup {
  /** 所有子条件都为真时命中。 */
  all?: PolicyCondition[];
  /** 任意子条件为真时命中。 */
  any?: PolicyCondition[];
}

/** 路由规则条件（组合条件或叶子条件）。 */
export type PolicyCondition = PolicyLeafCondition | PolicyConditionGroup;

/** 停止策略画像定义。 */
export interface StopProfileDefinition {
  /** 画像说明。 */
  description: string;
  /** 条件命中后的动作。 */
  onMatch: StopAction;
  /** 启用的停止条件 ID。 */
  conditionIds: string[];
  /** 最大重试次数。 */
  maxRetries?: number;
  /** 升级目标。 */
  escalateTo?: 'human' | 'policy_engine' | 'none';
}

/** 路由策略定义。 */
export interface RoutingStrategy {
  /** 路由模式。 */
  mode: RouteMode;
  /** 目标运行时。 */
  runtime: RuntimeTarget;
  /** 自治等级。 */
  autonomy: AutonomyLevel;
  /** 允许并行 worker 数。 */
  maxParallelWorkers: number;
  /** 该策略要求的能力集合。 */
  requiredCapabilities: string[];
}

/** 命中规则后的路由目标。 */
export interface RuleRouteTarget {
  /** 目标策略名。 */
  strategy: string;
  /** 停止画像名。 */
  stopProfile: string;
  /** 命中原因。 */
  reason: string;
}

/** 路由规则定义。 */
export interface RoutingRule {
  /** 规则 ID。 */
  id: string;
  /** 优先级，越大越先匹配。 */
  priority: number;
  /** 匹配条件。 */
  when: PolicyCondition;
  /** 命中路由结果。 */
  route: RuleRouteTarget;
}

/** 路由策略配置。 */
export interface RoutingPolicy {
  /** 策略版本。 */
  version: number;
  /** 策略 ID。 */
  policyId: string;
  /** 默认策略。 */
  defaults: RuleRouteTarget;
  /** 停止画像集合。 */
  stopProfiles: Record<string, StopProfileDefinition>;
  /** 策略定义集合。 */
  strategies: Record<string, RoutingStrategy>;
  /** 规则列表。 */
  rules: RoutingRule[];
  /** 回退策略。 */
  fallback: RuleRouteTarget;
}

/** 路由决策结果。 */
export interface RoutingDecision {
  /** 命中的策略名。 */
  selectedStrategy: string;
  /** 选中的路由详情。 */
  selectedRoute: {
    /** 路由模式。 */
    mode: RouteMode;
    /** 目标运行时。 */
    runtime: RuntimeTarget;
    /** 自治等级。 */
    autonomy: AutonomyLevel;
    /** 路由置信度（0-1）。 */
    score: number;
  };
  /** 命中的停止画像。 */
  stopProfile: string;
  /** 当前激活的停止条件。 */
  activeStopConditions: string[];
  /** 原因码集合。 */
  reasonCodes: string[];
  /** 该次路由要求的能力。 */
  requiredCapabilities: string[];
  /** 规则追踪信息。 */
  trace: {
    /** 参与评估的规则列表。 */
    evaluatedRules: string[];
    /** 最终命中的规则 ID。 */
    selectedRule: string;
    /** 决策时间。 */
    timestamp: string;
  };
}

/** 能力令牌定义。 */
export interface CapabilityToken {
  /** 令牌 ID。 */
  tokenId: string;
  /** 令牌作用域。 */
  scope: string[];
  /** 令牌 TTL（秒）。 */
  ttlSeconds: number;
  /** 签发时间。 */
  issuedAt: number;
}

/** 授权计划定义。 */
export interface AuthorityPlan {
  /** 是否需要审批。 */
  approvalsRequired: boolean;
  /** 本次执行所需能力。 */
  requiredCapabilities: string[];
  /** 签发的能力令牌。 */
  capabilityTokens: CapabilityToken[];
}

/** 任务状态。 */
export type TaskStatus =
  | 'queued'
  | 'running'
  | 'blocked'
  | 'retrying'
  | 'completed'
  | 'canceled'
  | 'failed';

/** 任务账本记录。 */
export interface TaskLedgerRecord {
  /** 任务 ID。 */
  taskId: string;
  /** 会话 ID。 */
  sessionId: string;
  /** 运行时。 */
  runtime: RuntimeTarget;
  /** 任务角色。 */
  role: string;
  /** 任务目标。 */
  objective: string;
  /** 当前状态。 */
  status: TaskStatus;
  /** 上游依赖。 */
  dependsOn: string[];
  /** 创建时间。 */
  createdAt: number;
  /** 更新时间。 */
  updatedAt: number;
  /** 失败原因（可选）。 */
  error?: string;
}

/** Outcome 回写记录。 */
export interface OutcomeRecord {
  /** 会话 ID。 */
  sessionId: string;
  /** 决策策略。 */
  selectedStrategy: string;
  /** 质量分。 */
  qualityScore: number;
  /** 总成本。 */
  totalCostUsd: number;
  /** 总耗时。 */
  totalLatencyMs: number;
  /** 执行是否成功。 */
  success: boolean;
  /** 时间戳。 */
  createdAt: number;
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
  logger: import('@velaris/shared').Logger;
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
  /** 可选：OpenHarness 风格路由策略配置 */
  routingPolicy?: RoutingPolicy;
  /** 可选：能力签发参数 */
  authorityConfig?: {
    /** 默认令牌 TTL（秒）。 */
    defaultTokenTtlSeconds?: number;
    /** 触发 ask 模式审批的能力名单。 */
    approvalSensitiveCapabilities?: string[];
  };
}

// ─── Event 类型 ─────────────────────────────────────

/** 框架事件类型定义 */
export interface VelarisEvents {
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
