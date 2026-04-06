/**
 * 任务账本（OpenHarness 二开版）
 * 作用：记录任务生命周期，支撑审计与回放。
 */

import { generateId, now } from '@velaris/shared';
import type { RuntimeTarget, TaskLedgerRecord, TaskStatus } from '../types.js';

/** 创建任务入参。 */
export interface CreateTaskInput {
  /** 会话 ID。 */
  sessionId: string;
  /** 运行时。 */
  runtime: RuntimeTarget;
  /** 角色。 */
  role: string;
  /** 任务目标。 */
  objective: string;
  /** 上游依赖。 */
  dependsOn?: string[];
}

/**
 * 任务账本服务：内存实现，后续可替换为数据库。
 */
export class TaskLedger {
  private readonly tasks = new Map<string, TaskLedgerRecord>();

  /**
   * 新建任务。
   * 为什么这样做：每个执行步骤都变成可追踪实体，失败时可以精确定位。
   */
  createTask(input: CreateTaskInput): TaskLedgerRecord {
    const timestamp = now();
    const task: TaskLedgerRecord = {
      taskId: generateId('task'),
      sessionId: input.sessionId,
      runtime: input.runtime,
      role: input.role,
      objective: input.objective,
      status: 'queued',
      dependsOn: input.dependsOn ?? [],
      createdAt: timestamp,
      updatedAt: timestamp,
    };
    this.tasks.set(task.taskId, task);
    return task;
  }

  /**
   * 更新任务状态。
   * 为什么这样做：将状态迁移与错误信息绑定，形成完整的执行轨迹。
   */
  updateStatus(taskId: string, status: TaskStatus, error?: string): TaskLedgerRecord | null {
    const task = this.tasks.get(taskId);
    if (!task) return null;

    const updated: TaskLedgerRecord = {
      ...task,
      status,
      updatedAt: now(),
      error,
    };
    this.tasks.set(taskId, updated);
    return updated;
  }

  /**
   * 查询单任务。
   */
  getTask(taskId: string): TaskLedgerRecord | null {
    return this.tasks.get(taskId) ?? null;
  }

  /**
   * 按会话查询任务列表。
   */
  listBySession(sessionId: string): TaskLedgerRecord[] {
    return [...this.tasks.values()].filter((task) => task.sessionId === sessionId);
  }
}
