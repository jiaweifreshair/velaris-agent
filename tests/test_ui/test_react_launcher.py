"""Tests for the React terminal launcher path."""

from __future__ import annotations

import json

import pytest

from openharness.ui.app import run_repl
from openharness.ui.react_launcher import build_backend_command
from openharness.ui.react_launcher import launch_react_tui


def test_build_backend_command_includes_flags():
    command = build_backend_command(
        cwd="/tmp/demo",
        model="kimi-k2.5",
        base_url="https://api.moonshot.cn/anthropic",
        system_prompt="system",
        api_key="secret",
    )
    assert command[:3] == [command[0], "-m", "velaris_agent"]
    assert "--backend-only" in command
    assert "--cwd" in command
    assert "--model" in command
    assert "--base-url" in command
    assert "--system-prompt" in command
    assert "--api-key" not in command


@pytest.mark.asyncio
async def test_launch_react_tui_forwards_runtime_overrides(tmp_path, monkeypatch):
    """React 启动器应把 provider 相关覆盖项传给后端命令。"""

    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "package.json").write_text("{}", encoding="utf-8")
    (frontend_dir / "node_modules").mkdir()

    captured: dict[str, object] = {}

    class FakeProcess:
        async def wait(self) -> int:
            return 0

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr("openharness.ui.react_launcher.get_frontend_dir", lambda: frontend_dir)
    monkeypatch.setattr("openharness.ui.react_launcher.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    await launch_react_tui(
        prompt="hi",
        cwd="/tmp/demo",
        model="gpt-5.4",
        provider="openai",
        api_format="openai_compat",
        base_url="https://api.openai.com/v1",
        system_prompt="system",
        auto_compact_threshold_tokens=2048,
        demo_mode="skillhub",
        demo_case_index=1,
        demo_cases=[
            {
                "case_id": "local-life",
                "title": "送机前买花",
                "query": "帮我在机场附近找 3 家美团花店。",
                "skill_slugs": ["meituan"],
                "route_agents": ["local-life-agent"],
                "description": "demo",
                "internal_only": False,
            }
        ],
    )

    frontend_config = json.loads(captured["kwargs"]["env"]["VELARIS_FRONTEND_CONFIG"])  # type: ignore[index]
    backend_command = frontend_config["backend_command"]
    assert backend_command[:3] == [backend_command[0], "-m", "velaris_agent"]
    assert "--provider" in backend_command
    assert "openai" in backend_command
    assert "--api-format" in backend_command
    assert "openai_compat" in backend_command
    assert "--auto-compact-threshold-tokens" in backend_command
    assert "2048" in backend_command
    assert frontend_config["initial_prompt"] == "hi"
    assert frontend_config["demo_mode"] == "skillhub"
    assert frontend_config["demo_case_index"] == 1
    assert frontend_config["demo_cases"][0]["case_id"] == "local-life"


@pytest.mark.asyncio
async def test_launch_react_tui_reinstalls_when_esbuild_arch_mismatch(tmp_path, monkeypatch):
    """React 启动器在 esbuild 原生包架构不匹配时应重新安装前端依赖。"""

    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "package.json").write_text("{}", encoding="utf-8")
    (frontend_dir / "node_modules" / "@esbuild" / "darwin-x64").mkdir(parents=True)

    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    class FakeProcess:
        async def wait(self) -> int:
            return 0

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append((tuple(str(arg) for arg in args), kwargs))
        return FakeProcess()

    monkeypatch.setattr("openharness.ui.react_launcher.get_frontend_dir", lambda: frontend_dir)
    monkeypatch.setattr("openharness.ui.react_launcher._normalize_macos_arch", lambda machine=None: "arm64")
    monkeypatch.setattr("openharness.ui.react_launcher.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    await launch_react_tui(prompt="hi")

    assert calls[0][0][1] == "install"
    assert calls[1][0][1] == "exec"


@pytest.mark.asyncio
async def test_run_repl_uses_react_launcher_by_default(monkeypatch):
    seen = {}

    async def _launch(**kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr("openharness.ui.app.launch_react_tui", _launch)
    await run_repl(
        prompt="hi",
        cwd="/tmp/demo",
        model="kimi-k2.5",
        demo_mode="skillhub",
        demo_case_index=2,
        demo_cases=[{"case_id": "travel-bundle"}],
    )

    assert seen["prompt"] == "hi"
    assert seen["cwd"] == "/tmp/demo"
    assert seen["model"] == "kimi-k2.5"
    assert seen["demo_mode"] == "skillhub"
    assert seen["demo_case_index"] == 2
    assert seen["demo_cases"] == [{"case_id": "travel-bundle"}]
