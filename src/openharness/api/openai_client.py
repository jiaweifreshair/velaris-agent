"""OpenAI-compatible API client。

用于接入 OpenAI、Moonshot、DashScope、Gemini OpenAI bridge 等兼容接口，
让 Velaris 在保留现有工具循环的前提下支持更多上游 OpenHarness 的 provider 能力。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator
from urllib.parse import urlsplit, urlunsplit

from openharness.api.client import (
    ApiMessageCompleteEvent,
    ApiMessageRequest,
    ApiStreamEvent,
    ApiTextDeltaEvent,
)
from openharness.api.errors import (
    AuthenticationFailure,
    OpenHarnessApiError,
    RateLimitFailure,
    RequestFailure,
)
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock, ToolResultBlock, ToolUseBlock

log = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_DELAY = 1.0
MAX_DELAY = 30.0
_MAX_COMPLETION_TOKEN_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _token_limit_param_for_model(model: str, max_tokens: int) -> dict[str, int]:
    """为不同模型家族选择正确的 token 限制字段。"""

    normalized = model.strip().lower()
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    if normalized.startswith(_MAX_COMPLETION_TOKEN_MODEL_PREFIXES):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}


def _normalize_openai_base_url(base_url: str | None) -> str | None:
    """规范化兼容网关地址，避免丢掉 `/v1` 这类路径前缀。"""

    if not base_url:
        return None
    trimmed = base_url.strip()
    if not trimmed:
        return None
    parts = urlsplit(trimmed)
    if not parts.scheme or not parts.netloc:
        return trimmed.rstrip("/")
    path = parts.path.rstrip("/")
    if not path:
        path = "/v1"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _convert_tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把 Anthropic 风格工具 schema 转成 OpenAI function calling。"""

    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        }
        for tool in tools
    ]


def _convert_messages_to_openai(
    messages: list[ConversationMessage],
    system_prompt: str | None,
) -> list[dict[str, Any]]:
    """把当前消息结构转换成 OpenAI chat completions 格式。"""

    openai_messages: list[dict[str, Any]] = []
    if system_prompt:
        openai_messages.append({"role": "system", "content": system_prompt})

    for message in messages:
        if message.role == "assistant":
            openai_messages.append(_convert_assistant_message(message))
            continue

        tool_results = [block for block in message.content if isinstance(block, ToolResultBlock)]
        user_text = "".join(block.text for block in message.content if isinstance(block, TextBlock))

        for tool_result in tool_results:
            openai_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_result.tool_use_id,
                    "content": tool_result.content,
                }
            )
        if user_text or not tool_results:
            openai_messages.append({"role": "user", "content": user_text})

    return openai_messages


def _convert_assistant_message(message: ConversationMessage) -> dict[str, Any]:
    """把 assistant 消息转换成 OpenAI assistant message。"""

    text = "".join(block.text for block in message.content if isinstance(block, TextBlock))
    tool_uses = [block for block in message.content if isinstance(block, ToolUseBlock)]
    payload: dict[str, Any] = {
        "role": "assistant",
        "content": text or None,
    }
    if tool_uses:
        payload["tool_calls"] = [
            {
                "id": tool_use.id,
                "type": "function",
                "function": {
                    "name": tool_use.name,
                    "arguments": json.dumps(tool_use.input, ensure_ascii=True),
                },
            }
            for tool_use in tool_uses
        ]
        reasoning = getattr(message, "_reasoning", None)
        if reasoning is not None:
            payload["reasoning_content"] = reasoning
    return payload


def _parse_assistant_response(response: Any) -> ConversationMessage:
    """把 OpenAI 响应解析回当前 agent 循环使用的消息结构。"""

    choice = response.choices[0]
    message = choice.message
    content: list[Any] = []
    if message.content:
        content.append(TextBlock(text=message.content))
    if message.tool_calls:
        for tool_call in message.tool_calls:
            try:
                arguments = json.loads(tool_call.function.arguments)
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            content.append(
                ToolUseBlock(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    input=arguments,
                )
            )
    parsed = ConversationMessage(role="assistant", content=content)
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning is not None:
        parsed.__dict__["_reasoning"] = reasoning
    return parsed


class OpenAICompatibleClient:
    """OpenAI-compatible provider 客户端。

    对外保持和 `AnthropicApiClient` 一致的流式接口，
    让 query engine 无需理解具体 provider 的差异。
    """

    def __init__(self, api_key: str, *, base_url: str | None = None, timeout: float | None = None) -> None:
        self._api_key = api_key
        self._base_url = _normalize_openai_base_url(base_url)
        self._timeout = timeout
        self._client: Any | None = None

    def _get_client(self) -> Any:
        """按需加载 OpenAI SDK，避免未安装时影响 Anthropic 路径。"""

        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - 依赖缺失时的兜底
            raise RequestFailure(
                "OpenAI-compatible provider requires the `openai` package. "
                "Run `uv sync --extra dev` or install project dependencies first."
            ) from exc

        kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        if self._timeout is not None:
            kwargs["timeout"] = self._timeout
        self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        """输出文本增量和最终消息，接口与 Anthropic 客户端保持一致。"""

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                async for event in self._stream_once(request):
                    yield event
                return
            except OpenHarnessApiError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt >= MAX_RETRIES or not self._is_retryable(exc):
                    raise self._translate_error(exc) from exc
                delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
                log.warning(
                    "OpenAI-compatible request failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    MAX_RETRIES + 1,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)

        if last_error is not None:
            raise self._translate_error(last_error) from last_error

    async def _stream_once(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        """执行一次请求并回放成统一的事件流。

        这里优先保证兼容性和结果一致性：使用一次非流式请求拿到稳定的
        文本、工具调用和 usage，再把文本作为单段 delta 回放给上层。
        """

        client = self._get_client()
        params: dict[str, Any] = {
            "model": request.model,
            "messages": _convert_messages_to_openai(request.messages, request.system_prompt),
            "stream": False,
            **_token_limit_param_for_model(request.model, request.max_tokens),
        }
        if request.tools:
            params["tools"] = _convert_tools_to_openai(request.tools)

        completion = await client.chat.completions.create(**params)
        final_message = _parse_assistant_response(completion)
        if final_message.text:
            yield ApiTextDeltaEvent(text=final_message.text)
        usage = getattr(completion, "usage", None)
        yield ApiMessageCompleteEvent(
            message=final_message,
            usage=UsageSnapshot(
                input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            ),
            stop_reason=getattr(completion.choices[0], "finish_reason", None) if completion.choices else None,
        )

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """判断异常是否值得自动重试。"""

        text = str(exc).lower()
        return any(marker in text for marker in ("rate limit", "timeout", "temporarily", "connection", "429", "500", "502", "503"))

    @staticmethod
    def _translate_error(exc: Exception) -> OpenHarnessApiError:
        """把 SDK 或网关异常映射成统一的运行时错误类型。"""

        text = str(exc).lower()
        if "auth" in text or "unauthorized" in text or "invalid api key" in text:
            return AuthenticationFailure(str(exc))
        if "rate limit" in text or "429" in text:
            return RateLimitFailure(str(exc))
        return RequestFailure(str(exc))
