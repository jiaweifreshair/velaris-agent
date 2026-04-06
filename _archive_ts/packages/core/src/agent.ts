/**
 * VelarisAgent - 六层编排主体
 * 串联 L0-L5 层，提供统一的 Session API
 */

import type {
  AgentConfig,
  Goal,
  DecisionResult,
  ExecutionResult,
  Evaluation,
  ExecutionContext,
  RoutingContext,
  RoutingDecision,
  GovernanceDemand,
  CapabilityDemand,
  TaskComplexity,
  RiskLevel,
  AuthorityPlan,
} from './types.js';
import { GoalParser } from './layers/goal-parser.js';
import { Planner } from './layers/planner.js';
import { DecisionCore } from './layers/decision-core.js';
import type { Candidate } from './layers/decision-core.js';
import { Executor } from './layers/executor.js';
import { Evaluator } from './layers/evaluator.js';
import { AgentNetwork } from './network/agent-network.js';
import { EventBus } from './network/event-bus.js';
import { SkillRegistry } from './skills/registry.js';
import { SessionCostTracker } from './cost/tracker.js';
import { BudgetManager } from './cost/budget.js';
import { createLogger, generateId } from '@velaris/shared';
import { PolicyRouter } from './policy/router.js';
import { defaultRoutingPolicy } from './policy/default-routing-policy.js';
import { AuthorityService } from './governance/authority.js';
import { TaskLedger } from './control/task-ledger.js';
import { OutcomeStore } from './eval/outcome-store.js';

// 内置 Skill
import { callLlmSkill } from './skills/builtins/call-llm.js';
import { scoreOptionsSkill } from './skills/builtins/score-options.js';
import { compressContextSkill } from './skills/builtins/compress-context.js';
import { fetchDataSkill } from './skills/builtins/fetch-data.js';

/**
 * VelarisAgent 会话
 * 每次 createSession 创建一个独立会话，包含独立的成本追踪
 */
export class VelarisSession {
  readonly sessionId: string;
  private readonly costTracker: SessionCostTracker;
  private readonly goalParser: GoalParser;
  private readonly planner: Planner;
  private readonly decisionCore: DecisionCore;
  private readonly executor: Executor;
  private readonly evaluator: Evaluator;
  private readonly network: AgentNetwork;
  private readonly config: AgentConfig;
  private readonly logger: ReturnType<typeof createLogger>;
  private readonly router: PolicyRouter;
  private readonly authority: AuthorityService;
  private readonly taskLedger: TaskLedger;
  private readonly outcomeStore: OutcomeStore;

  constructor(
    userId: string,
    config: AgentConfig,
    network: AgentNetwork,
    registry: SkillRegistry,
    eventBus: EventBus,
    router: PolicyRouter,
    authority: AuthorityService,
    taskLedger: TaskLedger,
    outcomeStore: OutcomeStore,
  ) {
    this.sessionId = generateId('sess');
    this.config = config;

    // 创建会话级日志器
    this.logger = createLogger({ level: 'info', layer: 'session' });

    // 创建会话级成本追踪
    this.costTracker = new SessionCostTracker(
      this.sessionId,
      config.budget,
      config.storage,
      eventBus,
    );

    // 初始化各层
    this.goalParser = new GoalParser(config.llm, this.logger);
    this.planner = new Planner(registry, config.recipes, this.logger);
    this.decisionCore = new DecisionCore(config.decisionWeights, this.logger);
    this.executor = new Executor(
      registry,
      config.recipes,
      this.logger,
      new BudgetManager(config.budget),
    );
    this.evaluator = new Evaluator(config.storage, this.logger);
    this.network = network;
    this.router = router;
    this.authority = authority;
    this.taskLedger = taskLedger;
    this.outcomeStore = outcomeStore;

    // 保存会话到存储
    void config.storage.saveSession({
      sessionId: this.sessionId,
      userId,
      productId: config.productId,
      goalJson: '{}',
      budgetJson: config.budget ? JSON.stringify(config.budget) : undefined,
      status: 'active',
      createdAt: Date.now(),
    });

    // 发射会话创建事件
    eventBus.emit('session:created', { sessionId: this.sessionId, userId });
  }

