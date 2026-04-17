"""Provider/auth capability helpers."""

from __future__ import annotations

from dataclasses import dataclass

from openharness.api.registry import (
    infer_provider_spec,
    resolve_api_key_source_from_env,
)
from openharness.config.settings import Settings


@dataclass(frozen=True)
class ProviderInfo:
    """已解析的 provider 元数据。

    用于 UI 和诊断输出，避免每个调用点自己拼装 provider 描述。
    """

    name: str
    display_name: str
    auth_kind: str
    voice_supported: bool
    voice_reason: str


@dataclass(frozen=True)
class AuthStatusInfo:
    """认证状态详情。

    统一表达当前 provider 的鉴权状态、来源和推荐环境变量，
    供 CLI、slash command 与状态面板复用，避免各处输出不一致。
    """

    status: str
    source: str
    credential_env: str


def detect_provider(settings: Settings) -> ProviderInfo:
    """Infer the active provider and rough capability set."""
    spec = infer_provider_spec(
        provider_name=settings.provider,
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        api_format=settings.api_format,
    )
    return ProviderInfo(
        name=spec.name,
        display_name=spec.display_name,
        auth_kind="api_key",
        voice_supported=False,
        voice_reason="voice mode shell exists, but live voice auth/streaming is not configured in this build",
    )


def auth_status(settings: Settings) -> str:
    """Return a compact auth status string."""
    return resolve_auth_status(settings).status


def auth_source(settings: Settings) -> str:
    """Return where the current provider credential is sourced from."""
    return resolve_auth_status(settings).source


def resolve_auth_status(settings: Settings) -> AuthStatusInfo:
    """Resolve provider-aware auth details for diagnostics and CLI output."""
    spec = infer_provider_spec(
        provider_name=settings.provider,
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        api_format=settings.api_format,
    )
    env_name, env_value = resolve_api_key_source_from_env(
        provider_name=settings.provider,
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        api_format=settings.api_format,
    )
    if env_value:
        return AuthStatusInfo(
            status="configured",
            source=f"env:{env_name}",
            credential_env=spec.env_key,
        )

    if settings.api_key:
        return AuthStatusInfo(
            status="configured",
            source="settings",
            credential_env=spec.env_key,
        )

    return AuthStatusInfo(
        status="missing",
        source="missing",
        credential_env=spec.env_key,
    )


def render_provider_status_panel(
    *,
    title: str,
    settings: Settings,
    auth_note: str | None = None,
) -> str:
    """渲染统一的 provider/auth 状态面板。"""

    provider = detect_provider(settings)
    auth_info = resolve_auth_status(settings)
    spec = infer_provider_spec(
        provider_name=settings.provider,
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        api_format=settings.api_format,
    )
    lines = [
        f"{title}:",
        f"- provider: {provider.name}",
        f"- display: {provider.display_name}",
        f"- api_format: {spec.api_format}",
        f"- base_url: {settings.base_url or '(provider default)'}",
        f"- model: {settings.model}",
        f"- auth_status: {auth_info.status}",
        f"- auth_source: {auth_info.source}",
        f"- credential_env: {auth_info.credential_env}",
    ]
    if auth_note:
        lines.append(f"- auth_note: {auth_note}")
    return "\n".join(lines)
