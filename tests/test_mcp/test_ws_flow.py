"""WebSocket MCP transport 行为测试。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from openharness.mcp import client as mcp_client_module
from openharness.mcp.client import McpClientManager
from openharness.mcp.types import McpWebSocketServerConfig


class _FakeClientSession:
    """模拟 MCP ClientSession，覆盖初始化、工具发现与资源发现。"""

    def __init__(
        self,
        read_stream: object,
        write_stream: object,
        *,
        resource_error: Exception | None = None,
    ) -> None:
        self.read_stream = read_stream
        self.write_stream = write_stream
        self.resource_error = resource_error
        self.initialized = False

    async def __aenter__(self) -> _FakeClientSession:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def initialize(self) -> None:
        self.initialized = True

    async def list_tools(self):
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="hello",
                    description="Say hello",
                    inputSchema={"type": "object", "properties": {}},
                )
            ]
        )

    async def list_resources(self):
        if self.resource_error is not None:
            raise self.resource_error
        return SimpleNamespace(
            resources=[
                SimpleNamespace(
                    name="Readme",
                    uri="demo://readme",
                    description="fixture resource",
                )
            ]
        )


@pytest.mark.asyncio
async def test_ws_mcp_manager_connects_and_collects_metadata(monkeypatch):
    """WebSocket MCP 服务器应能连接成功，并透传 headers 到握手层。"""

    captured: dict[str, object] = {}

    @asynccontextmanager
    async def fake_websocket_client(url, *, headers=None):
        """模拟 ws 传输层，记录 URL 与 headers 便于断言。"""

        captured["url"] = url
        captured["headers"] = headers
        yield ("read-stream", "write-stream")

    def fake_client_session(read_stream, write_stream):
        """构造可控的 MCP 会话桩，避免依赖真实远端服务。"""

        return _FakeClientSession(read_stream, write_stream)

    monkeypatch.setattr(
        mcp_client_module,
        "_websocket_client",
        fake_websocket_client,
        raising=False,
    )
    monkeypatch.setattr(mcp_client_module, "ClientSession", fake_client_session)

    manager = McpClientManager(
        {
            "demo": McpWebSocketServerConfig(
                url="wss://example.com/mcp",
                headers={"Authorization": "Bearer secret"},
            )
        }
    )

    await manager.connect_all()

    statuses = manager.list_statuses()
    assert len(statuses) == 1
    assert statuses[0].state == "connected"
    assert statuses[0].transport == "ws"
    assert statuses[0].auth_configured is True
    assert statuses[0].tools[0].name == "hello"
    assert statuses[0].resources[0].uri == "demo://readme"
    assert captured["url"] == "wss://example.com/mcp"
    assert captured["headers"] == {"Authorization": "Bearer secret"}

    await manager.close()


@pytest.mark.asyncio
async def test_ws_mcp_manager_tolerates_missing_list_resources(monkeypatch):
    """当服务端未实现 list_resources 时，ws MCP 连接仍应保持可用。"""

    @asynccontextmanager
    async def fake_websocket_client(url, *, headers=None):
        """模拟 WebSocket 握手成功，但不依赖真实网络。"""

        yield ("read-stream", "write-stream")

    def fake_client_session(read_stream, write_stream):
        """构造一个在资源发现阶段返回 Method not found 的会话桩。"""

        return _FakeClientSession(
            read_stream,
            write_stream,
            resource_error=RuntimeError("Method not found"),
        )

    monkeypatch.setattr(
        mcp_client_module,
        "_websocket_client",
        fake_websocket_client,
        raising=False,
    )
    monkeypatch.setattr(mcp_client_module, "ClientSession", fake_client_session)

    manager = McpClientManager({"demo": McpWebSocketServerConfig(url="wss://example.com/mcp")})

    await manager.connect_all()

    statuses = manager.list_statuses()
    assert statuses[0].state == "connected"
    assert statuses[0].tools[0].name == "hello"
    assert statuses[0].resources == []

    await manager.close()
