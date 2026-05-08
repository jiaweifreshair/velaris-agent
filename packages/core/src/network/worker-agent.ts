/**
 * Worker Agent - 增强的子 Agent 隔离
 * 参考 Claude Code 的 Sub-Agent 隔离机制：
 * - 独立 Context 预算
 * - 执行完毕只返回摘要（不污染主 Agent Context）
 * - 支持 TAOR 循环（Think-Act-Observe-Repeat）
 */

import type {
  ExecutionContext,
  CostEstimate,
  LLMAdapter,
  LLMMessage,
  Goal,
} from '../types.js';
import type { EventBus } from './event-bus.js';
import { generateId } from '@velaris/shared';
import { AutoCompaction } from '../cost/auto-compaction.js';
import { ContextCompressor } from '../cost/compressor.js';

/** Worker Agent 状态 */
export type WorkerStatus =
  | 'pending'
  | 'thinking'
  | 'acting'
  | 'observing'
  | 'completed'
  | 'failed';

/** TAOR 循环阶段 */
export type TAORPhase = 'think' | 'act' | 'observe';

/** Worker Agent 配置 */
export interface WorkerConfig {
  /** Worker 名称 */
  name: string;
  /** 独立 Context 预算（token 数） */
  contextBudget: number;
  /** 最大 TAOR 循环次数 */
  maxTaorCycles: number;
  /** 是否返回完整输出（默认只返回摘要） */
  returnFullOutput: boolean;
  /** 摘要最大 token 数 */
  summaryMaxTokens: number;
  /** 压缩阈值 */
  compactionThreshold: number;
}

const DEFAULT_WORKER_CONFIG: WorkerConfig = {
  name: 'worker',
  contextBudget: 100_000,
  maxTaorCycles: 10,
  returnFullOutput: false,
  summaryMaxTokens: 2000,
  compactionThreshold: 0.5,
};

/** TAOR 循环结果 */
export interface TAORCycleResult {
  /** 循环序号 */
  cycle: number;
  /** 思考内容 */
  thought: string;
  /** 执行的动作 */
  action: WorkerAction;
  /** 观察结果 */
  observation: string;
  /** 是否完成 */
  isComplete: boolean;
  /** 消耗的 token */
  tokensUsed: number;
}

/** Worker 动作 */
export interface WorkerAction {
  /** 动作类型 */
  type: string;
  /** 动作参数 */
  params: Record<string, unknown>;
  /** 执行结果 */
  result?: unknown;
  /** 是否成功 */
  success: boolean;
  /** 错误信息 */
  error?: string;
}

/** Worker Agent 执行结果 */
export interface WorkerResult {
  /** Worker ID */
  workerId: string;
  /** Worker 名称 */
  name: string;
  /** 摘要（默认返回） */
  summary: string;
  /** 完整输出（可选） */
  fullOutput?: unknown;
  /** TAOR 循环历史 */
  taorHistory: TAORCycleResult[];
  /** 成本 */
  cost: CostEstimate;
  /** 耗时 */
  latencyMs: number;
  /** 是否成功 */
  success: boolean;
  /** 错误信息 */
  error?: string;
  /** Context 使用情况 */
  contextUsage: {
    used: number;
    budget: number;
    percentage: number;
  };
}

/**
 * Worker Agent
 * 独立的子 Agent，拥有独立的 Context 预算
 */
export class WorkerAgent {
  readonly id: string;
  readonly name: string;
  private readonly config: WorkerConfig;
  private readonly llm: LLMAdapter;
  private readonly model: string;

  private _status: WorkerStatus = 'pending';
  private contextMessages: LLMMessage[] = [];
  private contextTokens = 0;
  private taorCycle = 0;
  private taorHistory: TAORCycleResult[] = [];
  private autoCompaction: AutoCompaction;

  constructor(
    config: Partial<WorkerConfig> & { name: string },
    llm: LLMAdapter,
    model: string,
    eventBus?: EventBus
  ) {
    this.id = generateId('worker');
    this.config = { ...DEFAULT_WORKER_CONFIG, ...config };
    this.name = this.config.name;
    this.llm = llm;
    this.model = model;

    this.autoCompaction = new AutoCompaction({
      sessionId: this.id,
      llm,
      model,
      threshold: this.config.compactionThreshold,
      eventBus,
    });
  }

  get status(): WorkerStatus {
    return this._status;
  }