  /**
   * 执行完整的六层决策流程
   * NL/Goal -> Parse -> Plan -> Decide -> Execute -> Evaluate
   */
  async run(input: string | Goal): Promise<{
    routing: RoutingDecision;
    authorityPlan: AuthorityPlan;
    decision: DecisionResult;
    execution: ExecutionResult;
    evaluation: Evaluation;
  }> {
    // L1: 目标解析
    const goal = typeof input === 'string'
      ? await this.goalParser.parseNaturalLanguage(
          input,
          'user',
          this.sessionId,
          this.config.recipes.map((r) => r.name),
        )
      : this.goalParser.parseStructured(input);

    // 更新会话的 goal
    void this.config.storage.saveSession({
      sessionId: this.sessionId,
      userId: goal.userId,
      productId: this.config.productId,
      goalJson: JSON.stringify(goal),
      budgetJson: this.config.budget ? JSON.stringify(this.config.budget) : undefined,
      status: 'active',
      createdAt: Date.now(),
    });

    // L2: 策略路由（OpenHarness 二开治理链路）
    const routingContext = this.buildRoutingContext(goal);
    const routing = this.router.route(routingContext);
    const authorityPlan = this.authority.issuePlan(
      routing.requiredCapabilities,
      routingContext.governance,
    );

    // L2.5: 创建任务账本根任务
    const rootTask = this.taskLedger.createTask({
      sessionId: this.sessionId,
      runtime: routing.selectedRoute.runtime,
      role: 'orchestrator',
      objective: goal.intent,
    });
    this.taskLedger.updateStatus(rootTask.taskId, 'running');

    // L3: 规划
    const plan = this.planner.plan(goal);

    // L4: 决策（生成候选方案并打分）
    const candidates = this.generateCandidates(plan, goal);
    const decision = this.decisionCore.decide(candidates, goal);
    decision.routing = routing;
    decision.authorityPlan = authorityPlan;

    // L5: 执行
    const planTasks = plan.steps.map((step) =>
      this.taskLedger.createTask({
        sessionId: this.sessionId,
        runtime: routing.selectedRoute.runtime,
        role: 'worker',
        objective: `执行技能 ${step.skillName}`,
        dependsOn: [rootTask.taskId],
      }),
    );

    const ctx = this.createContext(goal);
    let execution: ExecutionResult;
    try {
      execution = await this.executor.execute(plan, ctx);
    } catch (error) {
      for (const task of planTasks) {
        this.taskLedger.updateStatus(task.taskId, 'failed', error instanceof Error ? error.message : String(error));
      }
      this.taskLedger.updateStatus(
        rootTask.taskId,
        'failed',
        error instanceof Error ? error.message : String(error),
      );
      throw error;
    }

    for (let index = 0; index < planTasks.length; index++) {
      const task = planTasks[index]!;
      const stepResult = execution.stepResults[index];
      if (!stepResult) {
        this.taskLedger.updateStatus(task.taskId, 'blocked', '未返回步骤结果');
        continue;
      }
      this.taskLedger.updateStatus(
        task.taskId,
        stepResult.success ? 'completed' : 'failed',
        stepResult.error,
      );
    }

    // L6: 评估
    const evaluation = await this.evaluator.evaluate(decision, execution, this.costTracker);

    // 标记会话完成
    const status = this.costTracker.isBudgetExceeded() ? 'exceeded' : 'completed';
    void this.config.storage.updateSessionStatus(this.sessionId, status);
    this.taskLedger.updateStatus(
      rootTask.taskId,
      execution.stepResults.every((item) => item.success) ? 'completed' : 'failed',
    );

    // L7: Outcome 回写
    this.outcomeStore.record({
      sessionId: this.sessionId,
      selectedStrategy: routing.selectedStrategy,
      qualityScore: evaluation.qualityScore,
      totalCostUsd: evaluation.costAnalysis.totalCostUsd,
      totalLatencyMs: execution.totalLatencyMs,
      success: execution.stepResults.every((item) => item.success),
    });

    return { routing, authorityPlan, decision, execution, evaluation };
  }

