/**
 * L0 事件总线 - 类型安全的 EventEmitter
 * 用于六层架构之间的解耦通信
 */

import type { ValerisEvents } from '../types.js';

/** 事件处理函数类型 */
type EventHandler<T> = (data: T) => void;

/**
 * 类型安全的事件总线
 * 所有事件类型在 ValerisEvents 接口中定义
 */
export class EventBus {
  /** 事件监听器映射表 */
  private readonly listeners = new Map<string, Set<EventHandler<unknown>>>();

  /** 注册事件监听器 */
  on<K extends keyof ValerisEvents>(event: K, handler: EventHandler<ValerisEvents[K]>): void {
    const handlers = this.listeners.get(event as string) ?? new Set();
    handlers.add(handler as EventHandler<unknown>);
    this.listeners.set(event as string, handlers);
  }

  /** 注册一次性事件监听器 */
  once<K extends keyof ValerisEvents>(event: K, handler: EventHandler<ValerisEvents[K]>): void {
    const wrapper: EventHandler<ValerisEvents[K]> = (data) => {
      this.off(event, wrapper);
      handler(data);
    };
    this.on(event, wrapper);
  }

  /** 移除事件监听器 */
  off<K extends keyof ValerisEvents>(event: K, handler: EventHandler<ValerisEvents[K]>): void {
    const handlers = this.listeners.get(event as string);
    if (handlers) {
      handlers.delete(handler as EventHandler<unknown>);
      if (handlers.size === 0) {
        this.listeners.delete(event as string);
      }
    }
  }

  /** 发射事件，通知所有监听器 */
  emit<K extends keyof ValerisEvents>(event: K, data: ValerisEvents[K]): void {
    const handlers = this.listeners.get(event as string);
    if (handlers) {
      for (const handler of handlers) {
        try {
          handler(data);
        } catch {
          // 事件处理器异常不应阻断事件传播
        }
      }
    }
  }

  /** 移除所有监听器 */
  removeAll(): void {
    this.listeners.clear();
  }

  /** 获取指定事件的监听器数量 */
  listenerCount(event: keyof ValerisEvents): number {
    return this.listeners.get(event as string)?.size ?? 0;
  }
}
