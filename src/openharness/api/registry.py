"""LLM 提供商注册表。

把 provider 的协议格式、默认网关和环境变量收敛到一处，
避免 CLI、状态展示和 runtime 选型各自维护一套不一致规则。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    """提供商元数据。

    描述 provider 是什么、默认走什么 API 格式、该读哪个环境变量，
    以及当用户只给了模型名或 base_url 时如何推断 provider。
    """

    name: str
    display_name: str
    api_format: str
    env_key: str
    default_base_url: str = ""
    model_keywords: tuple[str, ...] = ()
    base_url_keywords: tuple[str, ...] = ()
    api_key_prefixes: tuple[str, ...] = ()


PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        name="anthropic",
        display_name="Anthropic",
        api_format="anthropic",
        env_key="ANTHROPIC_API_KEY",
        model_keywords=("claude", "anthropic", "sonnet", "opus", "haiku"),
    ),
    ProviderSpec(
        name="openai",
        display_name="OpenAI",
        api_format="openai_compat",
        env_key="OPENAI_API_KEY",
        model_keywords=("gpt", "openai", "o1", "o3", "o4"),
    ),
    ProviderSpec(
        name="moonshot",
        display_name="Moonshot",
        api_format="openai_compat",
        env_key="MOONSHOT_API_KEY",
        default_base_url="https://api.moonshot.ai/v1",
        model_keywords=("moonshot", "kimi"),
        base_url_keywords=("moonshot",),
    ),
    ProviderSpec(
        name="dashscope",
        display_name="DashScope",
        api_format="openai_compat",
        env_key="DASHSCOPE_API_KEY",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model_keywords=("qwen", "dashscope"),
        base_url_keywords=("dashscope", "aliyuncs"),
    ),
    ProviderSpec(
        name="gemini",
        display_name="Gemini",
        api_format="openai_compat",
        env_key="GEMINI_API_KEY",
        default_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model_keywords=("gemini",),
        base_url_keywords=("googleapis", "generativelanguage"),
    ),
    ProviderSpec(
        name="deepseek",
        display_name="DeepSeek",
        api_format="openai_compat",
        env_key="DEEPSEEK_API_KEY",
        default_base_url="https://api.deepseek.com/v1",
        model_keywords=("deepseek",),
        base_url_keywords=("deepseek",),
    ),
    ProviderSpec(
        name="minimax",
        display_name="MiniMax",
        api_format="openai_compat",
        env_key="MINIMAX_API_KEY",
        default_base_url="https://api.minimax.io/v1",
        model_keywords=("minimax",),
        base_url_keywords=("minimax",),
    ),
    ProviderSpec(
        name="zhipu",
        display_name="Zhipu AI",
        api_format="openai_compat",
        env_key="ZHIPUAI_API_KEY",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        model_keywords=("glm", "chatglm", "zhipu"),
        base_url_keywords=("bigmodel", "zhipu"),
    ),
    ProviderSpec(
        name="groq",
        display_name="Groq",
        api_format="openai_compat",
        env_key="GROQ_API_KEY",
        default_base_url="https://api.groq.com/openai/v1",
        model_keywords=("groq",),
        base_url_keywords=("groq",),
        api_key_prefixes=("gsk_",),
    ),
    ProviderSpec(
        name="openrouter",
        display_name="OpenRouter",
        api_format="openai_compat",
        env_key="OPENROUTER_API_KEY",
        default_base_url="https://openrouter.ai/api/v1",
        model_keywords=("openrouter",),
        base_url_keywords=("openrouter",),
        api_key_prefixes=("sk-or-",),
    ),
)


def list_provider_specs() -> tuple[ProviderSpec, ...]:
    """返回所有内置 provider。

    供 CLI 列表页和测试复用，避免散落的硬编码 provider 列表。
    """

    return PROVIDERS


def get_provider_spec(name: str | None) -> ProviderSpec | None:
    """按名称查找 provider 元数据。"""

    if not name:
        return None
    normalized = name.strip().lower()
    for spec in PROVIDERS:
        if spec.name == normalized:
            return spec
    return None


def infer_provider_spec(
    *,
    provider_name: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    api_format: str | None = None,
) -> ProviderSpec:
    """根据显式配置和线索推断当前 provider。

    优先级是显式 provider 名称，其次是 base_url、API key 前缀和模型名，
    最后再退回 API 格式默认值，保证没有 provider 配置时也能稳定工作。
    """

    explicit = get_provider_spec(provider_name)
    if explicit is not None:
        return explicit

    normalized_base_url = (base_url or "").strip().lower()
    if normalized_base_url:
        for spec in PROVIDERS:
            if any(keyword in normalized_base_url for keyword in spec.base_url_keywords):
                return spec

    normalized_api_key = (api_key or "").strip()
    if normalized_api_key:
        for spec in PROVIDERS:
            if any(normalized_api_key.startswith(prefix) for prefix in spec.api_key_prefixes):
                return spec

    normalized_model = (model or "").strip().lower()
    if normalized_model:
        for spec in PROVIDERS:
            if any(keyword in normalized_model for keyword in spec.model_keywords):
                return spec

    if api_format == "openai_compat":
        fallback = get_provider_spec("openai")
        assert fallback is not None
        return fallback

    fallback = get_provider_spec("anthropic")
    assert fallback is not None
    return fallback


def resolve_api_key_from_env(
    *,
    provider_name: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    api_format: str | None = None,
) -> str:
    """按 provider 语义从环境变量解析 API key。

    会同时兼容 `VELARIS_*`、`OPENHARNESS_*` 和 provider 自己的环境变量，
    这样品牌升级后旧配置仍可继续工作。
    """

    _env_name, env_value = resolve_api_key_source_from_env(
        provider_name=provider_name,
        model=model,
        base_url=base_url,
        api_key=api_key,
        api_format=api_format,
    )
    return env_value


def resolve_api_key_source_from_env(
    *,
    provider_name: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    api_format: str | None = None,
) -> tuple[str, str]:
    """按 provider 语义返回命中的环境变量名和值。

    会同时兼容 `VELARIS_*`、`OPENHARNESS_*` 和 provider 自己的环境变量，
    这样品牌升级后旧配置仍可继续工作。
    """

    spec = infer_provider_spec(
        provider_name=provider_name,
        model=model,
        base_url=base_url,
        api_key=api_key,
        api_format=api_format,
    )
    names: list[str] = ["VELARIS_API_KEY", "OPENHARNESS_API_KEY"]
    if spec.env_key:
        names.append(spec.env_key)
    if spec.api_format == "openai_compat":
        names.append("OPENAI_API_KEY")
    names.append("ANTHROPIC_API_KEY")

    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        value = os.environ.get(name, "")
        if value:
            return name, value
    return "", ""
