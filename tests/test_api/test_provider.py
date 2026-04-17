"""Provider 解析相关测试。"""

from __future__ import annotations

from openharness.api.provider import auth_status, detect_provider, resolve_auth_status
from openharness.config.settings import Settings


def test_detect_provider_prefers_explicit_provider() -> None:
    """显式 provider 应优先于模型名和 base_url 推断。"""

    info = detect_provider(
        Settings(
            provider="moonshot",
            api_format="openai_compat",
            model="claude-sonnet-4-20250514",
        )
    )
    assert info.name == "moonshot"
    assert info.display_name == "Moonshot"


def test_auth_status_uses_provider_specific_env(monkeypatch) -> None:
    """认证状态应识别 provider 对应的环境变量。"""

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    status = auth_status(Settings(provider="openai", api_format="openai_compat"))
    assert status == "configured"


def test_resolve_auth_status_prefers_env_source_over_loaded_api_key(monkeypatch) -> None:
    """当环境变量生效时，认证来源应显示为 env 而不是 settings。"""

    monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-secret")
    info = resolve_auth_status(
        Settings(
            provider="moonshot",
            api_format="openai_compat",
            api_key="persisted-secret",
        )
    )
    assert info.status == "configured"
    assert info.source == "env:MOONSHOT_API_KEY"
