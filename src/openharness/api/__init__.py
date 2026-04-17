"""API 顶层导出。

这里使用惰性导出，避免 `config.settings -> api.registry` 这类轻量依赖
因为 `api.__init__` 的重型导入而触发循环引用。
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AnthropicApiClient",
    "OpenAICompatibleClient",
    "OpenHarnessApiError",
    "ProviderInfo",
    "UsageSnapshot",
    "auth_status",
    "detect_provider",
]


def __getattr__(name: str) -> Any:
    """按需加载 API 导出，降低包初始化时的耦合。"""

    if name == "AnthropicApiClient":
        from openharness.api.client import AnthropicApiClient

        return AnthropicApiClient
    if name == "OpenAICompatibleClient":
        from openharness.api.openai_client import OpenAICompatibleClient

        return OpenAICompatibleClient
    if name == "OpenHarnessApiError":
        from openharness.api.errors import OpenHarnessApiError

        return OpenHarnessApiError
    if name == "UsageSnapshot":
        from openharness.api.usage import UsageSnapshot

        return UsageSnapshot
    if name in {"ProviderInfo", "auth_status", "detect_provider"}:
        from openharness.api.provider import ProviderInfo, auth_status, detect_provider

        return {
            "ProviderInfo": ProviderInfo,
            "auth_status": auth_status,
            "detect_provider": detect_provider,
        }[name]
    raise AttributeError(name)
