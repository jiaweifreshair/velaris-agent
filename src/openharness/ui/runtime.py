"""Shared runtime assembly for headless and Textual UIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable
from uuid import uuid4

from openharness.api.client import AnthropicApiClient, SupportsStreamingMessages
from openharness.api.registry import infer_provider_spec
from openharness.api.provider import auth_status, detect_provider
from openharness.bridge import get_bridge_manager
from openharness.commands import CommandContext, CommandResult, create_default_command_registry
from openharness.config import get_config_file_path, load_settings
from openharness.engine import QueryEngine
from openharness.engine.stream_events import StreamEvent
from openharness.hooks import HookEvent, HookExecutionContext, HookExecutor, load_hook_registry
from openharness.hooks.hot_reload import HookReloader
from openharness.mcp.client import McpClientManager
from openharness.mcp.config import load_mcp_server_configs
from openharness.permissions import PermissionChecker
from openharness.plugins import load_plugins
from openharness.prompts import build_runtime_system_prompt
from openharness.security import SecuritySessionState
from openharness.state import AppState, AppStateStore
from openharness.ui.mcp_notice import format_mcp_server_text_summary, summarize_mcp_notice_entry
from openharness.services.session_storage import save_session_snapshot
from openharness.skills.commands import (
    build_skill_invocation_message,
    resolve_skill_command,
)
from openharness.tools import ToolRegistry, create_default_tool_registry
from openharness.keybindings import load_keybindings

PermissionPrompt = Callable[[str, str], Awaitable[bool]]
AskUserPrompt = Callable[[str], Awaitable[str]]
SystemPrinter = Callable[[str], Awaitable[None]]
StreamRenderer = Callable[[StreamEvent], Awaitable[None]]
ClearHandler = Callable[[], Awaitable[None]]


def _build_api_client(settings) -> SupportsStreamingMessages:
    """根据当前设置选择 API 客户端。

    当 provider 或 `api_format` 指向 OpenAI-compatible 网关时，
    切到兼容客户端；否则继续走现有 Anthropic 路径。
    """

    spec = infer_provider_spec(
        provider_name=settings.provider,
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        api_format=settings.api_format,
    )
    resolved_base_url = settings.base_url or spec.default_base_url or None
    if spec.api_format == "openai_compat":
        from openharness.api.openai_client import OpenAICompatibleClient

        return OpenAICompatibleClient(
            api_key=settings.resolve_api_key(),
            base_url=resolved_base_url,
        )
    return AnthropicApiClient(
        api_key=settings.resolve_api_key(),
        base_url=resolved_base_url,
    )


@dataclass
class RuntimeBundle:
    """Shared runtime objects for one interactive session."""

    api_client: SupportsStreamingMessages
    cwd: str
    mcp_manager: McpClientManager
    tool_registry: ToolRegistry
    app_state: AppStateStore
    hook_executor: HookExecutor
    engine: QueryEngine
    commands: object
    external_api_client: bool
    session_id: str = ""
    settings_overrides: dict[str, object] = field(default_factory=dict)

    def current_settings(self):
        """返回本会话的有效设置。

        磁盘配置负责提供长期默认值，CLI 传入的 provider/model 等覆盖项
        需要在整个会话里持续生效，避免 UI 刷新后“跳回”旧配置。
        """

        return load_settings().merge_cli_overrides(**self.settings_overrides)

    def current_plugins(self):
        """Return currently visible plugins for the working tree."""
        return load_plugins(self.current_settings(), self.cwd)

    def hook_summary(self) -> str:
        """Return the current hook summary."""
        return load_hook_registry(self.current_settings(), self.current_plugins()).summary()

    def plugin_summary(self) -> str:
        """Return the current plugin summary."""
        plugins = self.current_plugins()
        if not plugins:
            return "No plugins discovered."
        lines = ["Plugins:"]
        for plugin in plugins:
            state = "enabled" if plugin.enabled else "disabled"
            lines.append(f"- {plugin.manifest.name} [{state}] {plugin.manifest.description}")
        return "\n".join(lines)

    def mcp_summary(self) -> str:
        """Return the current MCP summary."""
        return format_mcp_server_text_summary(self.mcp_manager.list_statuses())


def _summarize_mcp_notice_entry(statuses) -> tuple[str, str]:
    """提炼最近一次 MCP 提示及其语义级别。"""

    return summarize_mcp_notice_entry(statuses)


def _summarize_mcp_notice(statuses) -> str:
    """提炼最近一次 MCP 提示文本，供状态栏直接展示。"""

    return _summarize_mcp_notice_entry(statuses)[0]


def _summarize_mcp_notice_level(statuses) -> str:
    """提炼最近一次 MCP 提示的语义级别，供前后端统一渲染。"""

    return _summarize_mcp_notice_entry(statuses)[1]



async def build_runtime(
    *,
    prompt: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    api_format: str | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    api_key: str | None = None,
    auto_compact_threshold_tokens: int | None = None,
    api_client: SupportsStreamingMessages | None = None,
    permission_prompt: PermissionPrompt | None = None,
    ask_user_prompt: AskUserPrompt | None = None,
) -> RuntimeBundle:
    """Build the shared runtime for an OpenHarness session."""
    settings_overrides = {
        "model": model,
        "provider": provider,
        "api_format": api_format,
        "base_url": base_url,
        "system_prompt": system_prompt,
        "api_key": api_key,
        "auto_compact_threshold_tokens": auto_compact_threshold_tokens,
    }
    settings = load_settings().merge_cli_overrides(**settings_overrides)
    cwd = str(Path.cwd())
    session_id = uuid4().hex[:12]
    plugins = load_plugins(settings, cwd)
    resolved_api_client = api_client or _build_api_client(settings)
    mcp_manager = McpClientManager(load_mcp_server_configs(settings, plugins))
    await mcp_manager.connect_all()
    tool_registry = create_default_tool_registry(mcp_manager)
    provider = detect_provider(settings)
    bridge_manager = get_bridge_manager()
    security_session_state = SecuritySessionState()
    app_state = AppStateStore(
        AppState(
            model=settings.model,
            permission_mode=settings.permission.mode.value,
            theme=settings.theme,
            cwd=cwd,
            provider=provider.name,
            auth_status=auth_status(settings),
            base_url=settings.base_url or "",
            vim_enabled=settings.vim_mode,
            voice_enabled=settings.voice_mode,
            voice_available=provider.voice_supported,
            voice_reason=provider.voice_reason,
            fast_mode=settings.fast_mode,
            effort=settings.effort,
            passes=settings.passes,
            mcp_connected=sum(1 for status in mcp_manager.list_statuses() if status.state == "connected"),
            mcp_failed=sum(1 for status in mcp_manager.list_statuses() if status.state == "failed"),
            mcp_notice=_summarize_mcp_notice(mcp_manager.list_statuses()),
            mcp_notice_level=_summarize_mcp_notice_level(mcp_manager.list_statuses()),
            bridge_sessions=len(bridge_manager.list_sessions()),
            output_style=settings.output_style,
            keybindings=load_keybindings(),
        )
    )
    hook_reloader = HookReloader(get_config_file_path())
    hook_executor = HookExecutor(
        hook_reloader.current_registry() if api_client is None else load_hook_registry(settings, plugins),
        HookExecutionContext(
            cwd=Path(cwd).resolve(),
            api_client=resolved_api_client,
            default_model=settings.model,
            security_settings=settings.security,
            security_session_state=security_session_state,
            permission_prompt=permission_prompt,
        ),
    )
    engine = QueryEngine(
        api_client=resolved_api_client,
        tool_registry=tool_registry,
        permission_checker=PermissionChecker(settings.permission),
        cwd=cwd,
        model=settings.model,
        system_prompt=build_runtime_system_prompt(settings, cwd=cwd, latest_user_prompt=prompt),
        max_tokens=settings.max_tokens,
        auto_compact_threshold_tokens=settings.auto_compact_threshold_tokens,
        permission_prompt=permission_prompt,
        ask_user_prompt=ask_user_prompt,
        hook_executor=hook_executor,
        tool_metadata={
            "mcp_manager": mcp_manager,
            "bridge_manager": bridge_manager,
            "security_settings": settings.security,
            "security_session_state": security_session_state,
            "session_id": session_id,
        },
        skill_review_interval=settings.skills.creation_nudge_interval,
    )

    return RuntimeBundle(
        api_client=resolved_api_client,
        cwd=cwd,
        mcp_manager=mcp_manager,
        tool_registry=tool_registry,
        app_state=app_state,
        hook_executor=hook_executor,
        engine=engine,
        commands=create_default_command_registry(),
        external_api_client=api_client is not None,
        session_id=session_id,
        settings_overrides={k: v for k, v in settings_overrides.items() if v is not None},
    )


async def start_runtime(bundle: RuntimeBundle) -> None:
    """Run session start hooks."""
    await bundle.hook_executor.execute(
        HookEvent.SESSION_START,
        {"cwd": bundle.cwd, "event": HookEvent.SESSION_START.value},
    )


async def close_runtime(bundle: RuntimeBundle) -> None:
    """Close runtime-owned resources."""
    await bundle.engine.wait_for_background_tasks()
    await bundle.mcp_manager.close()
    await bundle.hook_executor.execute(
        HookEvent.SESSION_END,
        {"cwd": bundle.cwd, "event": HookEvent.SESSION_END.value},
    )


def sync_app_state(bundle: RuntimeBundle) -> None:
    """Refresh UI state from current settings and dynamic keybindings."""
    settings = bundle.current_settings()
    provider = detect_provider(settings)
    bundle.app_state.set(
        model=settings.model,
        permission_mode=settings.permission.mode.value,
        theme=settings.theme,
        cwd=bundle.cwd,
        provider=provider.name,
        auth_status=auth_status(settings),
        base_url=settings.base_url or "",
        vim_enabled=settings.vim_mode,
        voice_enabled=settings.voice_mode,
        voice_available=provider.voice_supported,
        voice_reason=provider.voice_reason,
        fast_mode=settings.fast_mode,
        effort=settings.effort,
        passes=settings.passes,
        mcp_connected=sum(1 for status in bundle.mcp_manager.list_statuses() if status.state == "connected"),
        mcp_failed=sum(1 for status in bundle.mcp_manager.list_statuses() if status.state == "failed"),
        mcp_notice=_summarize_mcp_notice(bundle.mcp_manager.list_statuses()),
        mcp_notice_level=_summarize_mcp_notice_level(bundle.mcp_manager.list_statuses()),
        bridge_sessions=len(get_bridge_manager().list_sessions()),
        output_style=settings.output_style,
        keybindings=load_keybindings(),
    )


async def handle_line(
    bundle: RuntimeBundle,
    line: str,
    *,
    print_system: SystemPrinter,
    render_event: StreamRenderer,
    clear_output: ClearHandler,
) -> bool:
    """Handle one submitted line for either headless or TUI rendering."""
    if not bundle.external_api_client:
        bundle.hook_executor.update_registry(
            load_hook_registry(bundle.current_settings(), bundle.current_plugins())
        )

    parsed = bundle.commands.lookup(line)
    if parsed is not None:
        command, args = parsed
        result = await command.handler(
            args,
            CommandContext(
                engine=bundle.engine,
                hooks_summary=bundle.hook_summary(),
                mcp_summary=bundle.mcp_summary(),
                plugin_summary=bundle.plugin_summary(),
                cwd=bundle.cwd,
                tool_registry=bundle.tool_registry,
                app_state=bundle.app_state,
            ),
        )
        await _render_command_result(result, print_system, clear_output, render_event)
        sync_app_state(bundle)
        return not result.should_exit

    submitted_line = line
    if line.startswith("/"):
        command_name, _, command_args = line.partition(" ")
        matched_skill = resolve_skill_command(command_name, bundle.cwd)
        if matched_skill is not None:
            submitted_line = build_skill_invocation_message(
                matched_skill,
                user_instruction=command_args,
            )

    settings = bundle.current_settings()
    bundle.engine.set_system_prompt(
        build_runtime_system_prompt(settings, cwd=bundle.cwd, latest_user_prompt=line)
    )
    async for event in bundle.engine.submit_message(submitted_line):
        await render_event(event)
    save_session_snapshot(
        cwd=bundle.cwd,
        model=settings.model,
        system_prompt=build_runtime_system_prompt(settings, cwd=bundle.cwd, latest_user_prompt=line),
        messages=bundle.engine.messages,
        usage=bundle.engine.total_usage,
        session_id=bundle.session_id,
    )
    sync_app_state(bundle)
    return True


async def _render_command_result(
    result: CommandResult,
    print_system: SystemPrinter,
    clear_output: ClearHandler,
    render_event: StreamRenderer | None = None,
) -> None:
    if result.clear_screen:
        await clear_output()
    if result.replay_messages and render_event is not None:
        # Replay restored conversation messages as transcript events
        from openharness.engine.stream_events import AssistantTextDelta, AssistantTurnComplete
        from openharness.api.usage import UsageSnapshot

        await clear_output()
        await print_system("Session restored:")
        for msg in result.replay_messages:
            if msg.role == "user":
                await print_system(f"> {msg.text}")
            elif msg.role == "assistant" and msg.text.strip():
                await render_event(AssistantTextDelta(text=msg.text))
                await render_event(AssistantTurnComplete(message=msg, usage=UsageSnapshot()))
    if result.message and not result.replay_messages:
        await print_system(result.message)
