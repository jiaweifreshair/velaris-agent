"""Interactive session entry points."""

from __future__ import annotations

import json
import sys

from openharness.api.client import SupportsStreamingMessages
from openharness.engine.stream_events import StreamEvent
from openharness.ui.backend_host import run_backend_host
from openharness.ui.react_launcher import launch_react_tui
from openharness.ui.runtime import build_runtime, close_runtime, handle_line, start_runtime


_API_KEY_GUIDE = """\

  Velaris 需要 API Key 才能启动交互会话。

  配置方式 (任选其一):

    1. 统一初始化 (推荐):
       velaris setup anthropic --model claude-sonnet-4 --use-env
       velaris setup moonshot --model kimi-k2 --use-env

    2. 环境变量:
       export VELARIS_API_KEY="sk-ant-..."
       # 或
       export ANTHROPIC_API_KEY="sk-ant-..."
       # OpenAI-compatible provider 也支持:
       export OPENAI_API_KEY="sk-..."
       export MOONSHOT_API_KEY="..."

    3. 配置文件:
       echo '{"api_key": "sk-ant-..."}' > ~/.velaris-agent/settings.json

    4. Provider / 鉴权子命令:
       velaris provider use moonshot
       velaris auth status
       velaris auth login moonshot --api-key sk-...
       velaris auth login moonshot --use-env

    5. OpenHarness 兼容入口:
       oh provider current
       openharness auth status

  不需要 API Key 也可以运行本地 Demo:
    velaris demo lifegoal
    velaris demo lifegoal --json

"""


def _print_api_key_guide(exc: Exception) -> None:
    """输出友好的 API Key 配置引导，替代原始 traceback。"""
    print(_API_KEY_GUIDE, file=sys.stderr)


async def run_repl(
    *,
    prompt: str | None = None,
    cwd: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    api_format: str | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    api_key: str | None = None,
    auto_compact_threshold_tokens: int | None = None,
    api_client: SupportsStreamingMessages | None = None,
    backend_only: bool = False,
    demo_mode: str | None = None,
    demo_case_index: int | None = None,
    demo_cases: list[dict[str, object]] | None = None,
) -> None:
    """Run the default OpenHarness interactive application (React TUI)."""
    if backend_only:
        try:
            await run_backend_host(
                cwd=cwd,
                model=model,
                provider=provider,
                api_format=api_format,
                base_url=base_url,
                system_prompt=system_prompt,
                api_key=api_key,
                auto_compact_threshold_tokens=auto_compact_threshold_tokens,
                api_client=api_client,
            )
        except ValueError as exc:
            _print_api_key_guide(exc)
            raise SystemExit(1) from exc
        return

    try:
        exit_code = await launch_react_tui(
            prompt=prompt,
            cwd=cwd,
            model=model,
            provider=provider,
            api_format=api_format,
            base_url=base_url,
            system_prompt=system_prompt,
            api_key=api_key,
            auto_compact_threshold_tokens=auto_compact_threshold_tokens,
            demo_mode=demo_mode,
            demo_case_index=demo_case_index,
            demo_cases=demo_cases,
        )
    except ValueError as exc:
        _print_api_key_guide(exc)
        raise SystemExit(1) from exc
    if exit_code != 0:
        raise SystemExit(exit_code)


async def run_print_mode(
    *,
    prompt: str,
    output_format: str = "text",
    cwd: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    api_format: str | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    append_system_prompt: str | None = None,
    api_key: str | None = None,
    auto_compact_threshold_tokens: int | None = None,
    api_client: SupportsStreamingMessages | None = None,
    permission_mode: str | None = None,
    max_turns: int | None = None,
) -> None:
    """Non-interactive mode: submit prompt, stream output, exit."""
    from openharness.engine.stream_events import (
        AssistantTextDelta,
        AssistantTurnComplete,
        ToolExecutionCompleted,
        ToolExecutionStarted,
    )

    async def _noop_permission(tool_name: str, reason: str) -> bool:
        return True

    async def _noop_ask(question: str) -> str:
        return ""

    try:
        bundle = await build_runtime(
            prompt=prompt,
            model=model,
            provider=provider,
            api_format=api_format,
            base_url=base_url,
            system_prompt=system_prompt,
            api_key=api_key,
            auto_compact_threshold_tokens=auto_compact_threshold_tokens,
            api_client=api_client,
            permission_prompt=_noop_permission,
            ask_user_prompt=_noop_ask,
        )
    except ValueError as exc:
        _print_api_key_guide(exc)
        raise SystemExit(1) from exc
    await start_runtime(bundle)

    collected_text = ""
    events_list: list[dict] = []

    try:
        async def _print_system(message: str) -> None:
            nonlocal collected_text
            if output_format == "text":
                print(message, file=sys.stderr)
            elif output_format == "stream-json":
                obj = {"type": "system", "message": message}
                print(json.dumps(obj), flush=True)
                events_list.append(obj)

        async def _render_event(event: StreamEvent) -> None:
            nonlocal collected_text
            if isinstance(event, AssistantTextDelta):
                collected_text += event.text
                if output_format == "text":
                    sys.stdout.write(event.text)
                    sys.stdout.flush()
                elif output_format == "stream-json":
                    obj = {"type": "assistant_delta", "text": event.text}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)
            elif isinstance(event, AssistantTurnComplete):
                if output_format == "text":
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                elif output_format == "stream-json":
                    obj = {"type": "assistant_complete", "text": event.message.text.strip()}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)
            elif isinstance(event, ToolExecutionStarted):
                if output_format == "stream-json":
                    obj = {"type": "tool_started", "tool_name": event.tool_name, "tool_input": event.tool_input}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)
            elif isinstance(event, ToolExecutionCompleted):
                if output_format == "stream-json":
                    obj = {"type": "tool_completed", "tool_name": event.tool_name, "output": event.output, "is_error": event.is_error}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)

        async def _clear_output() -> None:
            pass

        await handle_line(
            bundle,
            prompt,
            print_system=_print_system,
            render_event=_render_event,
            clear_output=_clear_output,
        )

        if output_format == "json":
            result = {"type": "result", "text": collected_text.strip()}
            print(json.dumps(result))
    finally:
        await close_runtime(bundle)
