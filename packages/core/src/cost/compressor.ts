/**
 * 上下文压缩器
 * 当 token budget 紧张时，压缩历史上下文以节省成本
 */

import type { LLMAdapter, LLMMessage } from '../types.js';

/** 压缩策略 */
export type CompressionStrategy = 'truncate' | 'summarize';

/** 压缩结果 */
export interface CompressionResult {
  /** 压缩后的消息列表 */
  messages: LLMMessage[];
  /** 压缩前 token 数（估算） */
  originalTokens: number;
  /** 压缩后 token 数（估算） */
  compressedTokens: number;
  /** 使用的策略 */
  strategy: CompressionStrategy;
}

/**
 * 上下文压缩器
 * 支持截断和摘要两种策略
 */
export class ContextCompressor {
  /** 粗略估算文本 token 数（英文约 4 字符/token，中文约 2 字符/token） */
  static estimateTokens(text: string): number {
    // 简单估算：英文按 4 字符/token，中文按 1.5 字符/token
    const cjkChars = (text.match(/[\u4e00-\u9fff\u3400-\u4dbf]/g) ?? []).length;
    const otherChars = text.length - cjkChars;
    return Math.ceil(cjkChars / 1.5 + otherChars / 4);
  }

  /** 估算消息列表的总 token 数 */
  static estimateMessagesTokens(messages: LLMMessage[]): number {
    return messages.reduce(
      (sum, msg) => sum + ContextCompressor.estimateTokens(msg.content) + 4, // 4 token overhead per message
      0,
    );
  }

  /**
   * 截断策略：保留系统消息 + 最近 N 条消息
   */
  static truncate(messages: LLMMessage[], maxTokens: number): CompressionResult {
    const originalTokens = ContextCompressor.estimateMessagesTokens(messages);

    if (originalTokens <= maxTokens) {
      return { messages, originalTokens, compressedTokens: originalTokens, strategy: 'truncate' };
    }

    // 保留第一条系统消息（如果有）
    const systemMsg = messages[0]?.role === 'system' ? [messages[0]] : [];
    const nonSystemMsgs = messages[0]?.role === 'system' ? messages.slice(1) : messages;

    // 从最新消息开始保留，直到达到 token 上限
    const kept: LLMMessage[] = [];
    let tokenCount = ContextCompressor.estimateMessagesTokens(systemMsg);

    for (let i = nonSystemMsgs.length - 1; i >= 0; i--) {
      const msg = nonSystemMsgs[i]!;
      const msgTokens = ContextCompressor.estimateTokens(msg.content) + 4;
      if (tokenCount + msgTokens > maxTokens) break;
      kept.unshift(msg);
      tokenCount += msgTokens;
    }

    const result = [...systemMsg, ...kept];
    return {
      messages: result,
      originalTokens,
      compressedTokens: ContextCompressor.estimateMessagesTokens(result),
      strategy: 'truncate',
    };
  }

  /**
   * 摘要策略：用 LLM 将历史消息压缩为摘要
   */
  static async summarize(
    messages: LLMMessage[],
    maxTokens: number,
    llm: LLMAdapter,
    model: string,
  ): Promise<CompressionResult> {
    const originalTokens = ContextCompressor.estimateMessagesTokens(messages);

    if (originalTokens <= maxTokens) {
      return { messages, originalTokens, compressedTokens: originalTokens, strategy: 'summarize' };
    }

    // 保留系统消息和最后 2 条消息
    const systemMsg = messages[0]?.role === 'system' ? messages[0] : null;
    const recentMessages = messages.slice(-2);
    const middleMessages = systemMsg
      ? messages.slice(1, -2)
      : messages.slice(0, -2);

    // 如果中间消息为空，直接截断
    if (middleMessages.length === 0) {
      return ContextCompressor.truncate(messages, maxTokens);
    }

    // 用 LLM 将中间消息压缩为摘要
    const conversationText = middleMessages
      .map((m) => `${m.role}: ${m.content}`)
      .join('\n');

    const response = await llm.chat({
      model,
      messages: [
        {
          role: 'system',
          content: 'Summarize the following conversation concisely, preserving key decisions, data, and context. Output only the summary.',
        },
        { role: 'user', content: conversationText },
      ],
      maxTokens: Math.floor(maxTokens * 0.3), // 摘要最多占 30% 预算
    });

    const summaryMsg: LLMMessage = {
      role: 'assistant',
      content: `[Previous conversation summary]\n${response.content}`,
    };

    const result = [
      ...(systemMsg ? [systemMsg] : []),
      summaryMsg,
      ...recentMessages,
    ];

    return {
      messages: result,
      originalTokens,
      compressedTokens: ContextCompressor.estimateMessagesTokens(result),
      strategy: 'summarize',
    };
  }
}