  /**
   * 执行任务
   * @param goal 目标
   * @param context 父 Agent 传递的上下文（只读）
   */
  async execute(
    goal: Goal,
    context?: ExecutionContext
  ): Promise<WorkerResult> {
    const start = Date.now();
    this._status = 'thinking';

    try {
      // 初始化 context（独立预算）
      await this.initializeContext(goal, context);

      // TAOR 循环
      let isComplete = false;
      while (!isComplete && this.taorCycle < this.config.maxTaorCycles) {
        const cycleResult = await this.runTAORCycle();
        this.taorHistory.push(cycleResult);
        this.taorCycle++;

        isComplete = cycleResult.isComplete;

        // 检查 context 预算
        if (this.contextTokens >= this.config.contextBudget) {
          // 触发压缩
          const compressed = await this.autoCompaction.compact(
            this.contextMessages,
            this.config.contextBudget
          );
          this.contextMessages = compressed.messages;
          this.contextTokens = compressed.compressedTokens;
        }
      }

      // 生成摘要
      const summary = await this.generateSummary();

      this._status = 'completed';

      return {
        workerId: this.id,
        name: this.name,
        summary,
        fullOutput: this.config.returnFullOutput
          ? this.taorHistory
          : undefined,
        taorHistory: this.taorHistory,
        cost: this.calculateCost(),
        latencyMs: Date.now() - start,
        success: true,
        contextUsage: {
          used: this.contextTokens,
          budget: this.config.contextBudget,
          percentage: this.contextTokens / this.config.contextBudget,
        },
      };
    } catch (err) {
      this._status = 'failed';
      return {
        workerId: this.id,
        name: this.name,
        summary: `Worker failed: ${err instanceof Error ? err.message : String(err)}`,
        taorHistory: this.taorHistory,
        cost: this.calculateCost(),
        latencyMs: Date.now() - start,
        success: false,
        error: err instanceof Error ? err.message : String(err),
        contextUsage: {
          used: this.contextTokens,
          budget: this.config.contextBudget,
          percentage: this.contextTokens / this.config.contextBudget,
        },
      };
    }
  }

  /**
   * 初始化独立 Context
   */
  private async initializeContext(
    goal: Goal,
    parentContext?: ExecutionContext
  ): Promise<void> {
    // 系统提示词
    const systemPrompt = this.buildSystemPrompt(goal);

    this.contextMessages = [
      { role: 'system', content: systemPrompt },
      {
        role: 'user',
        content: `Goal: ${goal.intent}\n\nConstraints: ${JSON.stringify(goal.constraints, null, 2)}`,
      },
    ];

    // 如果有父 Agent 上下文，添加相关上下文（只读）
    if (parentContext) {
      const parentContextSummary = `Parent session: ${parentContext.sessionId}\nPrevious outputs: ${JSON.stringify(Object.keys(parentContext.previousOutputs))}`;
      this.contextMessages.push({
        role: 'system',
        content: `[Parent Context - Read Only]\n${parentContextSummary}`,
      });
    }

    this.contextTokens = ContextCompressor.estimateMessagesTokens(
      this.contextMessages
    );
  }

  /**
   * 构建系统提示词
   */
  private buildSystemPrompt(goal: Goal): string {
    return `You are ${this.name}, a specialized worker agent.

Your goal: ${goal.intent}

You operate with an independent context budget of ${this.config.contextBudget} tokens.
Work autonomously using Think-Act-Observe-Repeat cycles.

When complete, provide a concise summary of your work.
Do not include verbose details - only key findings and results.`;
  }

  /**
   * 执行一次 TAOR 循环
   */
  private async runTAORCycle(): Promise<TAORCycleResult> {
    // Think
    this._status = 'thinking';
    const thought = await this.think();

    // Act
    this._status = 'acting';
    const action = await this.act(thought);

    // Observe
    this._status = 'observing';
    const observation = await this.observe(action);

    // 检查是否完成
    const isComplete = this.checkCompletion(observation);

    return {
      cycle: this.taorCycle,
      thought,
      action,
      observation,
      isComplete,
      tokensUsed: this.contextTokens,
    };
  }

  /**
   * Think 阶段
   */
  private async think(): Promise<string> {
    const response = await this.llm.chat({
      model: this.model,
      messages: [
        ...this.contextMessages,
        {
          role: 'user',
          content: 'THINK: What should I do next? Analyze the current state and plan the next action.',
        },
      ],
      maxTokens: 1000,
    });

    this.addToContext({
      role: 'assistant',
      content: `[THINK] ${response.content}`,
    });

    return response.content;
  }

