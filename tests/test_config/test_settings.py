"""Tests for openharness.config.settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openharness.config.settings import Settings, load_settings, save_settings


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.api_key == ""
        assert s.model == "claude-sonnet-4-20250514"
        assert s.max_tokens == 16384
        assert s.fast_mode is False
        assert s.permission.mode == "default"
        assert s.security.approval_mode == "manual"

    def test_resolve_api_key_from_instance(self):
        s = Settings(api_key="sk-test-123")
        assert s.resolve_api_key() == "sk-test-123"

    def test_resolve_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-456")
        s = Settings()
        assert s.resolve_api_key() == "sk-env-456"

    def test_resolve_api_key_from_openai_compatible_env(self, monkeypatch):
        """OpenAI-compatible provider 应读取对应环境变量。"""
        monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-key")
        s = Settings(provider="moonshot", api_format="openai_compat", model="kimi-k2")
        assert s.resolve_api_key() == "moonshot-key"

    def test_resolve_api_key_instance_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-456")
        s = Settings(api_key="sk-instance-789")
        assert s.resolve_api_key() == "sk-instance-789"

    def test_resolve_api_key_missing_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        s = Settings()
        with pytest.raises(ValueError, match="No API key found"):
            s.resolve_api_key()

    def test_merge_cli_overrides(self):
        s = Settings()
        updated = s.merge_cli_overrides(model="claude-opus-4-20250514", verbose=True, api_key=None)
        assert updated.model == "claude-opus-4-20250514"
        assert updated.verbose is True
        # api_key=None should not override the default
        assert updated.api_key == ""

    def test_merge_cli_overrides_returns_new_instance(self):
        s = Settings()
        updated = s.merge_cli_overrides(model="claude-opus-4-20250514")
        assert s.model != updated.model
        assert s is not updated


class TestLoadSaveSettings:
    def test_load_missing_file_returns_defaults(self, tmp_path: Path):
        path = tmp_path / "nonexistent.json"
        s = load_settings(path)
        assert s == Settings()

    def test_load_existing_file(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"model": "claude-opus-4-20250514", "verbose": True, "fast_mode": True}))
        s = load_settings(path)
        assert s.model == "claude-opus-4-20250514"
        assert s.verbose is True
        assert s.fast_mode is True
        assert s.api_key == ""  # default preserved

    def test_save_and_load_roundtrip(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        original = Settings(api_key="sk-roundtrip", model="claude-opus-4-20250514", verbose=True)
        save_settings(original, path)
        loaded = load_settings(path)
        assert loaded.api_key == original.api_key
        assert loaded.model == original.model
        assert loaded.verbose == original.verbose

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "deep" / "nested" / "settings.json"
        save_settings(Settings(), path)
        assert path.exists()

    def test_load_with_permission_settings(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "permission": {
                        "mode": "full_auto",
                        "allowed_tools": ["Bash", "Read"],
                    }
                }
            )
        )
        s = load_settings(path)
        assert s.permission.mode == "full_auto"
        assert s.permission.allowed_tools == ["Bash", "Read"]

    def test_load_with_security_settings(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "security": {
                        "approval_mode": "smart",
                        "scan_project_instructions": False,
                    }
                }
            )
        )

        s = load_settings(path)

        assert s.security.approval_mode == "smart"
        assert s.security.scan_project_instructions is False

    def test_load_applies_env_overrides_model(self, tmp_path: Path, monkeypatch):
        """Env var 应覆盖文件中未显式设置的 model 值（默认值场景）。"""
        path = tmp_path / "settings.json"
        # 文件中 model 为默认值，env 应能覆盖
        path.write_text(json.dumps({"base_url": "https://file.example"}))
        monkeypatch.setenv("ANTHROPIC_MODEL", "from-env-model")

        s = load_settings(path)

        assert s.model == "from-env-model"

    def test_load_applies_env_overrides_model_preserves_explicit_value(self, tmp_path: Path, monkeypatch):
        """Env var 不应覆盖文件中显式设置的 model 值（PR #4 行为）。"""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"model": "from-file"}))
        monkeypatch.setenv("ANTHROPIC_MODEL", "from-env-model")

        s = load_settings(path)

        assert s.model == "from-file"

    def test_load_applies_env_overrides_base_url(self, tmp_path: Path, monkeypatch):
        """Env var 应覆盖文件中已配置的 base_url 值。"""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"model": "from-file", "base_url": "https://file.example"}))
        monkeypatch.setenv("ANTHROPIC_MODEL", "from-env-model")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://env.example/anthropic")

        s = load_settings(path)

        assert s.base_url == "https://env.example/anthropic"

    def test_load_applies_env_overrides_api_key(self, tmp_path: Path, monkeypatch):
        """Env var 应覆盖文件中未显式设置的 api_key 值。"""
        path = tmp_path / "settings.json"
        # 文件中 api_key 为空，env 应能覆盖
        path.write_text(json.dumps({"model": "from-file"}))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-override")

        s = load_settings(path)

        assert s.api_key == "sk-env-override"

    def test_load_applies_env_overrides_api_key_preserves_explicit_value(self, tmp_path: Path, monkeypatch):
        """Env var 不应覆盖文件中显式设置的 api_key 值（PR #4 行为）。"""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"api_key": "sk-from-file"}))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-override")

        s = load_settings(path)

        assert s.api_key == "sk-from-file"

    def test_load_applies_provider_env_override(self, tmp_path: Path, monkeypatch):
        """Env var 应覆盖文件中已配置的 provider 值。"""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"provider": "anthropic", "model": "claude-sonnet-4-20250514"}))
        monkeypatch.setenv("VELARIS_PROVIDER", "moonshot")

        s = load_settings(path)

        assert s.provider == "moonshot"

    def test_load_applies_api_format_env_override(self, tmp_path: Path, monkeypatch):
        """Env var 应覆盖文件中已配置的 api_format 值。"""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"provider": "anthropic", "api_format": "anthropic"}))
        monkeypatch.setenv("VELARIS_API_FORMAT", "openai_compat")

        s = load_settings(path)

        assert s.api_format == "openai_compat"

    def test_load_applies_max_tokens_env_override(self, tmp_path: Path, monkeypatch):
        """Env var 应覆盖文件中已配置的 max_tokens 值。"""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"max_tokens": 8192}))
        monkeypatch.setenv("VELARIS_MAX_TOKENS", "32768")

        s = load_settings(path)

        assert s.max_tokens == 32768

    def test_load_applies_all_env_overrides_together(self, tmp_path: Path, monkeypatch):
        """多个 env vars 应同时覆盖文件中的多个值。"""
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-20250514",
                    "api_format": "anthropic",
                    "max_tokens": 8192,
                    "base_url": "https://file.example",
                }
            )
        )
        monkeypatch.setenv("VELARIS_PROVIDER", "moonshot")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-4-20250514")
        monkeypatch.setenv("VELARIS_API_FORMAT", "openai_compat")
        monkeypatch.setenv("VELARIS_MAX_TOKENS", "65536")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-all")

        s = load_settings(path)

        assert s.provider == "moonshot"
        assert s.model == "claude-opus-4-20250514"
        assert s.api_format == "openai_compat"
        assert s.max_tokens == 65536
        assert s.api_key == "sk-env-all"

    def test_load_applies_provider_and_compact_env_overrides(self, tmp_path: Path, monkeypatch):
        """Provider 和 compact 阈值应允许通过环境变量覆盖。"""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"provider": "anthropic", "api_format": "anthropic"}))
        monkeypatch.setenv("VELARIS_PROVIDER", "moonshot")
        monkeypatch.setenv("VELARIS_API_FORMAT", "openai_compat")
        monkeypatch.setenv("VELARIS_AUTO_COMPACT_THRESHOLD_TOKENS", "54321")

        s = load_settings(path)

        assert s.provider == "moonshot"
        assert s.api_format == "openai_compat"
        assert s.auto_compact_threshold_tokens == 54321
