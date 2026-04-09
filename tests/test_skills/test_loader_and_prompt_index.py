"""Skills 加载与索引提示测试。"""

from __future__ import annotations

from pathlib import Path

from openharness.prompts import build_runtime_system_prompt
from openharness.config.settings import Settings
from openharness.skills import load_skill_registry


def test_load_user_skill_from_directory_layout(tmp_path: Path, monkeypatch) -> None:
    """用户技能应支持 Hermes 风格的目录布局。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    skills_dir = tmp_path / "config" / "skills" / "python-debug"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        (
            "---\n"
            "name: python-debug\n"
            "description: 调试 Python 报错的稳定流程\n"
            "---\n\n"
            "# Python Debug\n\n"
            "先复现，再缩小范围。\n"
        ),
        encoding="utf-8",
    )

    registry = load_skill_registry(tmp_path)
    skill = registry.get("python-debug")
    assert skill is not None
    assert skill.slug == "python-debug"
    assert skill.skill_dir is not None


def test_runtime_prompt_includes_skills_guidance(tmp_path: Path, monkeypatch) -> None:
    """系统提示应包含 skills 索引和技能沉淀引导。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    skills_dir = tmp_path / "config" / "skills" / "incident-review"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        (
            "---\n"
            "name: incident-review\n"
            "description: 事故复盘和行动项收敛\n"
            "---\n\n"
            "# Incident Review\n\n"
            "记录时间线和行动项。\n"
        ),
        encoding="utf-8",
    )

    prompt = build_runtime_system_prompt(Settings(), cwd=tmp_path, latest_user_prompt="复盘线上事故")
    assert "# Skills" in prompt
    assert "After completing a complex task (5+ tool calls)" in prompt
    assert "incident-review" in prompt
