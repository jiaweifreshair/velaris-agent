"""SkillHub 内部演示台支持逻辑的测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.skills import skillhub_demo


def test_skillhub_demo_report_includes_public_routes() -> None:
    """报告页应展示公开 demo、领域路由与真实 skill slug。"""
    report = skillhub_demo.build_skillhub_demo_report(include_internal=False)

    assert "SkillHub 内部演示台" in report
    assert "local-life-agent" in report
    assert "coupon-agent" in report
    assert "travel-agent" in report
    assert "flight-agent" in report
    assert "meituan" in report
    assert "tripgenie" in report


def test_skillhub_demo_report_merges_existing_and_recent_installs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """报告页应同时展示 lock 中已有安装和本次新装的技能。"""

    monkeypatch.setattr(skillhub_demo, "_installed_skill_names", lambda: {"coupon"})

    report = skillhub_demo.build_skillhub_demo_report(
        include_internal=False,
        installed_slugs=["meituan"],
    )

    assert "- `meituan` → `local-life-agent` (installed)" in report
    assert "- `coupon` → `coupon-agent` (installed)" in report


def test_skillhub_demo_public_view_hides_internal_skill_slugs() -> None:
    """公开 demo 视图不应直接暴露内部 coupon / hotel 技能名。"""

    cases = skillhub_demo.skillhub_demo_cases(include_internal=False)
    coupon_case_model = next(case for case in cases if case.case_id == "coupon")
    payloads = skillhub_demo.skillhub_demo_case_payloads(include_internal=False)
    coupon_case = next(case for case in payloads if case["case_id"] == "coupon")

    assert coupon_case_model.skill_slugs == ("coupon",)
    assert coupon_case["skill_slugs"] == ["coupon"]

    report = skillhub_demo.build_skillhub_demo_report(include_internal=False)

    assert "tuniu-hotel" not in report
    assert "coupons" not in report
    assert "obtain-coupons-all-in-one" not in report
    assert "obtain-takeout-coupon" not in report


@pytest.mark.asyncio
async def test_skillhub_demo_sync_installs_public_skills_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """默认只应同步公开 SkillHub 技能。"""
    installed: list[str] = []

    class _FakeLock:
        def get_installed(self, name: str):  # noqa: ANN001
            return None

    async def _fake_install_skill(identifier: str, sources, *, force: bool = False):  # noqa: ANN001
        installed.append(identifier)
        assert force is False
        assert sources
        return f"installed {identifier}"

    monkeypatch.setattr(skillhub_demo, "HubLockFile", lambda: _FakeLock())
    monkeypatch.setattr(skillhub_demo, "install_skill", _fake_install_skill)
    monkeypatch.setattr(skillhub_demo, "get_user_skills_dir", lambda: tmp_path)

    result = await skillhub_demo.ensure_skillhub_demo_skills_installed(include_internal=False)

    assert result == installed
    assert "meituan" in installed
    assert "coupon" in installed
    assert "tripgenie" in installed
    assert "cabin" in installed
    assert "tuniu-hotel" not in installed


@pytest.mark.asyncio
async def test_skillhub_demo_sync_skips_blocked_public_skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """被安全扫描拦住的公开技能应跳过，不应拖垮整个 demo 安装流程。"""

    calls: list[str] = []

    class _FakeLock:
        def get_installed(self, name: str):  # noqa: ANN001
            return None

    async def _fake_install_skill(identifier: str, sources, *, force: bool = False):  # noqa: ANN001
        del sources, force
        calls.append(identifier)
        if identifier == "cabin":
            raise RuntimeError(
                "Installation of 'cabin' blocked by security scan: "
                "Blocked: 1 high-severity finding(s) — HTTP POST via curl — potential data exfiltration"
            )
        return f"installed {identifier}"

    monkeypatch.setattr(skillhub_demo, "HubLockFile", lambda: _FakeLock())
    monkeypatch.setattr(skillhub_demo, "install_skill", _fake_install_skill)
    monkeypatch.setattr(skillhub_demo, "get_user_skills_dir", lambda: tmp_path)
    monkeypatch.setattr(skillhub_demo, "skillhub_demo_install_targets", lambda *, include_internal=False: ["cabin", "meituan"])

    result = await skillhub_demo.ensure_skillhub_demo_skills_installed(include_internal=False)

    assert calls == ["cabin", "meituan"]
    assert result == ["meituan"]
