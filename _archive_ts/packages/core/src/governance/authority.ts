/**
 * 能力签发服务（OpenHarness 二开版）
 * 作用：把执行权限从提示词中剥离，显式签发可审计的最小权限令牌。
 */

import { generateId, now } from '@velaris/shared';
import type { AuthorityPlan, CapabilityToken, GovernanceDemand } from '../types.js';

/** 能力签发配置。 */
export interface AuthorityConfig {
  /** 默认令牌 TTL（秒）。 */
  defaultTokenTtlSeconds: number;
  /** 在 ask 模式下触发审批的敏感能力集合。 */
  approvalSensitiveCapabilities: string[];
}

const DEFAULT_AUTHORITY_CONFIG: AuthorityConfig = {
  defaultTokenTtlSeconds: 1800,
  approvalSensitiveCapabilities: ['write', 'exec', 'audit'],
};

/**
 * 授权服务：生成审批判定和能力令牌。
 */
export class AuthorityService {
  private readonly config: AuthorityConfig;

  constructor(config?: Partial<AuthorityConfig>) {
    this.config = {
      ...DEFAULT_AUTHORITY_CONFIG,
      ...config,
    };
  }

  /**
   * 生成授权计划。
   * 为什么这样做：执行前统一落地权限需求，避免隐式越权。
   */
  issuePlan(
    requiredCapabilities: string[],
    governance: GovernanceDemand,
  ): AuthorityPlan {
    const dedupedCapabilities = [...new Set(requiredCapabilities)];
    const approvalsRequired = this.shouldRequireApproval(dedupedCapabilities, governance);
    const capabilityTokens = this.createTokens(dedupedCapabilities);

    return {
      approvalsRequired,
      requiredCapabilities: dedupedCapabilities,
      capabilityTokens,
    };
  }

  /**
   * 计算是否需要审批。
   * 为什么这样做：把审批逻辑收敛到单函数，便于根据合规要求快速调整。
   */
  private shouldRequireApproval(
    requiredCapabilities: string[],
    governance: GovernanceDemand,
  ): boolean {
    if (governance.approvalMode === 'strict') {
      return true;
    }
    if (governance.approvalMode === 'none') {
      return false;
    }
    return requiredCapabilities.some((capability) =>
      this.config.approvalSensitiveCapabilities.includes(capability),
    );
  }

  /**
   * 创建能力令牌。
   * 为什么这样做：每次执行都签发短时令牌，支持最小权限和可追踪失效。
   */
  private createTokens(requiredCapabilities: string[]): CapabilityToken[] {
    if (requiredCapabilities.length === 0) {
      return [];
    }
    return [
      {
        tokenId: generateId('cap'),
        scope: requiredCapabilities,
        ttlSeconds: this.config.defaultTokenTtlSeconds,
        issuedAt: now(),
      },
    ];
  }
}
