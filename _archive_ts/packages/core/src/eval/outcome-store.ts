/**
 * Outcome 结果存储（OpenHarness 二开版）
 * 作用：沉淀每次执行结果，为后续策略优化与回放提供基础数据。
 */

import { now } from '@velaris/shared';
import type { OutcomeRecord } from '../types.js';

/**
 * Outcome 存储：当前为内存版，便于本地开发和单测。
 */
export class OutcomeStore {
  private readonly records: OutcomeRecord[] = [];

  /**
   * 记录一次执行 outcome。
   * 为什么这样做：把评估指标结构化沉淀，便于后续做策略学习和趋势统计。
   */
  record(input: Omit<OutcomeRecord, 'createdAt'>): OutcomeRecord {
    const record: OutcomeRecord = {
      ...input,
      createdAt: now(),
    };
    this.records.push(record);
    return record;
  }

  /**
   * 查询会话历史 outcome。
   */
  listBySession(sessionId: string): OutcomeRecord[] {
    return this.records.filter((item) => item.sessionId === sessionId);
  }
}