  /**
   * Act 阶段
   */
  private async act(thought: string): Promise<WorkerAction> {
    const response = await this.llm.chat({
      model: this.model,
      messages: [
        ...this.contextMessages,
        {
          role: 'user',
          content: `ACT: Based on your thought "${thought.slice(0, 200)}...", what action will you take? Respond with JSON: { "type": "...", "params": {...} }`,
        },
      ],
      maxTokens: 500,
      responseFormat: { type: 'json_object' },
    });

    let action: WorkerAction;
    try {
      const parsed = JSON.parse(response.content);
      action = {
        type: parsed.type ?? 'unknown',
        params: parsed.params ?? {},
        success: true,
      };
    } catch {
      action = {
        type: 'parse_error',
        params: {},
        success: false,
        error: 'Failed to parse action JSON',
      };
    }

    // 执行动作（简化版，实际应调用工具）
    action.result = { executed: true };
    action.success = true;

    this.addToContext({
      role: 'assistant',
      content: `[ACT] ${JSON.stringify(action)}`,
    });

    return action;
  }

  /**
   * Observe 阶段
   */
  private async observe(action: WorkerAction): Promise<string> {
    const observation = `Action ${action.type} ${action.success ? 'succeeded' : 'failed'}. Result: ${JSON.stringify(action.result)}`;

    this.addToContext({
      role: 'user',
      content: `[OBSERVE] ${observation}`,
    });

    return observation;
  }

  /**
   * 检查是否完成
   */
  private checkCompletion(observation: string): boolean {
    // 简单检查：包含完成关键词
    const completionKeywords = ['done', 'complete', 'finished', 'success'];
    const lower = observation.toLowerCase();
    return completionKeywords.some((k) => lower.includes(k));
  }

  /**
   * 生成摘要
   */
  private async generateSummary(): Promise<string> {
    // 如果历史很短，直接拼接
    if (this.taorHistory.length <= 3) {
      return this.taorHistory
        .map((c) => `Cycle ${c.cycle}: ${c.thought.slice(0, 100)}...`)
        .join('\n');
    }

    // 使用 LLM 生成摘要
    const historyText = this.taorHistory
      .map((c) => `Cycle ${c.cycle}:\n  Thought: ${c.thought}\n  Action: ${c.action.type}\n  Result: ${c.observation}`)
      .join('\n\n');

    const response = await this.llm.chat({
      model: this.model,
      messages: [
        {
          role: 'system',
          content: 'Summarize the worker agent\'s work concisely. Focus on key results and findings.',
        },
        { role: 'user', content: historyText },
      ],
      maxTokens: this.config.summaryMaxTokens,
    });

    return response.content;
  }

  /**
   * 添加消息到 context
   */
  private addToContext(message: LLMMessage): void {
    this.contextMessages.push(message);
    this.contextTokens += ContextCompressor.estimateTokens(message.content) + 4;
  }

  /**
   * 计算成本
   */
  private calculateCost(): CostEstimate {
    // 简化：假设每个 token $0.00001
    const totalTokens = this.contextTokens;
    return {
      inputTokens: Math.floor(totalTokens * 0.7),
      outputTokens: Math.floor(totalTokens * 0.3),
      totalUsd: totalTokens * 0.00001,
      model: this.model,
    };
  }

  /**
   * 获取 context 使用情况
   */
  getContextUsage(): { used: number; budget: number; percentage: number } {
    return {
      used: this.contextTokens,
      budget: this.config.contextBudget,
      percentage: this.contextTokens / this.config.contextBudget,
    };
  }
}

/**
 * Worker Agent 池
 * 管理多个 Worker Agent 的并行执行
 */
export class WorkerPool {
  private readonly workers: Map<string, WorkerAgent> = new Map();
  private readonly llm: LLMAdapter;
  private readonly model: string;
  private readonly eventBus?: EventBus;

  constructor(llm: LLMAdapter, model: string, eventBus?: EventBus) {
    this.llm = llm;
    this.model = model;
    this.eventBus = eventBus;
  }

  /**
   * 创建 Worker
   */
  createWorker(config: Partial<WorkerConfig> & { name: string }): WorkerAgent {
    const worker = new WorkerAgent(config, this.llm, this.model, this.eventBus);
    this.workers.set(worker.id, worker);
    return worker;
  }

  /**
   * 并行执行多个 Worker
   */
  async executeParallel(
    goals: Goal[],
    config: Partial<WorkerConfig> & { name: string }
  ): Promise<WorkerResult[]> {
    const workers = goals.map((_goal, i) =>
      this.createWorker({ ...config, name: `${config.name}_${i}` })
    );

    const promises = workers.map((worker, i) => worker.execute(goals[i]!));
    const results = await Promise.all(promises);

    // 清理
    for (const worker of workers) {
      this.workers.delete(worker.id);
    }

    return results;
  }

  /**
   * 获取活跃 Worker 数
   */
  get activeCount(): number {
    return this.workers.size;
  }

  /**
   * 获取所有 Worker
   */
  getWorkers(): WorkerAgent[] {
    return [...this.workers.values()];
  }
}
