"""CLI smoke tests."""

import json

from typer.testing import CliRunner

from openharness.cli import app
from openharness.config import load_settings


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Velaris" in result.output


def test_cli_lifegoal_demo():
    runner = CliRunner()
    result = runner.invoke(app, ["demo", "lifegoal"])
    assert result.exit_code == 0
    assert "人生目标决策结果" in result.output
    assert "偏好召回" in result.output


def test_cli_lifegoal_demo_json():
    runner = CliRunner()
    result = runner.invoke(app, ["demo", "lifegoal", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "人生目标决策结果" in payload
    assert payload["人生目标决策结果"]["recommended"]["id"] == "offer-b"


def test_cli_lifegoal_demo_save_to(tmp_path):
    runner = CliRunner()
    output_path = tmp_path / "lifegoal-demo.json"
    result = runner.invoke(app, ["demo", "lifegoal", "--save-to", str(output_path)])
    assert result.exit_code == 0
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "保存结果" in payload
    assert "Demo 结果已保存到:" in result.output


def test_cli_skillhub_demo_prepares_frontend_and_report(tmp_path, monkeypatch):
    """SkillHub demo 命令应先同步 skills，再生成演示页并传给前端。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    captured: dict[str, object] = {}

    async def fake_install_skills(*, include_internal: bool = False, force: bool = False):
        del force
        assert include_internal is False
        return ["meituan", "coupon"]

    async def fake_run_repl(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(
        "openharness.skills.skillhub_demo.ensure_skillhub_demo_skills_installed",
        fake_install_skills,
    )
    monkeypatch.setattr("openharness.ui.app.run_repl", fake_run_repl)

    runner = CliRunner()
    report_path = tmp_path / "skillhub-demo.md"
    result = runner.invoke(
        app,
        ["demo", "skillhub", "--case", "1", "--save-to", str(report_path)],
    )

    assert result.exit_code == 0
    assert report_path.exists()
    report = report_path.read_text(encoding="utf-8")
    assert "SkillHub 内部演示台" in report
    assert "local-life-agent" in report
    assert captured["demo_mode"] == "skillhub"
    assert captured["demo_case_index"] == 0
    assert captured["demo_cases"][0]["case_id"] == "local-life"
    assert captured["prompt"].startswith("帮我在机场附近找")


def test_cli_provider_list():
    """Provider 列表应包含内置预设。"""

    runner = CliRunner()
    result = runner.invoke(app, ["provider", "list"])
    assert result.exit_code == 0
    assert "anthropic" in result.output
    assert "moonshot" in result.output


def test_cli_provider_use_persists(tmp_path, monkeypatch):
    """切换 provider 后应把设置持久化到配置文件。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    from openharness.config import Settings, save_settings

    save_settings(Settings(provider="anthropic", api_key="old-secret", model="claude-sonnet-4-20250514"))
    runner = CliRunner()

    result = runner.invoke(app, ["provider", "use", "moonshot"])

    assert result.exit_code == 0
    assert "Provider switched:" in result.output
    assert "- provider: moonshot" in result.output
    settings = load_settings()
    assert settings.provider == "moonshot"
    assert settings.api_format == "openai_compat"
    assert settings.base_url == "https://api.moonshot.ai/v1"
    assert settings.api_key == ""


def test_cli_provider_current_uses_unified_status_panel(tmp_path, monkeypatch):
    """provider current 应复用统一状态面板输出。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MOONSHOT_API_KEY", "env-secret")
    from openharness.config import Settings, save_settings

    save_settings(Settings(provider="moonshot", api_format="openai_compat", model="kimi-k2"))
    runner = CliRunner()

    result = runner.invoke(app, ["provider", "current"])

    assert result.exit_code == 0
    assert "Provider current:" in result.output
    assert "- provider: moonshot" in result.output
    assert "- auth_source: env:MOONSHOT_API_KEY" in result.output


def test_cli_setup_persists_provider_model_and_api_key(tmp_path, monkeypatch):
    """setup 应把 provider、模型和 API key 一次性写入配置。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["setup", "moonshot", "--model", "kimi-k2", "--api-key", "secret-key"],
    )

    assert result.exit_code == 0
    assert "Setup complete" in result.output
    assert "provider: moonshot" in result.output
    assert "auth_status: configured" in result.output
    settings = load_settings()
    assert settings.provider == "moonshot"
    assert settings.api_format == "openai_compat"
    assert settings.base_url == "https://api.moonshot.ai/v1"
    assert settings.model == "kimi-k2"
    assert settings.api_key == "secret-key"


def test_cli_setup_use_env_clears_stale_api_key_on_provider_switch(tmp_path, monkeypatch):
    """切换 provider 且显式改用环境变量时，应清理旧的持久化 API key。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    from openharness.config import Settings, save_settings

    save_settings(Settings(provider="anthropic", api_key="old-secret", model="claude-sonnet-4-20250514"))
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["setup", "moonshot", "--model", "kimi-k2", "--use-env"],
    )

    assert result.exit_code == 0
    assert "MOONSHOT_API_KEY" in result.output
    settings = load_settings()
    assert settings.provider == "moonshot"
    assert settings.api_key == ""


def test_cli_auth_login_switches_provider_and_saves_key(tmp_path, monkeypatch):
    """auth login 应按 provider 预设更新设置并保存对应 API key。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    runner = CliRunner()

    result = runner.invoke(app, ["auth", "login", "moonshot", "--api-key", "secret-key"])

    assert result.exit_code == 0
    assert "Auth configured:" in result.output
    assert "- provider: moonshot" in result.output
    assert "- auth_status: configured" in result.output
    assert "- auth_source: settings" in result.output
    assert "- credential_env: MOONSHOT_API_KEY" in result.output
    settings = load_settings()
    assert settings.provider == "moonshot"
    assert settings.api_format == "openai_compat"
    assert settings.base_url == "https://api.moonshot.ai/v1"
    assert settings.api_key == "secret-key"


def test_cli_auth_status_reports_provider_specific_env_source(tmp_path, monkeypatch):
    """auth status 应展示 provider 对应的环境变量来源。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MOONSHOT_API_KEY", "env-secret")
    from openharness.config import Settings, save_settings

    save_settings(Settings(provider="moonshot", api_format="openai_compat", model="kimi-k2"))
    runner = CliRunner()

    result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 0
    assert "Auth status:" in result.output
    assert "- provider: moonshot" in result.output
    assert "- auth_source: env:MOONSHOT_API_KEY" in result.output


def test_cli_auth_status_reports_codex_auth_source(tmp_path, monkeypatch):
    """auth status 应展示来自 Codex auth 文件的来源。"""

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "auth.json").write_text(
        json.dumps(
            {
                "OPENAI_API_KEY": "sk-codex-secret",
                "auth_mode": "apikey",
                "tokens": {},
            }
        ),
        encoding="utf-8",
    )
    from openharness.config import Settings, save_settings

    save_settings(Settings(provider="openai", api_format="openai_compat", model="gpt-5"))
    runner = CliRunner()

    result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 0
    assert "Auth status:" in result.output
    assert "- provider: openai" in result.output
    assert "- auth_source: codex:~/.codex/auth.json#OPENAI_API_KEY" in result.output


def test_cli_auth_logout_clears_key_for_active_provider(tmp_path, monkeypatch):
    """auth logout 应清空当前 provider 的本地持久化 key。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    from openharness.config import Settings, save_settings

    save_settings(Settings(provider="moonshot", api_key="secret-key", api_format="openai_compat"))
    runner = CliRunner()

    result = runner.invoke(app, ["auth", "logout"])

    assert result.exit_code == 0
    assert "Auth cleared:" in result.output
    assert "- provider: moonshot" in result.output
    assert "- auth_status: missing" in result.output
    assert load_settings().api_key == ""


def test_cli_auth_switch_updates_provider_and_uses_unified_panel(tmp_path, monkeypatch):
    """auth switch 应切换 provider 并输出统一状态面板。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    from openharness.config import Settings, save_settings

    save_settings(Settings(provider="anthropic", api_key="old-secret", model="claude-sonnet-4-20250514"))
    runner = CliRunner()

    result = runner.invoke(app, ["auth", "switch", "moonshot"])

    assert result.exit_code == 0
    assert "Auth switched:" in result.output
    assert "- provider: moonshot" in result.output
    settings = load_settings()
    assert settings.provider == "moonshot"
    assert settings.api_key == ""


def test_cli_auth_login_can_select_provider_interactively(tmp_path, monkeypatch):
    """auth login 在未指定 provider 时应支持交互式选择。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    runner = CliRunner()

    result = runner.invoke(app, ["auth", "login", "--use-env"], input="moonshot\n")

    assert result.exit_code == 0
    assert "请选择要配置的 provider：" in result.output
    assert "MOONSHOT_API_KEY" in result.output
    settings = load_settings()
    assert settings.provider == "moonshot"
    assert settings.api_key == ""


def test_cli_auth_login_use_env_clears_stored_key_on_provider_switch(tmp_path, monkeypatch):
    """auth login 使用 --use-env 时应清理旧的持久化 key。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    from openharness.config import Settings, save_settings

    save_settings(Settings(provider="anthropic", api_key="old-secret", model="claude-sonnet-4-20250514"))
    runner = CliRunner()

    result = runner.invoke(app, ["auth", "login", "moonshot", "--use-env"])

    assert result.exit_code == 0
    assert "MOONSHOT_API_KEY" in result.output
    settings = load_settings()
    assert settings.provider == "moonshot"
    assert settings.api_key == ""


def test_cli_auth_logout_reports_when_env_still_active(tmp_path, monkeypatch):
    """auth logout 应提示用户环境变量鉴权仍然生效。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MOONSHOT_API_KEY", "env-secret")
    from openharness.config import Settings, save_settings

    save_settings(Settings(provider="moonshot", api_key="secret-key", api_format="openai_compat"))
    runner = CliRunner()

    result = runner.invoke(app, ["auth", "logout"])

    assert result.exit_code == 0
    assert "Auth cleared:" in result.output
    assert "env:MOONSHOT_API_KEY" in result.output


def test_cli_mcp_add_help_mentions_ws_transport():
    """`mcp add --help` 应明确提示支持 ws MCP 配置。"""

    runner = CliRunner()

    result = runner.invoke(app, ["mcp", "add", "--help"])

    assert result.exit_code == 0
    assert '"type":"ws"' in result.output
    assert "wss://mcp/ws" in result.output


def test_cli_mcp_add_and_list_support_ws_configs(tmp_path, monkeypatch):
    """`mcp add/list` 应支持并正确展示 ws MCP 配置。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    runner = CliRunner()

    add_result = runner.invoke(
        app,
        [
            "mcp",
            "add",
            "remote-ws",
            '{"type":"ws","url":"wss://example.com/mcp","headers":{"Authorization":"Bearer secret"}}',
        ],
    )

    assert add_result.exit_code == 0
    assert "remote-ws" in add_result.output

    settings = load_settings()
    config = settings.mcp_servers["remote-ws"]
    assert config.type == "ws"
    assert config.url == "wss://example.com/mcp"
    assert config.headers == {"Authorization": "Bearer secret"}

    list_result = runner.invoke(app, ["mcp", "list"])

    assert list_result.exit_code == 0
    assert "remote-ws: ws -> wss://example.com/mcp" in list_result.output
    assert "headers: 1" in list_result.output


def test_cli_storage_init_bootstraps_schema(tmp_path, monkeypatch):
    """storage init 应调用 schema bootstrap 并输出执行条数。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    called = {}

    def fake_bootstrap_sqlite_schema(database_path) -> int:
        called["database_path"] = str(database_path)
        return 6

    monkeypatch.setattr(
        "velaris_agent.persistence.schema.bootstrap_sqlite_schema",
        fake_bootstrap_sqlite_schema,
    )

    result = runner.invoke(app, ["storage", "init"])

    assert result.exit_code == 0
    assert called["database_path"] == str(tmp_path / ".velaris-agent" / "velaris.db")
    assert "Storage initialized: 6 statements applied" in result.output


def test_cli_storage_jobs_run_once(tmp_path, monkeypatch):
    """storage jobs run-once 应调用 worker 并输出处理数量。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    called = {}

    def fake_run_jobs_once(database_path: str, limit: int) -> int:
        """记录 CLI 传给 worker 的参数，并返回稳定的处理数。"""

        called["database_path"] = database_path
        called["limit"] = limit
        return 2

    monkeypatch.setattr("velaris_agent.persistence.job_queue.run_jobs_once", fake_run_jobs_once)

    result = runner.invoke(app, ["storage", "jobs", "run-once", "--limit", "5"])

    assert result.exit_code == 0
    assert called == {
        "database_path": str(tmp_path / ".velaris-agent" / "velaris.db"),
        "limit": 5,
    }
    assert "processed: 2" in result.output


def test_cli_storage_doctor_reports_missing_storage(tmp_path, monkeypatch):
    """storage doctor 在未初始化时应提示并返回非 0。"""

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["storage", "doctor"])

    assert result.exit_code != 0
    assert "Storage is not initialized" in result.output
