/**
 * ValerisAgent - 六层编排主体
 * 串联 L0-L5 层，提供统一的 Session API
 */

import type {
  AgentConfig,
  Goal,
  DecisionResult,
  ExecutionResult,
  Evaluation,
  ExecutionContext,
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
import { createLogger, generateId } from '@valeris/shared';

// 内置 Skill
import { callLlmSkill } from './skills/builtins/call-llm.js';
import { scoreOptionsSkill } from './skills/builtins/score-options.js';
import { compressContextSkill } from './skills/builtins/compress-context.js';
import { fetchDataSkill } from './skills/builtins/fetch-data.js';

/**
 * ValerisAgent 会话
 * 每次 createSession 创建一个独立会话，包含独立的成本追踪
 */
export class ValerisSession {
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

  constructor(
    userId: string,
    config: AgentConfig,
    network: AgentNetwork,
    registry: SkillRegistry,
    eventBus: EventBus,
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

    // L2: 规划
    const plan = this.planner.plan(goal);

    // L3: 决策（生成候选方案并打分）
    const candidates = this.generateCandidates(plan, goal);
    const decision = this.decisionCore.decide(candidates, goal);

    // L4: 执行
    const ctx = this.createContext(goal);
    const execution = await this.executor.execute(plan, ctx);

    // L5: 评估
    const evaluation = await this.evaluator.evaluate(decision, execution, this.costTracker);

    // 标记会话完成
    const status = this.costTracker.isBudgetExceeded() ? 'exceeded' : 'completed';
    void this.config.storage.updateSessionStatus(this.sessionId, status);

    return { decision, execution, evaluation };
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
}

/**
 * ValerisAgent 主类
 * 管理配置、Skill 注册、会话创建
 */
export class ValerisAgent {
  private readonly config: AgentConfig;
  private readonly registry: SkillRegistry;
  private readonly network: AgentNetwork;
  private readonly eventBus: EventBus;

  constructor(config: AgentConfig) {
    this.config = config;
    this.eventBus = new EventBus();
    this.network = new AgentNetwork(this.eventBus);

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
  createSession(userId: string): ValerisSession {
    return new ValerisSession(userId, this.config, this.network, this.registry, this.eventBus);
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
