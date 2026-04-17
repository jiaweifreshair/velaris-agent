"""Tests for the Textual terminal UI."""

from __future__ import annotations

import pytest

from openharness.api.client import ApiMessageCompleteEvent
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock, ToolUseBlock
from openharness.mcp.types import McpConnectionStatus
from openharness.ui.textual_app import OpenHarnessTerminalApp, format_mcp_notice_markup


class StaticApiClient:
    """Fake streaming client for UI tests."""

    def __init__(self, text: str) -> None:
        self._text = text

    async def stream_message(self, request):
        del request
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text=self._text)]),
            usage=UsageSnapshot(input_tokens=2, output_tokens=3),
            stop_reason=None,
        )


class ScriptedApiClient:
    """Fake client that yields a scripted sequence of assistant turns."""

    def __init__(self, messages) -> None:
        self._messages = list(messages)

    async def stream_message(self, request):
        del request
        message = self._messages.pop(0)
        yield ApiMessageCompleteEvent(
            message=message,
            usage=UsageSnapshot(input_tokens=2, output_tokens=3),
            stop_reason=None,
        )


@pytest.mark.asyncio
async def test_textual_app_handles_commands(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    app = OpenHarnessTerminalApp(api_client=StaticApiClient("unused"))
    async with app.run_test() as pilot:
        composer = app.query_one("#composer")
        composer.value = "/version"
        await pilot.press("enter")
        await pilot.pause()

    assert any("OpenHarness" in line for line in app.transcript_lines)


@pytest.mark.asyncio
async def test_textual_app_runs_one_model_turn(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    app = OpenHarnessTerminalApp(api_client=StaticApiClient("hello from textual"))
    async with app.run_test() as pilot:
        composer = app.query_one("#composer")
        composer.value = "hi"
        await pilot.press("enter")
        await pilot.pause()

    assert any("user> hi" in line for line in app.transcript_lines)
    assert any("assistant> hello from textual" in line for line in app.transcript_lines)


@pytest.mark.asyncio
async def test_textual_app_handles_ask_user_tool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    app = OpenHarnessTerminalApp(
        api_client=ScriptedApiClient(
            [
                ConversationMessage(
                    role="assistant",
                    content=[
                        ToolUseBlock(
                            id="toolu_ask",
                            name="ask_user_question",
                            input={"question": "Pick a color"},
                        )
                    ],
                ),
                ConversationMessage(
                    role="assistant",
                    content=[TextBlock(text="chosen green")],
                ),
            ]
        )
    )

    async def _answer(question: str) -> str:
        assert question == "Pick a color"
        return "green"

    app._ask_question = _answer
    async with app.run_test() as pilot:
        composer = app.query_one("#composer")
        composer.value = "hi"
        await pilot.press("enter")
        await pilot.pause()

    assert any("tool-result> ask_user_question: green" in line for line in app.transcript_lines)
    assert any("assistant> chosen green" in line for line in app.transcript_lines)


@pytest.mark.asyncio
async def test_textual_status_bar_shows_mcp_notice(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    app = OpenHarnessTerminalApp(api_client=StaticApiClient("unused"))
    async with app.run_test() as pilot:
        assert app._bundle is not None
        app._bundle.app_state.set(mcp_notice="Auto-reconnect recovered after transport closed")
        app._refresh_sidebars()
        await pilot.pause()
        status_bar = app.query_one("#status-bar")

    assert "Auto-reconnect recovered after transport closed" in str(status_bar.content)


def test_format_mcp_notice_markup_colors_recovered_notice():
    """Textual 状态栏应把恢复类 MCP 提示渲染成绿色标签。"""

    markup = format_mcp_notice_markup("Auto-reconnect recovered after transport closed")

    assert "[green]" in markup
    assert "mcp recovered:" in markup


def test_format_mcp_notice_markup_colors_failed_notice():
    """Textual 状态栏应把失败类 MCP 提示渲染成红色标签。"""

    markup = format_mcp_notice_markup("Auto-reconnect failed: broken pipe")

    assert "[red]" in markup
    assert "mcp error:" in markup


def test_textual_mcp_panel_formats_per_server_notice_levels():
    """Textual MCP 面板应按每个 server 的详情级别分别着色。"""

    from openharness.ui.textual_app import format_mcp_server_panel_markup

    markup = format_mcp_server_panel_markup(
        [
            McpConnectionStatus(
                name="travel-ws",
                state="connected",
                detail="Auto-reconnect recovered after transport closed",
                transport="ws",
                auth_configured=True,
            ),
            McpConnectionStatus(
                name="maps-http",
                state="failed",
                detail="broken pipe",
                transport="http",
                auth_configured=False,
            ),
        ]
    )

    assert "travel-ws [connected] ws" in markup
    assert "[green]mcp recovered: Auto-reconnect recovered after transport closed[/green]" in markup
    assert "maps-http [failed] http" in markup
    assert "[red]mcp error: broken pipe[/red]" in markup
