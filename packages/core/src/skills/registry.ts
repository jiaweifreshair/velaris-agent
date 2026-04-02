/**
 * Skill 注册表
 * 管理所有已注册的 Skill，支持按名称查找
 */

import type { SkillDefinition } from '../types.js';
import { SkillNotFoundError } from '@valeris/shared';

/**
 * Skill 注册表
 * 存储和检索 Skill 定义，保证名称唯一性
 */
export class SkillRegistry {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- 类型擦除容器，存储不同泛型参数的 Skill
  private readonly skills = new Map<string, SkillDefinition<any, any>>();

  /** 注册一个 Skill（接受任意泛型参数，注册后类型擦除） */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- registry 作为类型擦除容器需要接受任意 Skill
  register(skill: SkillDefinition<any, any>): void {
    if (this.skills.has(skill.name)) {
      throw new Error(`Skill already registered: ${skill.name}`);
    }
    this.skills.set(skill.name, skill);
  }

  /** 批量注册 Skill */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- registry 作为类型擦除容器需要接受任意 Skill
  registerAll(skills: SkillDefinition<any, any>[]): void {
    for (const skill of skills) {
      this.register(skill);
    }
  }

  /** 按名称获取 Skill，不存在则抛出异常 */
  get(name: string): SkillDefinition {
    const skill = this.skills.get(name);
    if (!skill) {
      throw new SkillNotFoundError(name);
    }
    return skill;
  }

  /** 按名称查找 Skill，不存在返回 null */
  find(name: string): SkillDefinition | null {
    return this.skills.get(name) ?? null;
  }

  /** 检查 Skill 是否已注册 */
  has(name: string): boolean {
    return this.skills.has(name);
  }

  /** 获取所有已注册的 Skill 名称 */
  listNames(): string[] {
    return [...this.skills.keys()];
  }

  /** 获取所有已注册的 Skill */
  listAll(): SkillDefinition[] {
    return [...this.skills.values()];
  }

  /** Skill 总数 */
  get size(): number {
    return this.skills.size;
  }
}
