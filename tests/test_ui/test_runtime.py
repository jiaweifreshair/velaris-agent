"""UI runtime 摘要输出测试。"""

from __future__ import annotations

from openharness.mcp.types import McpConnectionStatus, McpResourceInfo, McpToolInfo
from openharness.ui.runtime import RuntimeBundle, _summarize_mcp_notice_level


class _FakeMcpManager:
    """返回固定 MCP 状态的极简管理器桩。"""

    def __init__(self, statuses) -> None:
        self._statuses = statuses

    def list_statuses(self):
        return self._statuses


def test_runtime_bundle_mcp_summary_includes_transport_and_metadata():
    """MCP 摘要应展示 transport 以及工具/资源信息。"""

    bundle = RuntimeBundle(
        api_client=object(),
        cwd=".",
        mcp_manager=_FakeMcpManager(
            [
                McpConnectionStatus(
                    name="demo",
                    state="connected",
                    transport="ws",
                    auth_configured=True,
                    tools=[
                        McpToolInfo(
                            server_name="demo",
                            name="hello",
                            description="Say hello",
                            input_schema={"type": "object", "properties": {}},
                        )
                    ],
                    resources=[
                        McpResourceInfo(
                            server_name="demo",
                            name="Fixture Readme",
                            uri="fixture://readme",
                            description="fixture resource",
                        )
                    ],
                )
            ]
        ),
        tool_registry=object(),
        app_state=object(),
        hook_executor=object(),
        engine=object(),
        commands=object(),
        external_api_client=False,
    )

    summary = bundle.mcp_summary()

    assert "- demo [connected] ws" in summary
    assert "auth=True tools=1 resources=1" in summary
    assert "tool_names: hello" in summary
    assert "resource_uris: fixture://readme" in summary


def test_runtime_bundle_mcp_summary_labels_recovered_and_failed_notices():
    """纯文本 MCP 摘要应显式区分恢复提示与失败提示。"""

    bundle = RuntimeBundle(
        api_client=object(),
        cwd=".",
        mcp_manager=_FakeMcpManager(
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
        ),
        tool_registry=object(),
        app_state=object(),
        hook_executor=object(),
        engine=object(),
        commands=object(),
        external_api_client=False,
    )

    summary = bundle.mcp_summary()

    assert "mcp recovered: Auto-reconnect recovered after transport closed" in summary
    assert "mcp error: broken pipe" in summary


def test_summarize_mcp_notice_level_marks_recovered_notice_as_success():
    """Runtime 应显式把自动恢复提示归类为 success。"""

    level = _summarize_mcp_notice_level(
        [
            McpConnectionStatus(
                name="demo",
                state="connected",
                detail="Auto-reconnect recovered after transport closed",
                transport="ws",
            )
        ]
    )

    assert level == "success"


def test_summarize_mcp_notice_level_marks_failed_notice_as_error():
    """Runtime 应显式把失败提示归类为 error。"""

    level = _summarize_mcp_notice_level(
        [
            McpConnectionStatus(
                name="demo",
                state="failed",
                detail="broken pipe",
                transport="ws",
            )
        ]
    )

    assert level == "error"
