/**
 * 策略路由器（OpenHarness 二开版）
 * 作用：把“输入上下文”映射为“可执行路由决策”，实现可审计的规则命中链路。
 */

import type {
  PolicyCondition,
  PolicyLeafCondition,
  RoutingContext,
  RoutingDecision,
  RoutingPolicy,
  RoutingRule,
} from '../types.js';

/**
 * 路由器：根据策略配置执行规则匹配，输出标准化 RoutingDecision。
 */
export class PolicyRouter {
  constructor(private readonly policy: RoutingPolicy) {}

  /**
   * 执行一次路由决策。
   * 为什么这样做：统一把 rule match、fallback、trace 封装为单入口，便于审计与测试。
   */
  route(input: RoutingContext): RoutingDecision {
    const sortedRules = [...this.policy.rules].sort((a, b) => b.priority - a.priority);
    const evaluatedRules: string[] = [];

    let selectedRule: RoutingRule | null = null;
    for (const rule of sortedRules) {
      evaluatedRules.push(rule.id);
      if (this.matches(rule.when, input)) {
        selectedRule = rule;
        break;
      }
    }

    const selectedRoute = selectedRule?.route ?? this.policy.fallback;
    const strategy = this.policy.strategies[selectedRoute.strategy];
    if (!strategy) {
      throw new Error(`Routing strategy not found: ${selectedRoute.strategy}`);
    }

    const stopProfile = this.policy.stopProfiles[selectedRoute.stopProfile];
    if (!stopProfile) {
      throw new Error(`Stop profile not found: ${selectedRoute.stopProfile}`);
    }

    const confidence = this.computeConfidence(selectedRule, sortedRules.length);
    const selectedRuleId = selectedRule?.id ?? 'FALLBACK';

    return {
      selectedStrategy: selectedRoute.strategy,
      selectedRoute: {
        mode: strategy.mode,
        runtime: strategy.runtime,
        autonomy: strategy.autonomy,
        score: confidence,
      },
      stopProfile: selectedRoute.stopProfile,
      activeStopConditions: stopProfile.conditionIds,
      reasonCodes: [selectedRuleId, selectedRoute.reason],
      requiredCapabilities: strategy.requiredCapabilities,
      trace: {
        evaluatedRules,
        selectedRule: selectedRuleId,
        timestamp: input.timestamp,
      },
    };
  }

  /**
   * 判断条件是否命中。
   * 为什么这样做：支持 all/any 组合条件，便于把路由规则从代码迁移到配置。
   */
  private matches(condition: PolicyCondition, input: RoutingContext): boolean {
    if ('all' in condition || 'any' in condition) {
      const group = condition;
      if (group.all && group.all.length > 0) {
        return group.all.every((item) => this.matches(item, input));
      }
      if (group.any && group.any.length > 0) {
        return group.any.some((item) => this.matches(item, input));
      }
      return false;
    }

    const leaf = condition as PolicyLeafCondition;
    const actual = this.readPath(input, leaf.field);
    return this.compare(actual, leaf.op, leaf.value);
  }

  /**
   * 读取点路径字段。
   * 为什么这样做：规则字段使用字符串路径，路由器必须通用读取不同输入结构。
   */
  private readPath(data: unknown, path: string): unknown {
    const segments = path.split('.');
    let cursor: unknown = data;
    for (const segment of segments) {
      if (!cursor || typeof cursor !== 'object' || !(segment in cursor)) {
        return undefined;
      }
      cursor = (cursor as Record<string, unknown>)[segment];
    }
    return cursor;
  }

  /**
   * 执行操作符比较。
   * 为什么这样做：把规则表达式转换为统一比较逻辑，便于扩展新操作符。
   */
  private compare(actual: unknown, op: PolicyLeafCondition['op'], expected: unknown): boolean {
    switch (op) {
      case 'eq':
        return actual === expected;
      case 'ne':
        return actual !== expected;
      case 'gt':
        return typeof actual === 'number' && typeof expected === 'number' && actual > expected;
      case 'gte':
        return typeof actual === 'number' && typeof expected === 'number' && actual >= expected;
      case 'lt':
        return typeof actual === 'number' && typeof expected === 'number' && actual < expected;
      case 'lte':
        return typeof actual === 'number' && typeof expected === 'number' && actual <= expected;
      case 'in':
        return Array.isArray(expected) && expected.includes(actual);
      case 'not_in':
        return Array.isArray(expected) && !expected.includes(actual);
      default:
        return false;
    }
  }

  /**
   * 计算路由置信度。
   * 为什么这样做：命中越靠前优先级越高，给更高分用于下游审计分析。
   */
  private computeConfidence(rule: RoutingRule | null, totalRules: number): number {
    if (!rule || totalRules <= 0) return 0.55;
    const sorted = [...this.policy.rules].sort((a, b) => b.priority - a.priority);
    const index = sorted.findIndex((item) => item.id === rule.id);
    if (index < 0) return 0.6;
    const normalized = 1 - index / Math.max(totalRules, 1);
    return Math.round((0.6 + normalized * 0.4) * 1000) / 1000;
  }
}
