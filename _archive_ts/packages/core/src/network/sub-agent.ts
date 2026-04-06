/**
 * SubAgent - 子 Agent 定义与生命周期管理
 * 由主 Agent spawn 出来执行并行任务
 */

import type { ExecutionContext, CostEstimate } from '../types.js';
import { generateId } from '@velaris/shared';

/** SubAgent 任务定义 */
export interface SubAgentTask {
  /** 任务标识 */
  taskId: string;
  /** 子 Agent 名称 */
  agentName: string;
  /** 执行参数 */
  params: Record<string, unknown>;
}

/** SubAgent 执行结果 */
export interface SubAgentResult {
  /** 任务标识 */
  taskId: string;
  /** 子 Agent 名称 */
  agentName: string;
  /** 输出数据 */
  output: unknown;
  /** 成本 */
  cost: CostEstimate;
  /** 耗时 */
  latencyMs: number;
  /** 是否成功 */
  success: boolean;
  /** 错误信息 */
  error?: string;
}

/**
 * SubAgent 实例
 * 封装一个子任务的执行生命周期
 */
export class SubAgent {
  readonly id: string;
  readonly name: string;
  private _status: 'pending' | 'running' | 'completed' | 'failed' = 'pending';

  constructor(
    name: string,
    private readonly task: Record<string, unknown>,
    private readonly executeFn: (
      input: Record<string, unknown>,
      ctx: ExecutionContext,
    ) => Promise<unknown>,
  ) {
    this.id = generateId('sub');
    this.name = name;
  }

  get status(): string {
    return this._status;
  }

  /** 执行子 Agent 任务 */
  async execute(ctx: ExecutionContext): Promise<SubAgentResult> {
    this._status = 'running';
    const start = Date.now();

    try {
      const output = await this.executeFn(this.task, ctx);
      this._status = 'completed';

      return {
        taskId: this.id,
        agentName: this.name,
        output,
        cost: { inputTokens: 0, outputTokens: 0, totalUsd: 0, model: '' },
        latencyMs: Date.now() - start,
        success: true,
      };
    } catch (err) {
      this._status = 'failed';
      return {
        taskId: this.id,
        agentName: this.name,
        output: null,
        cost: { inputTokens: 0, outputTokens: 0, totalUsd: 0, model: '' },
        latencyMs: Date.now() - start,
        success: false,
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }
}
