"""SkillHub 分域 smoke 脚本的退出码与写报告行为测试。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_smoke_module():
    """按文件路径加载 smoke 脚本，避免把 scripts/ 目录改成包。"""
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "skillhub_domain_smoke.py"
    spec = importlib.util.spec_from_file_location("skillhub_domain_smoke", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 smoke 脚本: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_main_returns_zero_when_report_is_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """当报告结尾是 PASS 时，脚本退出码应为 0。"""
    smoke = _load_smoke_module()
    captured: dict[str, object] = {}

    async def _fake_collect_smoke_lines() -> list[str]:
        return ["# Smoke", "", "PASS"]

    def _fake_write_report(output_path: Path, lines: list[str]) -> None:
        captured["output_path"] = output_path
        captured["lines"] = list(lines)

    monkeypatch.setattr(smoke, "_collect_smoke_lines", _fake_collect_smoke_lines)
    monkeypatch.setattr(smoke, "_write_report", _fake_write_report)

    exit_code = await smoke._main(tmp_path / "skillhub-domain-agent-smoke-report.md")

    assert exit_code == 0
    assert captured["lines"] == ["# Smoke", "", "PASS"]


@pytest.mark.asyncio
async def test_main_returns_one_when_report_is_partial(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """当报告结尾是 PARTIAL 时，脚本退出码应为 1。"""
    smoke = _load_smoke_module()

    async def _fake_collect_smoke_lines() -> list[str]:
        return ["# Smoke", "", "PARTIAL"]

    monkeypatch.setattr(smoke, "_collect_smoke_lines", _fake_collect_smoke_lines)
    monkeypatch.setattr(smoke, "_write_report", lambda output_path, lines: None)

    exit_code = await smoke._main(tmp_path / "skillhub-domain-agent-smoke-report.md")

    assert exit_code == 1
