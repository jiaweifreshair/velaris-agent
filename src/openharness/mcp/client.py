"""MCP client manager."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, cast

import anyio
import httpx
import mcp.types as mcp_protocol_types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.message import SessionMessage
from mcp.types import CallToolResult, ReadResourceResult
from pydantic import ValidationError
from websockets.asyncio.client import connect as ws_connect
from websockets.typing import Subprotocol

from openharness.mcp.types import (
    McpConnectionStatus,
    McpHttpServerConfig,
    McpResourceInfo,
    McpStdioServerConfig,
    McpToolInfo,
    McpWebSocketServerConfig,
)
from openharness.security import (
    build_safe_mcp_env,
    redact_sensitive_text,
    sanitize_mcp_error,
    validate_workdir,
)


class McpServerNotConnectedError(RuntimeError):
    """表示 MCP 服务器未连接、已断连或底层传输已失效。"""


@asynccontextmanager
async def _websocket_client(
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> AsyncIterator[tuple[Any, Any]]:
    """创建支持自定义请求头的 MCP WebSocket 客户端传输。"""

    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

    async with ws_connect(
        url,
        subprotocols=[Subprotocol("mcp")],
        additional_headers=headers or None,
    ) as ws:

        async def ws_reader() -> None:
            """把服务端消息解析为 MCP SessionMessage 并推送到读流。"""

            async with read_stream_writer:
                async for raw_text in ws:
                    try:
                        message = mcp_protocol_types.JSONRPCMessage.model_validate_json(raw_text)
                        await read_stream_writer.send(SessionMessage(message))
                    except ValidationError as exc:  # pragma: no cover - 与上游实现保持一致
                        await read_stream_writer.send(exc)

        async def ws_writer() -> None:
            """把 MCP 写流中的消息序列化后发送到 WebSocket。"""

            async with write_stream_reader:
                async for session_message in write_stream_reader:
                    payload = session_message.message.model_dump(
                        by_alias=True,
                        mode="json",
                        exclude_none=True,
                    )
                    await ws.send(json.dumps(payload))

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(ws_reader)
            task_group.start_soon(ws_writer)
            yield (read_stream, write_stream)
            task_group.cancel_scope.cancel()


class McpClientManager:
    """Manage MCP connections and expose tools/resources."""

    def __init__(self, server_configs: dict[str, object]) -> None:
        self._server_configs = server_configs
        self._statuses: dict[str, McpConnectionStatus] = {
            name: McpConnectionStatus(
                name=name,
                state="pending",
                transport=getattr(config, "type", "unknown"),
            )
            for name, config in server_configs.items()
        }
        self._sessions: dict[str, ClientSession] = {}
        self._stacks: dict[str, AsyncExitStack] = {}
        self._reconnect_locks: dict[str, asyncio.Lock] = {}

    async def connect_all(self) -> None:
        """Connect all configured MCP servers supported by the current build."""
        for name, config in self._server_configs.items():
            await self._connect_server(name, config)

    async def reconnect_all(self) -> None:
        """Reconnect all configured servers."""
        await self.close()
        self._statuses = {
            name: McpConnectionStatus(name=name, state="pending", transport=getattr(config, "type", "unknown"))
            for name, config in self._server_configs.items()
        }
        await self.connect_all()

    def update_server_config(self, name: str, config: object) -> None:
        """Replace one server config in memory."""
        self._server_configs[name] = config

    def get_server_config(self, name: str) -> object | None:
        """Return one configured server object if present."""
        return self._server_configs.get(name)

    async def close(self) -> None:
        """Close all active MCP sessions."""
        for stack in list(self._stacks.values()):
            with contextlib.suppress(RuntimeError, asyncio.CancelledError):
                await stack.aclose()
        self._stacks.clear()
        self._sessions.clear()

    def list_statuses(self) -> list[McpConnectionStatus]:
        """Return statuses for all configured servers."""
        return [self._statuses[name] for name in sorted(self._statuses)]

    def list_tools(self) -> list[McpToolInfo]:
        """Return all connected MCP tools."""
        tools: list[McpToolInfo] = []
        for status in self.list_statuses():
            tools.extend(status.tools)
        return tools

    def list_resources(self) -> list[McpResourceInfo]:
        """Return all connected MCP resources."""
        resources: list[McpResourceInfo] = []
        for status in self.list_statuses():
            resources.extend(status.resources)
        return resources

    def _auth_configured(self, config: object | None) -> bool:
        """推断一条 MCP 配置当前是否显式带有鉴权信息。"""

        if config is None:
            return False
        headers = getattr(config, "headers", None)
        if headers:
            return True
        env = getattr(config, "env", None)
        return bool(env)

    def _pending_status(self, name: str, config: object | None) -> McpConnectionStatus:
        """构造单个 MCP server 的 pending 状态。"""

        return McpConnectionStatus(
            name=name,
            state="pending",
            transport=getattr(config, "type", "unknown"),
            auth_configured=self._auth_configured(config),
        )

    def _set_status_detail(self, server_name: str, detail: str) -> None:
        """更新单个 server 的状态详情，供 UI 显示最近一次重连结果。"""

        status = self._statuses.get(server_name)
        if status is not None:
            status.detail = detail

    async def _close_server(self, server_name: str) -> None:
        """关闭并移除单个 MCP server 的底层会话与退出栈。"""

        stack = self._stacks.pop(server_name, None)
        self._sessions.pop(server_name, None)
        if stack is not None:
            with contextlib.suppress(RuntimeError, asyncio.CancelledError):
                await stack.aclose()

    async def _connect_server(self, name: str, config: object) -> None:
        """按配置类型连接单个 server，供 connect/reconnect 复用。"""

        if isinstance(config, McpStdioServerConfig):
            await self._connect_stdio(name, config)
            return
        if isinstance(config, McpHttpServerConfig):
            await self._connect_http(name, config)
            return
        if isinstance(config, McpWebSocketServerConfig):
            await self._connect_ws(name, config)
            return

        transport = str(getattr(config, "type", "unknown"))
        self._statuses[name] = McpConnectionStatus(
            name=name,
            state="failed",
            transport=transport,
            auth_configured=self._auth_configured(config),
            detail=f"Unsupported MCP transport in current build: {transport}",
        )

    def _reconnect_delay(self, attempt: int, base_delay: float) -> float:
        """计算单个 server 自动重连的指数退避时间。"""

        safe_base = max(0.0, base_delay)
        return safe_base * (2 ** max(0, attempt - 1))

    async def reconnect_server(
        self,
        server_name: str,
        *,
        attempts: int = 2,
        base_delay: float = 0.1,
    ) -> bool:
        """按 server 粒度重连 MCP 连接，失败时使用指数退避。"""

        config = self._server_configs.get(server_name)
        if config is None:
            return False

        lock = self._reconnect_locks.setdefault(server_name, asyncio.Lock())
        async with lock:
            initial_status = self._statuses.get(server_name)
            last_error = sanitize_mcp_error((initial_status.detail or "").strip()) if initial_status else ""
            if server_name in self._sessions and self._statuses.get(server_name, None) and self._statuses[
                server_name
            ].state == "connected":
                return True

            total_attempts = max(1, attempts)
            for attempt in range(1, total_attempts + 1):
                await self._close_server(server_name)
                self._statuses[server_name] = self._pending_status(server_name, config)
                try:
                    await self._connect_server(server_name, config)
                except Exception as exc:
                    last_error = sanitize_mcp_error(str(exc))
                    self._statuses[server_name] = McpConnectionStatus(
                        name=server_name,
                        state="failed",
                        transport=getattr(config, "type", "unknown"),
                        auth_configured=self._auth_configured(config),
                        detail=last_error,
                    )

                status = self._statuses.get(server_name)
                if (
                    status is not None
                    and status.state == "connected"
                    and server_name in self._sessions
                ):
                    if last_error:
                        self._set_status_detail(
                            server_name,
                            f"Auto-reconnect recovered after {last_error}",
                        )
                    return True

                if attempt < total_attempts:
                    await asyncio.sleep(self._reconnect_delay(attempt, base_delay))

            if last_error:
                self._set_status_detail(server_name, f"Auto-reconnect failed: {last_error}")
            return False

    async def _get_session_with_reconnect(self, server_name: str) -> ClientSession:
        """优先复用现有会话；若缺失则尝试对单个 server 做懒重连。"""

        session = self._sessions.get(server_name)
        if session is not None:
            return session

        if server_name in self._server_configs:
            reconnected = await self.reconnect_server(server_name)
            if reconnected:
                session = self._sessions.get(server_name)
                if session is not None:
                    return session

        return self._require_session(server_name)

    def _require_session(self, server_name: str) -> ClientSession:
        """读取一个仍可用的 MCP 会话，不存在时抛出稳定错误。"""

        session = self._sessions.get(server_name)
        if session is not None:
            return session

        status = self._statuses.get(server_name)
        if status is None:
            detail = "unknown server"
        elif status.detail:
            detail = status.detail
        else:
            detail = "not connected"
        raise McpServerNotConnectedError(
            f"MCP server '{server_name}' is not connected: {detail}"
        )

    async def _mark_session_broken(self, server_name: str, detail: str) -> None:
        """把失效会话降级为 failed，避免后续重复复用坏连接。"""

        await self._close_server(server_name)

        previous = self._statuses.get(server_name)
        self._statuses[server_name] = McpConnectionStatus(
            name=server_name,
            state="failed",
            detail=detail,
            transport=previous.transport if previous is not None else "unknown",
            auth_configured=previous.auth_configured if previous is not None else False,
            tools=list(previous.tools) if previous is not None else [],
            resources=list(previous.resources) if previous is not None else [],
        )

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> str:
        """Invoke one MCP tool and stringify the result."""
        session = await self._get_session_with_reconnect(server_name)
        try:
            result: CallToolResult = await session.call_tool(tool_name, arguments)
        except Exception as exc:
            detail = sanitize_mcp_error(str(exc))
            await self._mark_session_broken(server_name, detail)
            if await self.reconnect_server(server_name):
                retry_session = self._require_session(server_name)
                try:
                    result = await retry_session.call_tool(tool_name, arguments)
                except Exception as retry_exc:
                    retry_detail = sanitize_mcp_error(str(retry_exc))
                    await self._mark_session_broken(server_name, retry_detail)
                    raise McpServerNotConnectedError(
                        f"MCP server '{server_name}' call failed: {retry_detail}"
                    ) from retry_exc
            else:
                raise McpServerNotConnectedError(
                    f"MCP server '{server_name}' call failed: {detail}"
                ) from exc
        parts: list[str] = []
        for item in result.content:
            if getattr(item, "type", None) == "text":
                parts.append(getattr(item, "text", ""))
            else:
                parts.append(item.model_dump_json())
        if result.structuredContent and not parts:
            parts.append(str(result.structuredContent))
        if not parts:
            parts.append("(no output)")
        return redact_sensitive_text("\n".join(parts).strip())

    async def read_resource(self, server_name: str, uri: str) -> str:
        """Read one MCP resource and stringify the response."""
        session = await self._get_session_with_reconnect(server_name)
        try:
            result: ReadResourceResult = await session.read_resource(cast(Any, uri))
        except Exception as exc:
            detail = sanitize_mcp_error(str(exc))
            await self._mark_session_broken(server_name, detail)
            if await self.reconnect_server(server_name):
                retry_session = self._require_session(server_name)
                try:
                    result = await retry_session.read_resource(cast(Any, uri))
                except Exception as retry_exc:
                    retry_detail = sanitize_mcp_error(str(retry_exc))
                    await self._mark_session_broken(server_name, retry_detail)
                    raise McpServerNotConnectedError(
                        f"MCP server '{server_name}' resource read failed: {retry_detail}"
                    ) from retry_exc
            else:
                raise McpServerNotConnectedError(
                    f"MCP server '{server_name}' resource read failed: {detail}"
                ) from exc
        parts: list[str] = []
        for item in result.contents:
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(text)
            else:
                parts.append(str(getattr(item, "blob", "")))
        return redact_sensitive_text("\n".join(parts).strip())

    async def _connect_stdio(self, name: str, config: McpStdioServerConfig) -> None:
        stack = AsyncExitStack()
        try:
            workdir_error = validate_workdir(config.cwd or "")
            if workdir_error is not None:
                self._statuses[name] = McpConnectionStatus(
                    name=name,
                    state="failed",
                    transport=config.type,
                    auth_configured=bool(config.env),
                    detail=workdir_error,
                )
                return

            read_stream, write_stream = await stack.enter_async_context(
                stdio_client(
                    StdioServerParameters(
                        command=config.command,
                        args=config.args,
                        env=build_safe_mcp_env(config.env),
                        cwd=config.cwd,
                    )
                )
            )
            await self._register_connected_session(
                name=name,
                config=config,
                stack=stack,
                read_stream=read_stream,
                write_stream=write_stream,
                auth_configured=bool(config.env),
            )
        except Exception as exc:
            await stack.aclose()
            self._statuses[name] = McpConnectionStatus(
                name=name,
                state="failed",
                transport=config.type,
                auth_configured=bool(config.env),
                detail=sanitize_mcp_error(str(exc)),
            )

    async def _connect_http(self, name: str, config: McpHttpServerConfig) -> None:
        """通过 streamable HTTP 连接远端 MCP 服务。"""

        stack = AsyncExitStack()
        try:
            http_client = await stack.enter_async_context(
                httpx.AsyncClient(headers=config.headers or None)
            )
            read_stream, write_stream, _get_session_id = await stack.enter_async_context(
                streamable_http_client(config.url, http_client=http_client)
            )
            await self._register_connected_session(
                name=name,
                config=config,
                stack=stack,
                read_stream=read_stream,
                write_stream=write_stream,
                auth_configured=bool(config.headers),
            )
        except Exception as exc:
            await stack.aclose()
            self._statuses[name] = McpConnectionStatus(
                name=name,
                state="failed",
                transport=config.type,
                auth_configured=bool(config.headers),
                detail=sanitize_mcp_error(str(exc)),
            )

    async def _connect_ws(self, name: str, config: McpWebSocketServerConfig) -> None:
        """通过 WebSocket 连接远端 MCP 服务。"""

        stack = AsyncExitStack()
        try:
            read_stream, write_stream = await stack.enter_async_context(
                _websocket_client(config.url, headers=config.headers or None)
            )
            await self._register_connected_session(
                name=name,
                config=config,
                stack=stack,
                read_stream=read_stream,
                write_stream=write_stream,
                auth_configured=bool(config.headers),
            )
        except Exception as exc:
            await stack.aclose()
            self._statuses[name] = McpConnectionStatus(
                name=name,
                state="failed",
                transport=config.type,
                auth_configured=bool(config.headers),
                detail=sanitize_mcp_error(str(exc)),
            )

    async def _register_connected_session(
        self,
        *,
        name: str,
        config: object,
        stack: AsyncExitStack,
        read_stream: Any,
        write_stream: Any,
        auth_configured: bool,
    ) -> None:
        """注册已建立底层传输的 MCP 会话，并统一发现工具/资源。"""

        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        tool_result = await session.list_tools()
        resource_result = None
        try:
            resource_result = await session.list_resources()
        except Exception as exc:
            if "Method not found" not in str(exc):
                raise
        tools = [
            McpToolInfo(
                server_name=name,
                name=tool.name,
                description=tool.description or "",
                input_schema=dict(tool.inputSchema or {"type": "object", "properties": {}}),
            )
            for tool in tool_result.tools
        ]
        resources = [
            McpResourceInfo(
                server_name=name,
                name=resource.name or str(resource.uri),
                uri=str(resource.uri),
                description=resource.description or "",
            )
            for resource in (resource_result.resources if resource_result is not None else [])
        ]
        self._sessions[name] = session
        self._stacks[name] = stack
        self._statuses[name] = McpConnectionStatus(
            name=name,
            state="connected",
            transport=getattr(config, "type", "unknown"),
            auth_configured=auth_configured,
            tools=tools,
            resources=resources,
        )
