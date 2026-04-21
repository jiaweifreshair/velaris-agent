"""CLI entry point using typer."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import typer

from openharness.commands.skills_cli import skills_app

if TYPE_CHECKING:
    from openharness.api.registry import ProviderSpec

app = typer.Typer(
    name="velaris",
    help=(
        "Velaris Agent Python runtime，基于 OpenHarness 运行时能力扩展。\n\n"
        "默认启动交互会话，使用 -p/--print 可切换为单次输出模式。\n"
        "迁移期保留 `oh` 与 `openharness` 兼容入口，但品牌与默认入口保持为 Velaris。"
    ),
    add_completion=False,
    rich_markup_mode="rich",
    invoke_without_command=True,
)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

mcp_app = typer.Typer(name="mcp", help="管理 MCP 服务器配置（支持 stdio / http / ws）")
provider_app = typer.Typer(name="provider", help="管理 provider 预设（list/current/use）")
plugin_app = typer.Typer(name="plugin", help="管理插件")
auth_app = typer.Typer(name="auth", help="管理 provider 感知的鉴权状态")
demo_app = typer.Typer(name="demo", help="运行本地内置 Demo")
storage_app = typer.Typer(name="storage", help="管理项目内 SQLite 存储（bootstrap/doctor/jobs）")
storage_jobs_app = typer.Typer(name="jobs", help="运行最小后台任务 worker")

app.add_typer(mcp_app)
app.add_typer(provider_app)
app.add_typer(plugin_app)
app.add_typer(auth_app)
app.add_typer(demo_app)
app.add_typer(storage_app)
storage_app.add_typer(storage_jobs_app)
app.add_typer(skills_app)


def _resolve_setup_provider(name: str | None, default_provider: str) -> ProviderSpec:
    """解析 setup 目标 provider。

    支持直接传 provider 名称；若用户未传，则展示内置列表并允许输入编号，
    这样既兼容脚本场景，也兼容首次初始化时的交互式体验。
    """

    from openharness.api.registry import get_provider_spec, list_provider_specs

    if name:
        spec = get_provider_spec(name)
        if spec is None:
            print(f"Unknown provider: {name}", file=sys.stderr)
            raise typer.Exit(1)
        return spec

    specs = list_provider_specs()
    print("请选择要配置的 provider：", flush=True)
    for index, spec in enumerate(specs, start=1):
        marker = "*" if spec.name == default_provider else " "
        print(f" {marker} {index}. {spec.display_name} [{spec.name}]", flush=True)

    raw = typer.prompt("输入编号或 provider 名称", default=default_provider)
    try:
        position = int(raw.strip()) - 1
    except ValueError:
        position = -1
    if 0 <= position < len(specs):
        return specs[position]

    spec = get_provider_spec(raw)
    if spec is None:
        print(f"Unknown provider: {raw}", file=sys.stderr)
        raise typer.Exit(1)
    return spec


def _resolve_named_provider(name: str | None, default_provider: str) -> ProviderSpec:
    """解析显式或默认 provider，但不触发交互式选择。"""

    from openharness.api.registry import get_provider_spec

    target_name = (name or default_provider).strip().lower()
    spec = get_provider_spec(target_name)
    if spec is None:
        print(f"Unknown provider: {target_name}", file=sys.stderr)
        raise typer.Exit(1)
    return spec


def _apply_provider_preset(settings, spec: ProviderSpec) -> None:
    """把 provider 预设写回 settings，统一 provider 切换语义。"""

    settings.provider = spec.name
    settings.api_format = spec.api_format
    settings.base_url = spec.default_base_url or None


def _render_provider_status_panel(*, title: str, settings, auth_note: str | None = None) -> str:
    """渲染统一的 provider/auth 状态面板。"""

    from openharness.api.provider import render_provider_status_panel

    return render_provider_status_panel(title=title, settings=settings, auth_note=auth_note)


def _resolve_setup_api_key(
    *,
    selected_provider: str,
    env_key: str,
    existing_provider: str | None,
    existing_api_key: str,
    cli_api_key: str | None,
    use_env: bool,
) -> tuple[str, str]:
    """决定 setup 后的 API key 落地方式，并返回展示给用户的说明文本。"""

    if cli_api_key is not None:
        normalized = cli_api_key.strip()
        if normalized:
            return normalized, "stored in settings.json"
        return "", f"use environment variable {env_key}"

    if use_env:
        return "", f"use environment variable {env_key}"

    if existing_provider == selected_provider and existing_api_key:
        return existing_api_key, "reuse stored key in settings.json"

    prompted = typer.prompt(
        f"输入 {selected_provider} 的 API key（留空则改用 {env_key}）",
        default="",
        show_default=False,
        hide_input=True,
    ).strip()
    if prompted:
        return prompted, "stored in settings.json"

    return "", f"set {env_key} (or rerun with --api-key)"


def _mcp_config_value(config: object, key: str, default: Any = None) -> Any:
    """统一读取 MCP 配置字段，兼容 dict 与 Pydantic 模型。"""

    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def _format_mcp_config_summary(name: str, config: object) -> str:
    """把一条 MCP 配置渲染成可读摘要，便于 CLI / 文档保持一致。"""

    transport = str(
        _mcp_config_value(
            config,
            "type",
            _mcp_config_value(
                config,
                "transport",
                "stdio" if _mcp_config_value(config, "command") else "unknown",
            ),
        )
    )

    if transport == "stdio":
        command = str(_mcp_config_value(config, "command", "") or "").strip()
        args = [str(item) for item in (_mcp_config_value(config, "args", []) or [])]
        target = " ".join(part for part in [command, *args] if part).strip() or "(missing command)"
        return f"  {name}: stdio -> {target}"

    if transport in {"http", "ws"}:
        url = str(_mcp_config_value(config, "url", "") or "").strip() or "(missing url)"
        headers = _mcp_config_value(config, "headers", {}) or {}
        header_note = f" (headers: {len(headers)})" if isinstance(headers, dict) and headers else ""
        return f"  {name}: {transport} -> {url}{header_note}"

    return f"  {name}: {transport}"


# ---- mcp subcommands ----

@mcp_app.command("list")
def mcp_list() -> None:
    """列出已配置的 MCP 服务器，并显示 transport 与目标地址。"""
    from openharness.config import load_settings
    from openharness.mcp.config import load_mcp_server_configs
    from openharness.plugins import load_plugins

    settings = load_settings()
    plugins = load_plugins(settings, str(Path.cwd()))
    configs = load_mcp_server_configs(settings, plugins)
    if not configs:
        print("当前没有配置 MCP 服务器。")
        return
    for name, cfg in configs.items():
        print(_format_mcp_config_summary(name, cfg))


@mcp_app.command("add")
def mcp_add(
    name: str = typer.Argument(..., help="服务器名称，例如 travel-browser"),
    config_json: str = typer.Argument(
        ...,
        help=(
            "MCP 配置 JSON，支持 stdio / http / ws。"
            '例如：\'{\"type\":\"ws\",\"url\":\"wss://mcp/ws\"}\''
        ),
    ),
) -> None:
    """新增一条 MCP 服务器配置，并在写入前做 transport 结构校验。"""
    from openharness.config import load_settings, save_settings
    from openharness.mcp.types import McpServerConfig
    from pydantic import TypeAdapter, ValidationError

    settings = load_settings()
    try:
        cfg = json.loads(config_json)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        raise typer.Exit(1)
    try:
        validated = TypeAdapter(McpServerConfig).validate_python(cfg)
    except ValidationError as exc:
        print(f"Invalid MCP config: {exc}", file=sys.stderr)
        raise typer.Exit(1)
    if not isinstance(settings.mcp_servers, dict):
        settings.mcp_servers = {}
    settings.mcp_servers[name] = validated
    save_settings(settings)
    print(f"Added MCP server: {name} [{validated.type}]")


@mcp_app.command("remove")
def mcp_remove(
    name: str = typer.Argument(..., help="Server name to remove"),
) -> None:
    """删除一条 MCP 服务器配置。"""
    from openharness.config import load_settings, save_settings

    settings = load_settings()
    if not isinstance(settings.mcp_servers, dict) or name not in settings.mcp_servers:
        print(f"MCP server not found: {name}", file=sys.stderr)
        raise typer.Exit(1)
    del settings.mcp_servers[name]
    save_settings(settings)
    print(f"Removed MCP server: {name}")


# ---- provider subcommands ----

@provider_app.command("list")
def provider_list() -> None:
    """列出内置 provider 预设。"""
    from openharness.api.provider import detect_provider
    from openharness.api.registry import list_provider_specs
    from openharness.config import load_settings

    settings = load_settings()
    active = detect_provider(settings).name
    for spec in list_provider_specs():
        marker = "*" if spec.name == active else " "
        base = spec.default_base_url or "(custom / official default)"
        print(f"{marker} {spec.name}: format={spec.api_format} env={spec.env_key} base={base}")


@provider_app.command("current")
def provider_current() -> None:
    """显示当前生效的 provider 配置。"""
    from openharness.config import load_settings

    settings = load_settings()
    print(_render_provider_status_panel(title="Provider current", settings=settings))


@provider_app.command("use")
def provider_use(
    name: str = typer.Argument(..., help="Provider name, e.g. anthropic/openai/moonshot"),
) -> None:
    """切换并持久化 provider 预设，同时保留 Velaris 品牌入口。"""
    from openharness.api.registry import get_provider_spec
    from openharness.config import load_settings, save_settings

    spec = get_provider_spec(name)
    if spec is None:
        print(f"Unknown provider: {name}", file=sys.stderr)
        raise typer.Exit(1)

    settings = load_settings()
    previous_provider = settings.provider or ""
    note = ""
    if previous_provider and previous_provider != spec.name and settings.api_key:
        settings.api_key = ""
        note = "cleared stored API key because provider changed"
    _apply_provider_preset(settings, spec)
    save_settings(settings)
    print(_render_provider_status_panel(title="Provider switched", settings=settings, auth_note=note or None))


@app.command("setup")
def setup_cmd(
    provider: str | None = typer.Argument(None, help="Provider name, e.g. anthropic/openai/moonshot"),
    model: str | None = typer.Option(None, "--model", help="要持久化的模型名称"),
    api_key: str | None = typer.Option(None, "--api-key", "-k", help="把 API key 写入 settings.json"),
    use_env: bool = typer.Option(False, "--use-env", help="不落盘 API key，改为依赖环境变量"),
) -> None:
    """交互式初始化当前 Velaris provider、模型与鉴权方式。"""

    from openharness.api.provider import detect_provider
    from openharness.config import load_settings, save_settings

    settings = load_settings()
    active_provider = detect_provider(settings).name
    spec = _resolve_setup_provider(provider, active_provider)

    selected_model = (model or "").strip()
    if not selected_model:
        selected_model = typer.prompt("Model", default=settings.model).strip()

    resolved_api_key, auth_summary = _resolve_setup_api_key(
        selected_provider=spec.name,
        env_key=spec.env_key,
        existing_provider=settings.provider,
        existing_api_key=settings.api_key,
        cli_api_key=api_key,
        use_env=use_env,
    )

    _apply_provider_preset(settings, spec)
    settings.model = selected_model
    settings.api_key = resolved_api_key
    save_settings(settings)

    print(_render_provider_status_panel(title="Setup complete", settings=settings, auth_note=auth_summary))


# ---- plugin subcommands ----

@plugin_app.command("list")
def plugin_list() -> None:
    """列出已安装插件。"""
    from openharness.config import load_settings
    from openharness.plugins import load_plugins

    settings = load_settings()
    plugins = load_plugins(settings, str(Path.cwd()))
    if not plugins:
        print("当前没有安装插件。")
        return
    for plugin in plugins:
        status = "enabled" if plugin.enabled else "disabled"
        print(f"  {plugin.name} [{status}] - {plugin.description or ''}")


@plugin_app.command("install")
def plugin_install(
    source: str = typer.Argument(..., help="Plugin source (path or URL)"),
) -> None:
    """从本地路径安装插件。"""
    from openharness.plugins.installer import install_plugin_from_path

    result = install_plugin_from_path(source)
    print(f"Installed plugin: {result}")


@plugin_app.command("uninstall")
def plugin_uninstall(
    name: str = typer.Argument(..., help="Plugin name to uninstall"),
) -> None:
    """卸载插件。"""
    from openharness.plugins.installer import uninstall_plugin

    uninstall_plugin(name)
    print(f"Uninstalled plugin: {name}")


# ---- auth subcommands ----

@auth_app.command("status")
def auth_status_cmd() -> None:
    """显示当前鉴权状态。"""
    from openharness.config import load_settings

    settings = load_settings()
    print(_render_provider_status_panel(title="Auth status", settings=settings))


@auth_app.command("switch")
def auth_switch(
    provider: str | None = typer.Argument(None, help="Provider name, e.g. anthropic/openai/moonshot"),
) -> None:
    """切换活跃 provider 预设，同时保持 Velaris 的轻量鉴权流程。"""

    from openharness.api.provider import detect_provider
    from openharness.config import load_settings, save_settings

    settings = load_settings()
    previous_provider = detect_provider(settings).name
    spec = _resolve_setup_provider(provider, previous_provider)
    note = ""
    if previous_provider != spec.name and settings.api_key:
        settings.api_key = ""
        note = "cleared stored API key because provider changed"
    elif previous_provider == spec.name:
        note = "provider already active"
    _apply_provider_preset(settings, spec)
    save_settings(settings)
    print(_render_provider_status_panel(title="Auth switched", settings=settings, auth_note=note or None))


@auth_app.command("login")
def auth_login(
    provider: str | None = typer.Argument(None, help="Provider name, e.g. anthropic/openai/moonshot"),
    api_key: str | None = typer.Option(None, "--api-key", "-k", help="API key"),
    use_env: bool = typer.Option(False, "--use-env", help="Do not store API key, rely on environment variables"),
) -> None:
    """配置当前 provider 的鉴权方式。"""
    from openharness.api.provider import detect_provider
    from openharness.config import load_settings, save_settings

    settings = load_settings()
    active_provider = detect_provider(settings).name
    spec = _resolve_setup_provider(provider, active_provider)
    if use_env and api_key is not None:
        print("不能同时使用 --api-key 和 --use-env。", file=sys.stderr)
        raise typer.Exit(1)
    if not use_env and not api_key:
        api_key = typer.prompt(f"请输入 {spec.display_name} 的 API key", hide_input=True)
    _apply_provider_preset(settings, spec)
    settings.api_key = "" if use_env else api_key
    save_settings(settings)
    auth_note = (
        f"use environment variable {spec.env_key}"
        if use_env
        else "stored in settings.json"
    )
    print(_render_provider_status_panel(title="Auth configured", settings=settings, auth_note=auth_note))


@auth_app.command("logout")
def auth_logout(
    provider: str | None = typer.Argument(None, help="Optional provider to activate before clearing stored auth"),
) -> None:
    """清除本地持久化的鉴权信息。"""
    from openharness.api.provider import detect_provider, resolve_auth_status
    from openharness.config import load_settings, save_settings

    settings = load_settings()
    active_provider = detect_provider(settings).name
    spec = _resolve_named_provider(provider, active_provider)
    _apply_provider_preset(settings, spec)
    settings.api_key = ""
    save_settings(settings)
    auth_note = "cleared stored API key"
    auth_info = resolve_auth_status(settings)
    if auth_info.source != "missing":
        auth_note = f"{auth_note}; active auth source remains {auth_info.source}"
    print(_render_provider_status_panel(title="Auth cleared", settings=settings, auth_note=auth_note))


# ---- demo subcommands ----

@demo_app.command("lifegoal")
def demo_lifegoal(
    domain: str = typer.Option(
        "career",
        "--domain", "-d",
        help="决策领域: career/finance/health/education/lifestyle/relationship",
    ),
    json_output: bool = typer.Option(False, "--json", help="以 JSON 格式输出 Demo 结果"),
    save_to: str | None = typer.Option(None, "--save-to", help="把 Demo 结果保存到指定文件"),
) -> None:
    """运行人生目标决策本地 Demo (支持 6 个领域)。"""
    from velaris_agent.scenarios.lifegoal.demo import (
        ALL_DOMAINS,
        render_lifegoal_demo_output,
        run_lifegoal_demo_sync,
        save_lifegoal_demo_output,
        serialize_lifegoal_demo_output,
    )

    if domain not in ALL_DOMAINS:
        print(f"不支持的领域: {domain}")
        print(f"可选: {', '.join(ALL_DOMAINS)}")
        raise typer.Exit(1)

    payload = run_lifegoal_demo_sync(domain)
    if save_to:
        saved = save_lifegoal_demo_output(payload, save_to)
        print(f"Demo 结果已保存到: {saved}")
    if json_output:
        print(serialize_lifegoal_demo_output(payload))
        return
    print(render_lifegoal_demo_output(payload))


@demo_app.command("skillhub")
def demo_skillhub(
    case: int = typer.Option(
        1,
        "--case",
        "-c",
        help="起始案例编号，从 1 开始",
    ),
    internal: bool = typer.Option(
        False,
        "--internal",
        help="包含内部 SkillHub skills 和内部 demo case",
    ),
    save_to: str = typer.Option(
        str(
            Path(
                "/Users/apus/Documents/UGit/smart-travel-workspace/output/"
                "skillhub-domain-agent-demo-page.md"
            )
        ),
        "--save-to",
        help="把 demo 页面保存到指定 markdown 文件",
    ),
) -> None:
    """运行 SkillHub 内部演示台。"""

    from openharness.skills.skillhub_demo import (
        build_skillhub_demo_frontend_config,
        build_skillhub_demo_prompt,
        ensure_skillhub_demo_skills_installed,
        skillhub_demo_cases,
        write_skillhub_demo_report,
    )

    import asyncio

    cases = skillhub_demo_cases(include_internal=internal)
    if not cases:
        print("SkillHub demo 没有可用案例。")
        raise typer.Exit(1)
    if case < 1 or case > len(cases):
        print(f"无效的案例编号: {case}")
        print(f"可选范围: 1 - {len(cases)}")
        raise typer.Exit(1)

    selected_index = case - 1
    installed = asyncio.run(
        ensure_skillhub_demo_skills_installed(include_internal=internal)
    )
    report_path = write_skillhub_demo_report(
        save_to,
        include_internal=internal,
        selected_case_index=selected_index,
        installed_slugs=installed,
    )
    print(f"Demo page 已写入: {report_path}")

    frontend_config = build_skillhub_demo_frontend_config(
        include_internal=internal,
        selected_case_index=selected_index,
    )
    prompt = build_skillhub_demo_prompt(
        include_internal=internal,
        selected_case_index=selected_index,
    )

    from openharness.ui.app import run_repl

    asyncio.run(
        run_repl(
            prompt=prompt,
            demo_mode=str(frontend_config["demo_mode"]),
            demo_case_index=int(frontend_config["demo_case_index"]),
            demo_cases=list(frontend_config["demo_cases"]),
        )
    )


# ---- storage subcommands ----

@storage_app.command("init")
def storage_init() -> None:
    """初始化项目内 SQLite 存储 schema。"""

    from openharness.config.paths import get_project_database_path
    from velaris_agent.persistence.schema import bootstrap_sqlite_schema

    database_path = get_project_database_path(Path.cwd())

    count = bootstrap_sqlite_schema(database_path)
    print(f"Storage initialized: {count} statements applied")


@storage_app.command("doctor")
def storage_doctor() -> None:
    """检查当前项目 SQLite 存储是否可用且 schema 完整。"""

    from openharness.config.paths import get_project_database_path
    from velaris_agent.persistence.schema import EXPECTED_TABLES

    database_path = get_project_database_path(Path.cwd())
    base_dir = database_path.parent
    database_exists = database_path.exists()
    base_dir_exists = base_dir.exists()

    lines: list[str] = [
        f"project_dir: {Path.cwd().resolve()}",
        f"base_dir: {base_dir} ({'present' if base_dir_exists else 'missing'})",
        f"database: {database_path} ({'present' if database_exists else 'missing'})",
    ]

    if not database_exists:
        lines.append("")
        lines.append("Storage is not initialized. Run: velaris storage init")
        print("\n".join(lines))
        raise typer.Exit(1)

    # 只读检查：避免在 doctor 中触发 WAL/SHM 写入或创建新库。
    import sqlite3

    try:
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        lines.append("")
        lines.append(f"storage_unavailable: {exc}")
        print("\n".join(lines))
        raise typer.Exit(1) from exc

    try:
        rows = connection.execute("select name from sqlite_master where type='table'").fetchall()
    finally:
        connection.close()

    existing_tables = {str(row[0]) for row in rows}
    missing_tables = [name for name in EXPECTED_TABLES if name not in existing_tables]
    if missing_tables:
        lines.append(f"schema: incomplete (missing {len(missing_tables)} tables)")
        lines.append("missing_tables: " + ", ".join(missing_tables))
        lines.append("")
        lines.append("Run: velaris storage init")
        print("\n".join(lines))
        raise typer.Exit(1)

    lines.append("schema: ok")
    print("\n".join(lines))


@storage_jobs_app.command("run-once")
def storage_jobs_run_once(
    limit: int = typer.Option(10, "--limit", min=1, help="单次最多处理的任务数量"),
) -> None:
    """执行一次数据库任务队列轮询。"""

    from openharness.config.paths import get_project_database_path
    from velaris_agent.persistence.job_queue import run_jobs_once

    database_path = get_project_database_path(Path.cwd())
    processed = run_jobs_once(str(database_path), limit=limit)
    print(f"processed: {processed}")


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    # --- Session ---
    continue_session: bool = typer.Option(
        False,
        "--continue",
        "-c",
        help="Continue the most recent conversation in the current directory",
        rich_help_panel="Session",
    ),
    resume: str | None = typer.Option(
        None,
        "--resume",
        "-r",
        help="Resume a conversation by session ID, or open picker",
        rich_help_panel="Session",
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        "-n",
        help="Set a display name for this session",
        rich_help_panel="Session",
    ),
    # --- Model & Effort ---
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Model alias (e.g. 'sonnet', 'opus') or full model ID",
        rich_help_panel="Model & Effort",
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        help="Provider preset (e.g. anthropic, openai, moonshot, dashscope)",
        rich_help_panel="Model & Effort",
    ),
    api_format: str | None = typer.Option(
        None,
        "--api-format",
        help="Provider protocol format: anthropic or openai_compat",
        rich_help_panel="Model & Effort",
    ),
    effort: str | None = typer.Option(
        None,
        "--effort",
        help="Effort level for the session (low, medium, high, max)",
        rich_help_panel="Model & Effort",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Override verbose mode setting from config",
        rich_help_panel="Model & Effort",
    ),
    max_turns: int | None = typer.Option(
        None,
        "--max-turns",
        help="Maximum number of agentic turns (useful with --print)",
        rich_help_panel="Model & Effort",
    ),
    # --- Output ---
    print_mode: str | None = typer.Option(
        None,
        "--print",
        "-p",
        help="Print response and exit. Pass your prompt as the value: -p 'your prompt'",
        rich_help_panel="Output",
    ),
    output_format: str | None = typer.Option(
        None,
        "--output-format",
        help="Output format with --print: text (default), json, or stream-json",
        rich_help_panel="Output",
    ),
    # --- Permissions ---
    permission_mode: str | None = typer.Option(
        None,
        "--permission-mode",
        help="Permission mode: default, plan, or full_auto",
        rich_help_panel="Permissions",
    ),
    dangerously_skip_permissions: bool = typer.Option(
        False,
        "--dangerously-skip-permissions",
        help="Bypass all permission checks (only for sandboxed environments)",
        rich_help_panel="Permissions",
    ),
    allowed_tools: Optional[list[str]] = typer.Option(
        None,
        "--allowed-tools",
        help="Comma or space-separated list of tool names to allow",
        rich_help_panel="Permissions",
    ),
    disallowed_tools: Optional[list[str]] = typer.Option(
        None,
        "--disallowed-tools",
        help="Comma or space-separated list of tool names to deny",
        rich_help_panel="Permissions",
    ),
    # --- System & Context ---
    system_prompt: str | None = typer.Option(
        None,
        "--system-prompt",
        "-s",
        help="Override the default system prompt",
        rich_help_panel="System & Context",
    ),
    append_system_prompt: str | None = typer.Option(
        None,
        "--append-system-prompt",
        help="Append text to the default system prompt",
        rich_help_panel="System & Context",
    ),
    settings_file: str | None = typer.Option(
        None,
        "--settings",
        help="Path to a JSON settings file or inline JSON string",
        rich_help_panel="System & Context",
    ),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="Provider API base URL",
        rich_help_panel="System & Context",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        "-k",
        help="API key (overrides config and environment)",
        rich_help_panel="System & Context",
    ),
    bare: bool = typer.Option(
        False,
        "--bare",
        help="Minimal mode: skip hooks, plugins, MCP, and auto-discovery",
        rich_help_panel="System & Context",
    ),
    auto_compact_threshold_tokens: int | None = typer.Option(
        None,
        "--auto-compact-threshold-tokens",
        help="Override the token threshold that triggers auto-compact",
        rich_help_panel="Advanced",
    ),
    # --- Advanced ---
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug logging",
        rich_help_panel="Advanced",
    ),
    mcp_config: Optional[list[str]] = typer.Option(
        None,
        "--mcp-config",
        help="Load MCP servers from JSON files or strings",
        rich_help_panel="Advanced",
    ),
    cwd: str = typer.Option(
        str(Path.cwd()),
        "--cwd",
        help="Working directory for the session",
        hidden=True,
    ),
    backend_only: bool = typer.Option(
        False,
        "--backend-only",
        help="Run the structured backend host for the React terminal UI",
        hidden=True,
    ),
) -> None:
    """Start an interactive session or run a single prompt."""
    if ctx.invoked_subcommand is not None:
        return

    import asyncio

    if dangerously_skip_permissions:
        permission_mode = "full_auto"

    from openharness.ui.app import run_print_mode, run_repl

    if print_mode is not None:
        prompt = print_mode.strip()
        if not prompt:
            print("Error: -p/--print requires a prompt value, e.g. -p 'your prompt'", file=sys.stderr)
            raise typer.Exit(1)
        asyncio.run(
            run_print_mode(
                prompt=prompt,
                output_format=output_format or "text",
                cwd=cwd,
                model=model,
                provider=provider,
                api_format=api_format,
                base_url=base_url,
                system_prompt=system_prompt,
                append_system_prompt=append_system_prompt,
                api_key=api_key,
                auto_compact_threshold_tokens=auto_compact_threshold_tokens,
                permission_mode=permission_mode,
                max_turns=max_turns,
            )
        )
        return

    asyncio.run(
        run_repl(
            prompt=None,
            cwd=cwd,
            model=model,
            provider=provider,
            api_format=api_format,
            backend_only=backend_only,
            base_url=base_url,
            system_prompt=system_prompt,
            api_key=api_key,
            auto_compact_threshold_tokens=auto_compact_threshold_tokens,
        )
    )
