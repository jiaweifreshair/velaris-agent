/**
 * 内存存储实现
 * 用于开发和测试，数据不持久化
 */

import type {
  StorageAdapter,
  SessionRecord,
  DecisionRecord,
  EvaluationRecord,
  CostEventRecord,
} from '../types.js';

/**
 * 基于 Map 的内存存储
 * 适用于测试和快速原型验证
 */
export class MemoryStorage implements StorageAdapter {
  private readonly sessions = new Map<string, SessionRecord>();
  private readonly decisions: DecisionRecord[] = [];
  private readonly evaluations: EvaluationRecord[] = [];
  private readonly costEvents: CostEventRecord[] = [];
  private decisionIdCounter = 0;

  async saveSession(session: SessionRecord): Promise<void> {
    this.sessions.set(session.sessionId, { ...session });
  }

  async getSession(sessionId: string): Promise<SessionRecord | null> {
    return this.sessions.get(sessionId) ?? null;
  }

  async updateSessionStatus(sessionId: string, status: string): Promise<void> {
    const session = this.sessions.get(sessionId);
    if (session) {
      session.status = status as SessionRecord['status'];
    }
  }

  async saveDecision(decision: DecisionRecord): Promise<number> {
    this.decisionIdCounter++;
    this.decisions.push({ ...decision });
    return this.decisionIdCounter;
  }

  async saveEvaluation(evaluation: EvaluationRecord): Promise<void> {
    this.evaluations.push({ ...evaluation });
  }

  async saveCostEvent(event: CostEventRecord): Promise<void> {
    this.costEvents.push({ ...event });
  }

  async getCostEvents(sessionId: string): Promise<CostEventRecord[]> {
    return this.costEvents.filter((e) => e.sessionId === sessionId);
  }

  // ─── 测试辅助方法 ──────────────────────────

  /** 获取所有决策记录（测试用） */
  getAllDecisions(): DecisionRecord[] {
    return [...this.decisions];
  }

  /** 获取所有评估记录（测试用） */
  getAllEvaluations(): EvaluationRecord[] {
    return [...this.evaluations];
  }

  /** 清空所有数据（测试用） */
  clear(): void {
    this.sessions.clear();
    this.decisions.length = 0;
    this.evaluations.length = 0;
    this.costEvents.length = 0;
    this.decisionIdCounter = 0;
  }
}
