"""MCP 提示辅助函数，供 runtime、协议层和终端 UI 复用。"""

from __future__ import annotations

from collections.abc import Iterable

from openharness.mcp.types import McpConnectionStatus

_ERROR_TOKENS = (
    "fail",
    "error",
    "denied",
    "timeout",
    "timed out",
    "broken pipe",
    "disconnected",
    "not connected",
)
_SUCCESS_TOKENS = (
    "recover",
    "reconnected",
    "restored",
    "connected",
)


# 统一 MCP notice 的语义级别，避免多个 UI 模块各自猜测同一条状态文案。
_McpNoticeLevel = str


def infer_mcp_notice_level(state: str, detail: str, explicit_level: str | None = None) -> _McpNoticeLevel:
    """根据状态、详情和可选显式级别推断 MCP 提示语义。

    优先信任显式传入的级别；若没有，再结合运行时状态与 detail 文案兜底。
    """

    normalized_level = (explicit_level or "").strip().lower()
    if normalized_level in {"error", "failed", "failure"}:
        return "error"
    if normalized_level in {"success", "ok", "recovered"}:
        return "success"
    if normalized_level in {"warning", "warn", "notice", "info"}:
        return "warning"

    lowered = detail.lower()
    if state == "failed" or any(token in lowered for token in _ERROR_TOKENS):
        return "error"
    if state == "connected" or any(token in lowered for token in _SUCCESS_TOKENS):
        return "success"
    return "warning"


def summarize_mcp_notice_entry(statuses: Iterable[McpConnectionStatus]) -> tuple[str, str]:
    """提炼最近一次值得展示的 MCP 提示及其级别。"""

    status_list = list(statuses)
    for status in status_list:
        detail = (status.detail or "").strip()
        lowered = detail.lower()
        if detail and ("auto-reconnect" in lowered or "reconnect" in lowered or "recovered" in lowered):
            return detail, infer_mcp_notice_level(status.state, detail)
    for status in status_list:
        detail = (status.detail or "").strip()
        if status.state == "failed" and detail:
            return detail, "error"
    return "", ""


def format_mcp_notice_text(message: str, level: str | None = None) -> str:
    """把 MCP notice 格式化成纯文本标签，供 slash command 与摘要输出复用。"""

    normalized_level = infer_mcp_notice_level("pending", message, level)
    if normalized_level == "error":
        return f"mcp error: {message}"
    if normalized_level == "success":
        return f"mcp recovered: {message}"
    return f"mcp notice: {message}"


def format_mcp_notice_markup(message: str, level: str | None = None) -> str:
    """把 MCP notice 格式化成 Textual 可直接渲染的彩色 markup。"""

    normalized_level = infer_mcp_notice_level("pending", message, level)
    if normalized_level == "error":
        return f"[red]{format_mcp_notice_text(message, normalized_level)}[/red]"
    if normalized_level == "success":
        return f"[green]{format_mcp_notice_text(message, normalized_level)}[/green]"
    return f"[yellow]{format_mcp_notice_text(message, normalized_level)}[/yellow]"


def format_mcp_server_text_summary(statuses: Iterable[McpConnectionStatus]) -> str:
    """生成纯文本 MCP 摘要，显式标注每个 server 的详情语义。"""

    status_list = list(statuses)
    if not status_list:
        return "No MCP servers configured."

    lines = ["MCP servers:"]
    for status in status_list:
        lines.append(f"- {status.name} [{status.state}] {status.transport}")
        lines.append(
            f"  auth={bool(status.auth_configured)} tools={len(status.tools)} resources={len(status.resources)}"
        )
        if status.detail:
            lines.append(f"  {format_mcp_notice_text(status.detail, infer_mcp_notice_level(status.state, status.detail))}")
        if status.tools:
            lines.append(f"  tool_names: {', '.join(tool.name for tool in status.tools)}")
        if status.resources:
            lines.append(f"  resource_uris: {', '.join(resource.uri for resource in status.resources)}")
    return "\n".join(lines)


def format_mcp_server_panel_markup(statuses: Iterable[McpConnectionStatus]) -> str:
    """生成 Textual MCP 面板的逐 server markup 文本。

    每个 server 保留原始连接信息，并对 detail 行补充语义着色，方便快速定位
    哪个 server 刚恢复、哪个 server 仍然失败。
    """

    status_list = list(statuses)
    if not status_list:
        return "[b]MCP[/b]\n(none)"

    lines = ["[b]MCP[/b]"]
    for status in status_list[:5]:
        lines.append(f"{status.name} [{status.state}] {status.transport}")
        lines.append(
            f"[dim]auth={bool(status.auth_configured)} tools={len(status.tools)} resources={len(status.resources)}[/dim]"
        )
        if status.detail:
            lines.append(format_mcp_notice_markup(status.detail, infer_mcp_notice_level(status.state, status.detail)))
    return "\n".join(lines)


__all__ = [
    "format_mcp_notice_markup",
    "format_mcp_notice_text",
    "format_mcp_server_panel_markup",
    "format_mcp_server_text_summary",
    "infer_mcp_notice_level",
    "summarize_mcp_notice_entry",
]
