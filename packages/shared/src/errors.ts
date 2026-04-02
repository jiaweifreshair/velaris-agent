/**
 * Valeris Agent 错误类型定义
 * 所有框架内部错误的基类和分类
 */

/** 框架错误基类 */
export class ValerisError extends Error {
  /** 错误代码，用于程序化错误处理 */
  readonly code: string;
  /** 产生错误的层级 */
  readonly layer?: string;
  /** 关联的会话 ID */
  readonly sessionId?: string;

  constructor(
    message: string,
    code: string,
    options?: { layer?: string; sessionId?: string; cause?: unknown },
  ) {
    super(message, { cause: options?.cause });
    this.name = 'ValerisError';
    this.code = code;
    this.layer = options?.layer;
    this.sessionId = options?.sessionId;
  }
}

/** 目标解析失败 */
export class GoalParseError extends ValerisError {
  constructor(message: string, options?: { sessionId?: string; cause?: unknown }) {
    super(message, 'GOAL_PARSE_ERROR', { layer: 'goal-parser', ...options });
    this.name = 'GoalParseError';
  }
}

/** 决策失败（无候选方案或全部被过滤） */
export class DecisionError extends ValerisError {
  constructor(message: string, options?: { sessionId?: string; cause?: unknown }) {
    super(message, 'DECISION_ERROR', { layer: 'decision-core', ...options });
    this.name = 'DecisionError';
  }
}

/** 预算超限 */
export class BudgetExceededError extends ValerisError {
  /** 已使用的 token 数 */
  readonly tokensUsed: number;
  /** 已花费的 USD */
  readonly costUsd: number;

  constructor(
    message: string,
    tokensUsed: number,
    costUsd: number,
    options?: { sessionId?: string },
  ) {
    super(message, 'BUDGET_EXCEEDED', { layer: 'executor', ...options });
    this.name = 'BudgetExceededError';
    this.tokensUsed = tokensUsed;
    this.costUsd = costUsd;
  }
}

/** Skill 执行失败 */
export class SkillExecutionError extends ValerisError {
  /** 失败的 Skill 名称 */
  readonly skillName: string;

  constructor(
    skillName: string,
    message: string,
    options?: { sessionId?: string; cause?: unknown },
  ) {
    super(message, 'SKILL_EXECUTION_ERROR', { layer: 'executor', ...options });
    this.name = 'SkillExecutionError';
    this.skillName = skillName;
  }
}

/** Skill 未找到 */
export class SkillNotFoundError extends ValerisError {
  constructor(skillName: string) {
    super(`Skill not found: ${skillName}`, 'SKILL_NOT_FOUND', { layer: 'planner' });
    this.name = 'SkillNotFoundError';
  }
}

/** LLM 调用失败 */
export class LLMError extends ValerisError {
  constructor(message: string, options?: { sessionId?: string; cause?: unknown }) {
    super(message, 'LLM_ERROR', { layer: 'executor', ...options });
    this.name = 'LLMError';
  }
}

/** 存储操作失败 */
export class StorageError extends ValerisError {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, 'STORAGE_ERROR', { ...options });
    this.name = 'StorageError';
  }
}
