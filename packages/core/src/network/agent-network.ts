/**
 * L0 Agent Network - 主从编排层
 * 管理 SubAgent 的 spawn、并行执行和结果汇总
 */

import type { ExecutionContext } from '../types.js';
import { SubAgent } from './sub-agent.js';
import type { SubAgentResult } from './sub-agent.js';
import { EventBus } from './event-bus.js';

/** SubAgent 工厂函数类型 */
type SubAgentFactory = (
  input: Record<string, unknown>,
  ctx: ExecutionContext,
) => Promise<unknown>;

/**
 * Agent 网络管理器
 * 负责 SubAgent 的注册、spawn 和并行编排
 */
export class AgentNetwork {
  /** 已注册的 SubAgent 工厂 */
  private readonly factories = new Map<string, SubAgentFactory>();
  /** 当前活跃的 SubAgent 实例 */
  private readonly activeAgents = new Map<string, SubAgent>();
  /** 事件总线 */
  readonly eventBus: EventBus;

  constructor(eventBus?: EventBus) {
    this.eventBus = eventBus ?? new EventBus();
  }

  /** 注册 SubAgent 工厂函数 */
  registerAgent(name: string, factory: SubAgentFactory): void {
    this.factories.set(name, factory);
  }

  /** 创建（spawn）一个 SubAgent 实例 */
  spawn(name: string, params: Record<string, unknown>): SubAgent {
    const factory = this.factories.get(name);
    if (!factory) {
      throw new Error(`SubAgent factory not registered: ${name}`);
    }

    const agent = new SubAgent(name, params, factory);
    this.activeAgents.set(agent.id, agent);
    return agent;
  }

  /** 并行执行多个 SubAgent */
  async parallel(agents: SubAgent[], ctx: ExecutionContext): Promise<SubAgentResult[]> {
    const promises = agents.map((agent) => agent.execute(ctx));
    const results = await Promise.all(promises);

    // 清理已完成的 agent
    for (const agent of agents) {
      this.activeAgents.delete(agent.id);
    }

    return results;
  }

  /** 获取当前活跃的 SubAgent 数量 */
  get activeCount(): number {
    return this.activeAgents.size;
  }

  /** 获取已注册的 SubAgent 工厂名称 */
  listRegistered(): string[] {
    return [...this.factories.keys()];
  }
}
