"""HTTP MCP transport 行为测试。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from openharness.mcp import client as mcp_client_module
from openharness.mcp.client import McpClientManager
from openharness.mcp.types import McpHttpServerConfig


class _FakeHttpClient:
    """记录 HTTP 头部的极简客户端桩，便于断言鉴权透传。"""

    def __init__(self, headers: dict[str, str] | None) -> None:
        self.headers = headers


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
async def test_http_mcp_manager_connects_and_collects_metadata(monkeypatch):
    """HTTP MCP 服务器应能连接成功，并暴露工具与资源元数据。"""

    captured: dict[str, object] = {}

    @asynccontextmanager
    async def fake_async_client(*, headers=None):
        """模拟 `httpx.AsyncClient`，记录透传头部便于断言。"""

        captured["headers"] = headers
        yield _FakeHttpClient(headers)

    @asynccontextmanager
    async def fake_streamable_http_client(url, *, http_client=None, terminate_on_close=True):
        """模拟 streamable HTTP 传输层，返回固定读写流。"""

        captured["url"] = url
        captured["http_client"] = http_client
        captured["terminate_on_close"] = terminate_on_close
        yield ("read-stream", "write-stream", lambda: "session-1")

    def fake_client_session(read_stream, write_stream):
        """构造可控的 MCP 会话桩，避免依赖真实远端服务。"""

        return _FakeClientSession(read_stream, write_stream)

    monkeypatch.setattr(
        mcp_client_module,
        "httpx",
        SimpleNamespace(AsyncClient=fake_async_client),
        raising=False,
    )
    monkeypatch.setattr(
        mcp_client_module,
        "streamable_http_client",
        fake_streamable_http_client,
        raising=False,
    )
    monkeypatch.setattr(mcp_client_module, "ClientSession", fake_client_session)

    manager = McpClientManager(
        {
            "demo": McpHttpServerConfig(
                url="https://example.com/mcp",
                headers={"Authorization": "Bearer secret"},
            )
        }
    )

    await manager.connect_all()

    statuses = manager.list_statuses()
    assert len(statuses) == 1
    assert statuses[0].state == "connected"
    assert statuses[0].transport == "http"
    assert statuses[0].auth_configured is True
    assert statuses[0].tools[0].name == "hello"
    assert statuses[0].resources[0].uri == "demo://readme"
    assert captured["headers"] == {"Authorization": "Bearer secret"}
    assert captured["url"] == "https://example.com/mcp"

    await manager.close()


@pytest.mark.asyncio
async def test_http_mcp_manager_tolerates_missing_list_resources(monkeypatch):
    """当服务端未实现 list_resources 时，HTTP MCP 连接仍应保持可用。"""

    @asynccontextmanager
    async def fake_async_client(*, headers=None):
        """模拟不带鉴权头部的 HTTP 客户端上下文。"""

        yield _FakeHttpClient(headers)

    @asynccontextmanager
    async def fake_streamable_http_client(url, *, http_client=None, terminate_on_close=True):
        """模拟 HTTP 传输建立，但刻意不提供真实网络依赖。"""

        yield ("read-stream", "write-stream", lambda: "session-2")

    def fake_client_session(read_stream, write_stream):
        """构造一个在资源发现阶段返回 Method not found 的会话桩。"""

        return _FakeClientSession(
            read_stream,
            write_stream,
            resource_error=RuntimeError("Method not found"),
        )

    monkeypatch.setattr(
        mcp_client_module,
        "httpx",
        SimpleNamespace(AsyncClient=fake_async_client),
        raising=False,
    )
    monkeypatch.setattr(
        mcp_client_module,
        "streamable_http_client",
        fake_streamable_http_client,
        raising=False,
    )
    monkeypatch.setattr(mcp_client_module, "ClientSession", fake_client_session)

    manager = McpClientManager({"demo": McpHttpServerConfig(url="https://example.com/mcp")})

    await manager.connect_all()

    statuses = manager.list_statuses()
    assert statuses[0].state == "connected"
    assert statuses[0].tools[0].name == "hello"
    assert statuses[0].resources == []

    await manager.close()
