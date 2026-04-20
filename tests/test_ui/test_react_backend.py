"""Tests for the React backend host protocol."""

from __future__ import annotations

import pytest

from openharness.api.client import ApiMessageCompleteEvent
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.mcp.types import McpConnectionStatus, McpResourceInfo, McpToolInfo
from openharness.ui.backend_host import BackendHostConfig, ReactBackendHost, run_backend_host
from openharness.ui.runtime import build_runtime, close_runtime, start_runtime


class StaticApiClient:
    """Fake streaming client for backend host tests."""

    def __init__(self, text: str) -> None:
        self._text = text

    async def stream_message(self, request):
        del request
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text=self._text)]),
            usage=UsageSnapshot(input_tokens=2, output_tokens=3),
            stop_reason=None,
        )


class StaticMcpManager:
    """返回固定 MCP 状态，供 React backend 端到端快照测试使用。"""

    def __init__(self, statuses) -> None:
        self._statuses = statuses

    def list_statuses(self):
        return self._statuses

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_run_backend_host_propagates_runtime_overrides(tmp_path, monkeypatch):
    """后端 host 包装器应把 provider 相关覆盖项传给运行时配置。"""

    captured: dict[str, BackendHostConfig] = {}
    monkeypatch.chdir(tmp_path)

    class FakeHost:
        def __init__(self, config: BackendHostConfig) -> None:
            captured["config"] = config

        async def run(self) -> int:
            return 0

    monkeypatch.setattr("openharness.ui.backend_host.ReactBackendHost", FakeHost)

    result = await run_backend_host(
        cwd=str(tmp_path),
        model="gpt-5.4",
        provider="openai",
        api_format="openai_compat",
        base_url="https://api.openai.com/v1",
        system_prompt="system",
        api_key="secret",
        auto_compact_threshold_tokens=2048,
        api_client=StaticApiClient("unused"),
    )

    assert result == 0
    config = captured["config"]
    assert config.model == "gpt-5.4"
    assert config.provider == "openai"
    assert config.api_format == "openai_compat"
    assert config.base_url == "https://api.openai.com/v1"
    assert config.system_prompt == "system"
    assert config.api_key == "secret"
    assert config.auto_compact_threshold_tokens == 2048


@pytest.mark.asyncio
async def test_backend_host_processes_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))
    host._bundle = await build_runtime(api_client=StaticApiClient("unused"))
    events = []

    async def _emit(event):
        events.append(event)

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        should_continue = await host._process_line("/version")
    finally:
        await close_runtime(host._bundle)

    assert should_continue is True
    assert any(event.type == "transcript_item" and event.item and event.item.role == "user" for event in events)
    assert any(
        event.type == "transcript_item"
        and event.item
        and event.item.role == "system"
        and "OpenHarness" in event.item.text
        for event in events
    )
    assert any(event.type == "state_snapshot" for event in events)


@pytest.mark.asyncio
async def test_backend_host_processes_model_turn(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("hello from react backend")))
    host._bundle = await build_runtime(api_client=StaticApiClient("hello from react backend"))
    events = []

    async def _emit(event):
        events.append(event)

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        should_continue = await host._process_line("hi")
    finally:
        await close_runtime(host._bundle)

    assert should_continue is True
    assert any(
        event.type == "assistant_complete" and event.message == "hello from react backend"
        for event in events
    )
    assert any(
        event.type == "assistant_complete"
        and event.item
        and event.item.role == "assistant"
        and "hello from react backend" in event.item.text
        for event in events
    )


@pytest.mark.asyncio
async def test_backend_host_status_snapshot_includes_ws_mcp_metadata(tmp_path, monkeypatch):
    """React backend 在 `/mcp` 后应把 ws transport 状态快照发给前端。"""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))
    host._bundle = await build_runtime(api_client=StaticApiClient("unused"))
    host._bundle.mcp_manager = StaticMcpManager(
        [
            McpConnectionStatus(
                name="travel-ws",
                state="connected",
                detail="Auto-reconnect recovered after transport closed",
                transport="ws",
                auth_configured=True,
                tools=[
                    McpToolInfo(
                        server_name="travel-ws",
                        name="search_flights",
                        description="Search flights",
                        input_schema={"type": "object", "properties": {}},
                    )
                ],
                resources=[
                    McpResourceInfo(
                        server_name="travel-ws",
                        name="Travel Guide",
                        uri="travel://guide",
                        description="guide",
                    )
                ],
            )
        ]
    )
    events = []

    async def _emit(event):
        events.append(event)

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        should_continue = await host._process_line("/mcp")
    finally:
        await close_runtime(host._bundle)

    assert should_continue is True
    assert any(
        event.type == "transcript_item"
        and event.item
        and event.item.role == "system"
        and "travel-ws [connected] ws" in event.item.text
        and "auth=True tools=1 resources=1" in event.item.text
        for event in events
    )
    assert any(
        event.type == "state_snapshot"
        and event.mcp_servers
        and event.mcp_servers[0]["name"] == "travel-ws"
        and event.state
        and event.state["mcp_notice"] == "Auto-reconnect recovered after transport closed"
        and event.state["mcp_notice_level"] == "success"
        and event.mcp_servers[0]["detail_level"] == "success"
        and event.mcp_servers[0]["transport"] == "ws"
        and event.mcp_servers[0]["tool_count"] == 1
        and event.mcp_servers[0]["resource_count"] == 1
        for event in events
    )
