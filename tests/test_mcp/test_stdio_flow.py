"""Real stdio MCP integration tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from openharness.mcp.client import McpClientManager
from openharness.mcp.types import McpStdioServerConfig
from openharness.security import build_safe_mcp_env, sanitize_mcp_error
from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolExecutionContext


@pytest.mark.asyncio
async def test_stdio_mcp_manager_connects_and_executes_real_server():
    server_script = Path(__file__).resolve().parents[1] / "fixtures" / "fake_mcp_server.py"
    manager = McpClientManager(
        {
            "fixture": McpStdioServerConfig(
                command=sys.executable,
                args=[str(server_script)],
            )
        }
    )
    await manager.connect_all()
    try:
        statuses = manager.list_statuses()
        assert len(statuses) == 1
        assert statuses[0].state == "connected"
        assert statuses[0].tools[0].name == "hello"
        assert statuses[0].resources[0].uri == "fixture://readme"

        registry = create_default_tool_registry(manager)
        hello_tool = registry.get("mcp__fixture__hello")
        assert hello_tool is not None
        hello_result = await hello_tool.execute(
            hello_tool.input_model.model_validate({"name": "world"}),
            ToolExecutionContext(cwd=Path(".")),
        )
        assert hello_result.output == "fixture-hello:world"

        resource_tool = registry.get("read_mcp_resource")
        assert resource_tool is not None
        resource_result = await resource_tool.execute(
            resource_tool.input_model.model_validate(
                {"server": "fixture", "uri": "fixture://readme"}
            ),
            ToolExecutionContext(cwd=Path(".")),
        )
        assert "fixture resource contents" in resource_result.output
    finally:
        await manager.close()


def test_build_safe_mcp_env_filters_process_secrets(monkeypatch):
    """MCP stdio 子进程只应继承安全基础变量和显式配置项。"""

    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/tmp/home")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-secret")

    env = build_safe_mcp_env({"MCP_AUTH_TOKEN": "demo-token"})

    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/tmp/home"
    assert env["MCP_AUTH_TOKEN"] == "demo-token"
    assert "OPENAI_API_KEY" not in env


def test_sanitize_mcp_error_redacts_secret_values():
    """MCP 连接错误中的凭据不应直接暴露给状态面板或模型。"""

    text = "connect failed with Bearer secret-token and ghp_abcdefghijk"
    sanitized = sanitize_mcp_error(text)

    assert "[REDACTED]" in sanitized
    assert "secret-token" not in sanitized
