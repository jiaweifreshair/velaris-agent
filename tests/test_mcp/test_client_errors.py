"""MCP 客户端断连与错误包装测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from mcp.types import CallToolResult, ReadResourceResult, TextContent, TextResourceContents

from openharness.mcp.client import McpClientManager, McpServerNotConnectedError
from openharness.mcp.types import McpConnectionStatus, McpStdioServerConfig, McpToolInfo
from openharness.tools.base import ToolExecutionContext
from openharness.tools.mcp_tool import McpToolAdapter
from openharness.tools.read_mcp_resource_tool import ReadMcpResourceTool


@pytest.mark.asyncio
async def test_call_tool_raises_when_server_never_connected():
    """未连接服务器调用工具时，应返回稳定的 not connected 错误。"""

    manager = McpClientManager({})

    with pytest.raises(McpServerNotConnectedError, match="not connected"):
        await manager.call_tool("missing", "hello", {})


@pytest.mark.asyncio
async def test_call_tool_raises_when_server_failed_to_connect():
    """重连仍失败时，call_tool 应返回最新的连接失败详情。"""

    manager = McpClientManager({"bad": McpStdioServerConfig(command="false", args=[])})
    manager._statuses["bad"] = McpConnectionStatus(
        name="bad",
        state="failed",
        detail="Connection refused",
        transport="stdio",
    )

    with pytest.raises(McpServerNotConnectedError, match="Connection (refused|closed)"):
        await manager.call_tool("bad", "hello", {})


@pytest.mark.asyncio
async def test_call_tool_raises_when_session_errors():
    """运行中的传输异常应被包装成稳定的 MCP 连接错误。"""

    manager = McpClientManager({})
    session = AsyncMock()
    session.call_tool.side_effect = RuntimeError("transport closed")
    manager._sessions["flaky"] = session

    with pytest.raises(McpServerNotConnectedError, match="transport closed"):
        await manager.call_tool("flaky", "hello", {})


@pytest.mark.asyncio
async def test_read_resource_raises_when_server_never_connected():
    """未连接服务器读取资源时，应返回稳定的 not connected 错误。"""

    manager = McpClientManager({})

    with pytest.raises(McpServerNotConnectedError, match="not connected"):
        await manager.read_resource("missing", "fixture://readme")


@pytest.mark.asyncio
async def test_read_resource_raises_when_session_errors():
    """资源读取阶段的底层异常应被包装成稳定错误。"""

    manager = McpClientManager({})
    session = AsyncMock()
    session.read_resource.side_effect = OSError("broken pipe")
    manager._sessions["flaky"] = session

    with pytest.raises(McpServerNotConnectedError, match="broken pipe"):
        await manager.read_resource("flaky", "fixture://readme")


@pytest.mark.asyncio
async def test_mcp_tool_adapter_returns_error_result_on_disconnected_server():
    """MCP 工具适配层遇到断连时，应返回 is_error 结果而不是抛异常。"""

    manager = McpClientManager({})
    tool_info = McpToolInfo(
        server_name="missing",
        name="hello",
        description="Say hello",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    )
    adapter = McpToolAdapter(manager, tool_info)

    result = await adapter.execute(
        adapter.input_model.model_validate({"name": "world"}),
        ToolExecutionContext(cwd=Path(".")),
    )

    assert result.is_error is True
    assert "not connected" in result.output


@pytest.mark.asyncio
async def test_read_mcp_resource_tool_returns_error_result_on_disconnected_server():
    """资源读取工具遇到断连时，应返回 is_error 结果而不是抛异常。"""

    manager = McpClientManager({})
    tool = ReadMcpResourceTool(manager)

    result = await tool.execute(
        tool.input_model.model_validate({"server": "missing", "uri": "fixture://readme"}),
        ToolExecutionContext(cwd=Path(".")),
    )

    assert result.is_error is True
    assert "not connected" in result.output


@pytest.mark.asyncio
async def test_call_tool_reconnects_missing_session_before_failing(monkeypatch):
    """存在配置但当前无会话时，call_tool 应先尝试按 server 自动重连。"""

    manager = McpClientManager({"demo": McpStdioServerConfig(command="python", args=["-m", "fixture"])})
    manager._statuses["demo"] = McpConnectionStatus(
        name="demo",
        state="failed",
        detail="transport closed",
        transport="stdio",
    )
    recovered_session = AsyncMock()
    recovered_session.call_tool.return_value = CallToolResult(
        content=[TextContent(type="text", text="recovered:hello")]
    )
    reconnect_calls: list[str] = []

    async def fake_reconnect_server(name: str, *, attempts: int = 2, base_delay: float = 0.1) -> bool:
        reconnect_calls.append(name)
        manager._sessions[name] = recovered_session
        manager._statuses[name] = McpConnectionStatus(name=name, state="connected", transport="stdio")
        return True

    monkeypatch.setattr(manager, "reconnect_server", fake_reconnect_server)

    result = await manager.call_tool("demo", "hello", {})

    assert result == "recovered:hello"
    assert reconnect_calls == ["demo"]


@pytest.mark.asyncio
async def test_call_tool_reconnects_after_transport_error_and_retries(monkeypatch):
    """已连接会话在调用期断开时，call_tool 应自动重连并重试一次。"""

    manager = McpClientManager({"demo": McpStdioServerConfig(command="python", args=["-m", "fixture"])})
    broken_session = AsyncMock()
    broken_session.call_tool.side_effect = RuntimeError("transport closed")
    manager._sessions["demo"] = broken_session
    manager._statuses["demo"] = McpConnectionStatus(name="demo", state="connected", transport="stdio")

    recovered_session = AsyncMock()
    recovered_session.call_tool.return_value = CallToolResult(
        content=[TextContent(type="text", text="recovered:tool")]
    )

    async def fake_reconnect_server(name: str, *, attempts: int = 2, base_delay: float = 0.1) -> bool:
        manager._sessions[name] = recovered_session
        manager._statuses[name] = McpConnectionStatus(name=name, state="connected", transport="stdio")
        return True

    monkeypatch.setattr(manager, "reconnect_server", fake_reconnect_server)

    result = await manager.call_tool("demo", "hello", {})

    assert result == "recovered:tool"
    assert manager.list_statuses()[0].state == "connected"


@pytest.mark.asyncio
async def test_read_resource_reconnects_after_transport_error_and_retries(monkeypatch):
    """资源读取阶段断开连接时，也应按 server 自动重连并重试。"""

    manager = McpClientManager({"demo": McpStdioServerConfig(command="python", args=["-m", "fixture"])})
    broken_session = AsyncMock()
    broken_session.read_resource.side_effect = OSError("broken pipe")
    manager._sessions["demo"] = broken_session
    manager._statuses["demo"] = McpConnectionStatus(name="demo", state="connected", transport="stdio")

    recovered_session = AsyncMock()
    recovered_session.read_resource.return_value = ReadResourceResult(
        contents=[
            TextResourceContents(
                uri="fixture://readme",
                text="recovered:resource",
                mimeType="text/plain",
            )
        ]
    )

    async def fake_reconnect_server(name: str, *, attempts: int = 2, base_delay: float = 0.1) -> bool:
        manager._sessions[name] = recovered_session
        manager._statuses[name] = McpConnectionStatus(name=name, state="connected", transport="stdio")
        return True

    monkeypatch.setattr(manager, "reconnect_server", fake_reconnect_server)

    result = await manager.read_resource("demo", "fixture://readme")

    assert result == "recovered:resource"
    assert manager.list_statuses()[0].state == "connected"


@pytest.mark.asyncio
async def test_reconnect_server_retries_with_backoff(monkeypatch):
    """reconnect_server 应在失败后按指数退避重试单个 server。"""

    manager = McpClientManager({"demo": McpStdioServerConfig(command="python", args=["-m", "fixture"])})
    attempts: list[str] = []
    sleeps: list[float] = []

    async def fake_connect_server(name: str, config: object) -> None:
        attempts.append(name)
        if len(attempts) < 2:
            raise RuntimeError("temporary failure")
        manager._sessions[name] = AsyncMock()
        manager._statuses[name] = McpConnectionStatus(name=name, state="connected", transport="stdio")

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(manager, "_connect_server", fake_connect_server)
    monkeypatch.setattr("openharness.mcp.client.asyncio.sleep", fake_sleep)

    reconnected = await manager.reconnect_server("demo", attempts=2, base_delay=0.25)

    assert reconnected is True
    assert attempts == ["demo", "demo"]
    assert sleeps == [0.25]
