"""真实 WebSocket MCP 夹具集成测试。"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

import mcp.types as types
import pytest
import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.websocket import websocket_server

from openharness.mcp.client import McpClientManager
from openharness.mcp.types import McpWebSocketServerConfig


def _build_ws_fixture_app(captured: dict[str, Any]):
    """构造一个最小可用的真实 MCP WebSocket ASGI 夹具。"""

    server = Server("fixture-ws")

    @server.list_tools()
    async def list_tools():
        """暴露一个 hello 工具供客户端发现。"""

        return [
            types.Tool(
                name="hello",
                description="Say hello from ws fixture",
                inputSchema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, object]):
        """执行 hello 工具并返回文本结果。"""

        if name != "hello":
            raise ValueError(f"Unknown tool: {name}")
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=f"fixture-hello:{arguments.get('name', '')}",
                )
            ]
        )

    @server.list_resources()
    async def list_resources():
        """暴露一个简单文本资源。"""

        return [
            types.Resource(
                name="Fixture Readme",
                uri="fixture://readme",
                description="fixture resource",
                mimeType="text/plain",
            )
        ]

    @server.read_resource()
    async def read_resource(uri):
        """读取固定资源内容。"""

        if str(uri) != "fixture://readme":
            raise ValueError(f"Unknown resource: {uri}")
        return "fixture resource contents"

    async def app(scope, receive, send):
        """提供 `/mcp` WebSocket 端点，供真实客户端接入。"""

        if scope["type"] != "websocket" or scope["path"] != "/mcp":
            raise RuntimeError(f"Unexpected ASGI scope: {scope['type']} {scope.get('path')}")
        captured["headers"] = {
            key.decode("utf-8"): value.decode("utf-8")
            for key, value in scope.get("headers", [])
        }
        async with websocket_server(scope, receive, send) as (
            read_stream,
            write_stream,
        ):
            await server.run(
                read_stream,
                write_stream,
                initialization_options=server.create_initialization_options(),
                raise_exceptions=True,
            )

    return app


async def _start_uvicorn_server(app, port: int) -> tuple[uvicorn.Server, asyncio.Task[None]]:
    """启动测试专用的 uvicorn WebSocket 服务。"""

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    for _ in range(200):
        if server.started:
            return server, task
        await asyncio.sleep(0.01)

    server.should_exit = True
    with suppress(Exception):
        await task
    raise RuntimeError("Timed out waiting for ws MCP fixture to start")


async def _stop_uvicorn_server(server: uvicorn.Server, task: asyncio.Task[None]) -> None:
    """优雅关闭测试用 uvicorn 服务。"""

    server.should_exit = True
    with suppress(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_ws_mcp_manager_works_against_real_websocket_fixture(unused_tcp_port):
    """WebSocket MCP 客户端应能连通真实夹具并完成工具/资源调用。"""

    captured: dict[str, Any] = {}
    server, task = await _start_uvicorn_server(_build_ws_fixture_app(captured), unused_tcp_port)
    manager = McpClientManager(
        {
            "fixture": McpWebSocketServerConfig(
                url=f"ws://127.0.0.1:{unused_tcp_port}/mcp",
                headers={"x-velaris-test": "ws-secret"},
            )
        }
    )

    try:
        await manager.connect_all()

        statuses = manager.list_statuses()
        assert len(statuses) == 1
        assert statuses[0].state == "connected"
        assert statuses[0].transport == "ws"
        assert statuses[0].tools[0].name == "hello"
        assert statuses[0].resources[0].uri == "fixture://readme"
        assert captured["headers"]["x-velaris-test"] == "ws-secret"

        tool_result = await manager.call_tool("fixture", "hello", {"name": "world"})
        resource_result = await manager.read_resource("fixture", "fixture://readme")

        assert tool_result == "fixture-hello:world"
        assert resource_result == "fixture resource contents"
    finally:
        await manager.close()
        await _stop_uvicorn_server(server, task)