  /** Spawn 子 Agent */
  spawn(agentName: string, params: Record<string, unknown>) {
    return this.network.spawn(agentName, params);
  }

  /** 并行执行多个子 Agent */
  async parallel(agents: ReturnType<typeof this.spawn>[]) {
    const ctx = this.createContext({
      goalType: 'parallel',
      userId: 'system',
      intent: 'parallel execution',
      constraints: {},
      sessionId: this.sessionId,
    });
    return this.network.parallel(agents, ctx);
  }

  /** 直接调用 Decision Core */
  decide(candidates: Candidate[], goal: Goal): DecisionResult {
    return this.decisionCore.decide(candidates, goal);
  }

  /** 获取成本摘要 */
  getCostSummary() {
    return this.costTracker.getSummary();
  }

  /** 获取当前会话任务账本。 */
  getTaskLedger() {
    return this.taskLedger.listBySession(this.sessionId);
  }

  /** 获取当前会话 outcome 历史。 */
  getOutcomes() {
    return this.outcomeStore.listBySession(this.sessionId);
  }

  /** 创建执行上下文 */
  private createContext(goal: Goal): ExecutionContext {
    return {
      sessionId: this.sessionId,
      goal,
      llm: this.config.llm,
      costTracker: this.costTracker,
      logger: this.logger,
      previousOutputs: {},
    };
  }

  /** 从执行计划生成候选方案 */
  private generateCandidates(
    _plan: { steps: Array<{ skillName: string }> },
    goal: Goal,
  ): Candidate[] {
    // 默认候选方案：按计划执行
    const planCandidate: Candidate = {
      actionType: 'execute_plan',
      params: { goalType: goal.goalType },
      rawScores: {
        quality: 0.8,
        cost: 0.6,
        speed: 0.7,
      },
    };

    // 快速方案：跳过部分步骤，更快但质量可能下降
    const fastCandidate: Candidate = {
      actionType: 'fast_execute',
      params: { goalType: goal.goalType, skipOptional: true },
      rawScores: {
        quality: 0.5,
        cost: 0.9,
        speed: 0.9,
      },
    };

    return [planCandidate, fastCandidate];
  }

  /** 构造策略路由输入。 */
  private buildRoutingContext(goal: Goal): RoutingContext {
    const capabilityDemand = this.inferCapabilityDemand(goal);
    const governance = this.inferGovernanceDemand(goal);
    return {
      requestId: generateId('req'),
      timestamp: new Date().toISOString(),
      goal,
      risk: {
        level: this.inferRiskLevel(goal, capabilityDemand, governance),
      },
      state: {
        taskComplexity: this.inferTaskComplexity(goal),
        evidenceConflict: false,
        toolHealth: 'healthy',
      },
      budgets: {
        remainingTokens: goal.budget?.maxTokens ?? 200_000,
        remainingCostUsd: goal.budget?.maxCostUsd ?? 10,
        remainingLatencyMs: goal.budget?.maxLatencyMs ?? 120_000,
      },
      capabilityDemand,
      governance,
      availableRuntimes: ['self', 'openclaw', 'claude_code', 'mixed'],
    };
  }

  /** 推断能力需求。 */
  private inferCapabilityDemand(goal: Goal): CapabilityDemand {
    const constraints = goal.constraints;
    return {
      readCode: this.readBooleanConstraint(constraints['readCode'], true),
      writeCode: this.readBooleanConstraint(
        constraints['writeCode'],
        goal.goalType.includes('code'),
      ),
      execCommand: this.readBooleanConstraint(
        constraints['execCommand'],
        goal.goalType.includes('deploy') || goal.goalType.includes('ops'),
      ),
      networkAccess: this.readBooleanConstraint(constraints['networkAccess'], true),
      externalSideEffects: this.readBooleanConstraint(
        constraints['externalSideEffects'],
        goal.goalType.includes('notify') || goal.goalType.includes('publish'),
      ),
    };
  }

