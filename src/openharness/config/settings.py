"""Settings model and loading logic for Velaris/OpenHarness compatibility mode.

Settings are resolved with the following precedence (highest first):
1. CLI arguments
2. Environment variables (VELARIS_*, ANTHROPIC_*, OPENHARNESS_*)
3. Config file (~/.velaris-agent/settings.json, compatible with legacy path)
4. Defaults
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from openharness.api.registry import infer_provider_spec, resolve_api_key_from_env
from openharness.hooks.schemas import HookDefinition
from openharness.mcp.types import McpServerConfig
from openharness.permissions.modes import PermissionMode


class PathRuleConfig(BaseModel):
    """A glob-pattern path permission rule."""

    pattern: str
    allow: bool = True


class PermissionSettings(BaseModel):
    """Permission mode configuration."""

    mode: PermissionMode = PermissionMode.DEFAULT
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    path_rules: list[PathRuleConfig] = Field(default_factory=list)
    denied_commands: list[str] = Field(default_factory=list)


class MemorySettings(BaseModel):
    """Memory system configuration."""

    enabled: bool = True
    max_files: int = 5
    max_entrypoint_lines: int = 200


class SkillsSettings(BaseModel):
    """Skills 系统配置。

    该配置控制技能索引注入与后台 review 的触发频率，
    用于把技能沉淀从“单次行为”变成稳定运行机制。
    """

    enabled: bool = True
    creation_nudge_interval: int = 10
    max_index_entries: int = 200


class SecuritySettings(BaseModel):
    """安全防护配置。

    该配置把高风险命令审批、上下文注入扫描和输出脱敏收敛到同一处，
    让 Bash、提示词装配和 MCP 子进程都能复用统一策略。
    """

    approval_mode: Literal["manual", "smart", "off"] = "manual"
    scan_project_instructions: bool = True
    redact_secrets: bool = True


class StorageSettings(BaseModel):
    """存储后端配置。

    这组配置只负责描述 PostgreSQL bootstrap 所需的连接与调度参数，
    便于后续任务在不引入额外基础设施的前提下复用同一份设置。
    """

    postgres_dsn: str = ""
    evidence_dir: str | None = None
    job_poll_interval_seconds: float = 2.0
    job_max_attempts: int = 3


class Settings(BaseModel):
    """Main settings model for OpenHarness."""

    # API configuration
    api_key: str = ""
    api_format: Literal["anthropic", "openai_compat"] = "anthropic"
    provider: str | None = None
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 16384
    base_url: str | None = None
    auto_compact_threshold_tokens: int | None = None

    # Behavior
    system_prompt: str | None = None
    permission: PermissionSettings = Field(default_factory=PermissionSettings)
    hooks: dict[str, list[HookDefinition]] = Field(default_factory=dict)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    skills: SkillsSettings = Field(default_factory=SkillsSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    enabled_plugins: dict[str, bool] = Field(default_factory=dict)
    mcp_servers: dict[str, McpServerConfig] = Field(default_factory=dict)

    # UI
    theme: str = "default"
    output_style: str = "default"
    vim_mode: bool = False
    voice_mode: bool = False
    fast_mode: bool = False
    effort: str = "medium"
    passes: int = 1
    verbose: bool = False

    def resolve_api_key(self) -> str:
        """Resolve API key with precedence: instance value > env var > empty.

        Returns the API key string. Raises ValueError if no key is found.
        """
        if self.api_key:
            return self.api_key

        env_key = resolve_api_key_from_env(
            provider_name=self.provider,
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            api_format=self.api_format,
        )
        if env_key:
            return env_key

        raise ValueError(
            "No API key found. Set VELARIS_API_KEY, provider-specific API key "
            "(for example ANTHROPIC_API_KEY / OPENAI_API_KEY / MOONSHOT_API_KEY), "
            "or configure api_key in ~/.velaris-agent/settings.json"
        )

    def merge_cli_overrides(self, **overrides: Any) -> Settings:
        """Return a new Settings with CLI overrides applied (non-None values only)."""
        updates = {k: v for k, v in overrides.items() if v is not None}
        return self.model_copy(update=updates)


def _apply_env_overrides(settings: Settings) -> Settings:
    """Apply supported environment variable overrides over loaded settings."""
    updates: dict[str, Any] = {}
    storage_updates: dict[str, Any] = {}
    provider = os.environ.get("VELARIS_PROVIDER") or os.environ.get("OPENHARNESS_PROVIDER")
    if provider:
        updates["provider"] = provider

    api_format = os.environ.get("VELARIS_API_FORMAT") or os.environ.get("OPENHARNESS_API_FORMAT")
    if api_format:
        updates["api_format"] = api_format

    model = (
        os.environ.get("ANTHROPIC_MODEL")
        or os.environ.get("VELARIS_MODEL")
        or os.environ.get("OPENHARNESS_MODEL")
    )
    if model:
        updates["model"] = model

    candidate = settings.model_copy(update=updates) if updates else settings
    provider_spec = infer_provider_spec(
        provider_name=candidate.provider,
        model=candidate.model,
        base_url=candidate.base_url,
        api_key=candidate.api_key,
        api_format=candidate.api_format,
    )
    base_url = (
        os.environ.get("VELARIS_BASE_URL")
        or os.environ.get("OPENHARNESS_BASE_URL")
        or (
            os.environ.get("ANTHROPIC_BASE_URL")
            if provider_spec.name == "anthropic"
            else ""
        )
    )
    if base_url:
        updates["base_url"] = base_url

    max_tokens = os.environ.get("VELARIS_MAX_TOKENS") or os.environ.get("OPENHARNESS_MAX_TOKENS")
    if max_tokens:
        updates["max_tokens"] = int(max_tokens)

    auto_compact_threshold_tokens = (
        os.environ.get("VELARIS_AUTO_COMPACT_THRESHOLD_TOKENS")
        or os.environ.get("OPENHARNESS_AUTO_COMPACT_THRESHOLD_TOKENS")
    )
    if auto_compact_threshold_tokens:
        updates["auto_compact_threshold_tokens"] = int(auto_compact_threshold_tokens)

    postgres_dsn = os.environ.get("VELARIS_POSTGRES_DSN")
    if postgres_dsn:
        storage_updates["postgres_dsn"] = postgres_dsn

    evidence_dir = os.environ.get("VELARIS_EVIDENCE_DIR")
    if evidence_dir:
        storage_updates["evidence_dir"] = evidence_dir

    if storage_updates:
        updates["storage"] = settings.storage.model_copy(update=storage_updates)

    candidate = settings.model_copy(update=updates) if updates else settings
    api_key = resolve_api_key_from_env(
        provider_name=candidate.provider,
        model=candidate.model,
        base_url=candidate.base_url,
        api_key=candidate.api_key,
        api_format=candidate.api_format,
    )
    if api_key:
        updates["api_key"] = api_key

    if not updates:
        return settings
    return settings.model_copy(update=updates)


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from config file, merging with defaults.

    Args:
        config_path: Path to settings.json. If None, uses the default location.

    Returns:
        Settings instance with file values merged over defaults.
    """
    if config_path is None:
        from openharness.config.paths import get_config_file_path

        config_path = get_config_file_path()

    if config_path.exists():
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        return _apply_env_overrides(Settings.model_validate(raw))

    return _apply_env_overrides(Settings())


def save_settings(settings: Settings, config_path: Path | None = None) -> None:
    """Persist settings to the config file.

    Args:
        settings: Settings instance to save.
        config_path: Path to write. If None, uses the default location.
    """
    if config_path is None:
        from openharness.config.paths import get_config_file_path

        config_path = get_config_file_path()

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        settings.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
