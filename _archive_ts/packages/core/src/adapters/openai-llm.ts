/**
 * OpenAI-compatible LLM 适配器
 * 支持所有 OpenAI API 兼容的提供商（OpenAI, Anthropic via proxy, Deepseek 等）
 */

import type { LLMAdapter, LLMChatRequest, LLMChatResponse } from '../types.js';
import { LLMError } from '@velaris/shared';

/** OpenAI LLM 配置 */
export interface OpenAILLMConfig {
  /** API Key */
  apiKey: string;
  /** API Base URL，默认 https://api.openai.com/v1 */
  baseUrl?: string;
  /** 默认模型 */
  defaultModel?: string;
  /** 请求超时毫秒，默认 30000 */
  timeoutMs?: number;
}

/**
 * OpenAI-compatible LLM 适配器
 * 使用 fetch API 直接调用，无需额外依赖
 */
export class OpenAILLM implements LLMAdapter {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly defaultModel: string;
  private readonly timeoutMs: number;

  constructor(config: OpenAILLMConfig) {
    this.apiKey = config.apiKey;
    this.baseUrl = config.baseUrl ?? 'https://api.openai.com/v1';
    this.defaultModel = config.defaultModel ?? 'gpt-4o-mini';
    this.timeoutMs = config.timeoutMs ?? 30000;
  }

  async chat(request: LLMChatRequest): Promise<LLMChatResponse> {
    const model = request.model || this.defaultModel;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await fetch(`${this.baseUrl}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${this.apiKey}`,
        },
        body: JSON.stringify({
          model,
          messages: request.messages.map((m) => ({
            role: m.role,
            content: m.content,
          })),
          temperature: request.temperature ?? 0.7,
          max_tokens: request.maxTokens,
          ...(request.responseFormat && {
            response_format: { type: request.responseFormat.type },
          }),
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errorBody = await response.text();
        throw new LLMError(
          `OpenAI API error ${response.status}: ${errorBody}`,
        );
      }

      const data = (await response.json()) as OpenAIResponse;
      const choice = data.choices[0];

      return {
        content: choice?.message?.content ?? '',
        model: data.model,
        usage: {
          inputTokens: data.usage?.prompt_tokens ?? 0,
          outputTokens: data.usage?.completion_tokens ?? 0,
        },
        finishReason: choice?.finish_reason === 'stop' ? 'stop' : 'length',
      };
    } catch (err) {
      if (err instanceof LLMError) throw err;
      throw new LLMError(`LLM call failed: ${String(err)}`, { cause: err });
    } finally {
      clearTimeout(timeout);
    }
  }

  async listModels(): Promise<string[]> {
    try {
      const response = await fetch(`${this.baseUrl}/models`, {
        headers: { Authorization: `Bearer ${this.apiKey}` },
      });

      if (!response.ok) return [this.defaultModel];

      const data = (await response.json()) as { data: Array<{ id: string }> };
      return data.data.map((m) => m.id);
    } catch {
      return [this.defaultModel];
    }
  }
}

/** OpenAI API 响应类型 */
interface OpenAIResponse {
  model: string;
  choices: Array<{
    message?: { content: string };
    finish_reason?: string;
  }>;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
  };
}