  /** 推断治理需求。 */
  private inferGovernanceDemand(goal: Goal): GovernanceDemand {
    const constraints = goal.constraints;
    const approvalModeRaw = constraints['approvalMode'];
    const mode = approvalModeRaw === 'strict' || approvalModeRaw === 'ask' || approvalModeRaw === 'none'
      ? approvalModeRaw
      : 'none';
    return {
      requiresAuditTrail: this.readBooleanConstraint(constraints['requiresAuditTrail'], false),
      approvalMode: mode,
    };
  }

  /** 推断风险等级。 */
  private inferRiskLevel(
    goal: Goal,
    capabilityDemand: CapabilityDemand,
    governance: GovernanceDemand,
  ): RiskLevel {
    const level = goal.constraints['riskLevel'];
    if (level === 'critical' || level === 'high' || level === 'medium' || level === 'low') {
      return level;
    }
    if (governance.requiresAuditTrail || governance.approvalMode === 'strict') {
      return 'high';
    }
    if (capabilityDemand.externalSideEffects) {
      return 'medium';
    }
    return 'low';
  }

  /** 推断任务复杂度。 */
  private inferTaskComplexity(goal: Goal): TaskComplexity {
    const complexity = goal.constraints['taskComplexity'];
    if (complexity === 'simple' || complexity === 'medium' || complexity === 'complex') {
      return complexity;
    }
    const intentLength = goal.intent.length;
    if (intentLength >= 80) return 'complex';
    if (intentLength >= 30) return 'medium';
    return 'simple';
  }

  /** 读取布尔约束，失败时回退默认值。 */
  private readBooleanConstraint(value: unknown, fallback: boolean): boolean {
    return typeof value === 'boolean' ? value : fallback;
  }
}

/**
 * VelarisAgent 主类
 * 管理配置、Skill 注册、会话创建
 */
export class VelarisAgent {
  private readonly config: AgentConfig;
  private readonly registry: SkillRegistry;
  private readonly network: AgentNetwork;
  private readonly eventBus: EventBus;
  private readonly router: PolicyRouter;
  private readonly authority: AuthorityService;
  private readonly taskLedger: TaskLedger;
  private readonly outcomeStore: OutcomeStore;

  constructor(config: AgentConfig) {
    this.config = config;
    this.eventBus = new EventBus();
    this.network = new AgentNetwork(this.eventBus);
    this.router = new PolicyRouter(config.routingPolicy ?? defaultRoutingPolicy);
    this.authority = new AuthorityService({
      defaultTokenTtlSeconds: config.authorityConfig?.defaultTokenTtlSeconds,
      approvalSensitiveCapabilities: config.authorityConfig?.approvalSensitiveCapabilities,
    });
    this.taskLedger = new TaskLedger();
    this.outcomeStore = new OutcomeStore();

    // 初始化 Skill 注册表
    this.registry = new SkillRegistry();

    // 注册内置 Skill
    this.registry.register(callLlmSkill);
    this.registry.register(scoreOptionsSkill);
    this.registry.register(compressContextSkill);
    this.registry.register(fetchDataSkill);

    // 注册用户自定义 Skill
    this.registry.registerAll(config.skills);
  }

  /** 创建新会话 */
  createSession(userId: string): VelarisSession {
    return new VelarisSession(
      userId,
      this.config,
      this.network,
      this.registry,
      this.eventBus,
      this.router,
      this.authority,
      this.taskLedger,
      this.outcomeStore,
    );
  }

  /** 获取事件总线（用于监听框架事件） */
  getEventBus(): EventBus {
    return this.eventBus;
  }

  /** 获取 Agent 网络（用于注册 SubAgent） */
  getNetwork(): AgentNetwork {
    return this.network;
  }

  /** 获取 Skill 注册表 */
  getRegistry(): SkillRegistry {
    return this.registry;
  }
}
