"""动态技能命令注入测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.api.client import ApiMessageCompleteEvent
from openharness.api.usage import UsageSnapshot
from openharness.commands import create_default_command_registry
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.engine.query_engine import QueryEngine
from openharness.permissions import PermissionChecker
from openharness.config.settings import PermissionSettings
from openharness.state import AppState, AppStateStore
from openharness.tools import create_default_tool_registry
from openharness.ui.runtime import RuntimeBundle, handle_line


class RecordingApiClient:
    """记录请求内容的假客户端。"""

    def __init__(self) -> None:
        self.requests: list[str] = []

    async def stream_message(self, request):
        self.requests.append(request.messages[-1].content[0].text)
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="ok")]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


class _StubMcpManager:
    """最小 MCP 管理器桩对象。"""

    def list_statuses(self) -> list[object]:
        return []


@pytest.mark.asyncio
async def test_handle_line_injects_skill_content_for_dynamic_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """`/skill-name` 应被转换为携带完整技能内容的用户消息。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    skill_dir = tmp_path / "config" / "skills" / "incident-review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            "name: incident-review\n"
            "description: 线上事故复盘流程\n"
            "---\n\n"
            "# Incident Review\n\n"
            "先补时间线，再列行动项。\n"
        ),
        encoding="utf-8",
    )

    api_client = RecordingApiClient()
    tool_registry = create_default_tool_registry()
    bundle = RuntimeBundle(
        api_client=api_client,
        cwd=str(tmp_path),
        mcp_manager=_StubMcpManager(),  # type: ignore[arg-type]
        tool_registry=tool_registry,
        app_state=AppStateStore(
            AppState(model="claude-test", permission_mode="default", theme="default", keybindings={})
        ),
        hook_executor=None,  # type: ignore[arg-type]
        engine=QueryEngine(
            api_client=api_client,
            tool_registry=tool_registry,
            permission_checker=PermissionChecker(PermissionSettings()),
            cwd=tmp_path,
            model="claude-test",
            system_prompt="system",
            skill_review_interval=0,
        ),
        commands=create_default_command_registry(),
        external_api_client=True,
        session_id="test-session",
    )

    async def _print_system(message: str) -> None:
        del message

    async def _render_event(event) -> None:
        del event

    async def _clear_output() -> None:
        return None

    keep_running = await handle_line(
        bundle,
        "/incident-review 帮我复盘昨晚故障",
        print_system=_print_system,
        render_event=_render_event,
        clear_output=_clear_output,
    )

    assert keep_running is True
    assert api_client.requests
    injected = api_client.requests[0]
    assert '用户显式调用了技能 "incident-review"' in injected
    assert "先补时间线，再列行动项。" in injected
    assert "帮我复盘昨晚故障" in injected
