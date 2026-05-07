"""Tests for SKILL.md YAML frontmatter 解析器。"""

from __future__ import annotations

from pathlib import Path

import pytest

from velaris_agent.scenarios.skill_loader import load_skill_md, scan_scenario_dir


def _write_skill_md(directory: Path, name: str, content: str) -> Path:
    """辅助函数：在目录下创建 SKILL.md。"""
    scenario_dir = directory / name
    scenario_dir.mkdir(parents=True, exist_ok=True)
    skill_file = scenario_dir / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")
    return skill_file


# ── load_skill_md ──────────────────────────────────────────


class TestLoadSkillMd:
    """测试 SKILL.md 解析。"""

    def test_parse_complete_frontmatter(self, tmp_path: Path) -> None:
        """完整 frontmatter 应全部解析。"""
        content = """\
---
name: travel
version: "1.0"
keywords: [travel, flight, hotel, 商旅]
capabilities: [intent_parse, option_score]
weights:
  price: 0.40
  time: 0.35
  comfort: 0.25
governance:
  requires_audit: false
  approval_mode: default
  stop_profile: balanced
risk_level: medium
recommended_tools:
  - biz_execute
  - travel_recommend
---

# Travel Scenario

商旅对比与推荐场景。
"""
        path = _write_skill_md(tmp_path, "travel", content)
        spec = load_skill_md(path)

        assert spec.name == "travel"
        assert spec.version == "1.0"
        assert "travel" in spec.keywords
        assert "商旅" in spec.keywords
        assert "intent_parse" in spec.capabilities
        assert spec.weights["price"] == pytest.approx(0.40)
        assert spec.governance["requires_audit"] is False
        assert spec.risk_level == "medium"
        assert "biz_execute" in spec.recommended_tools
        assert spec.description == "商旅对比与推荐场景。"

    def test_parse_minimal_frontmatter(self, tmp_path: Path) -> None:
        """最小 frontmatter：只有 name 和 keywords。"""
        content = """\
---
name: minimal
keywords: [test]
---

# Minimal
"""
        path = _write_skill_md(tmp_path, "minimal", content)
        spec = load_skill_md(path)

        assert spec.name == "minimal"
        assert spec.keywords == ("test",)
        assert spec.version == "1.0"
        assert spec.capabilities == ()
        assert spec.weights == {}
        assert spec.risk_level == "medium"
        assert spec.recommended_tools == ()

    def test_parse_no_frontmatter_raises(self, tmp_path: Path) -> None:
        """没有 frontmatter 应抛出 ValueError。"""
        skill_file = tmp_path / "noskill" / "SKILL.md"
        skill_file.parent.mkdir()
        skill_file.write_text("Just plain text", encoding="utf-8")

        with pytest.raises(ValueError, match="No YAML frontmatter"):
            load_skill_md(skill_file)

    def test_parse_empty_name_uses_dirname(self, tmp_path: Path) -> None:
        """name 为空时回退到目录名。"""
        content = """\
---
keywords: [test]
---
"""
        path = _write_skill_md(tmp_path, "mydir", content)
        spec = load_skill_md(path)
        assert spec.name == "mydir"

    def test_parse_governance_defaults(self, tmp_path: Path) -> None:
        """governance 缺失时使用默认值。"""
        content = """\
---
name: no_gov
keywords: [test]
---
"""
        path = _write_skill_md(tmp_path, "no_gov", content)
        spec = load_skill_md(path)
        assert spec.governance["requires_audit"] is False
        assert spec.governance["approval_mode"] == "default"

    def test_parse_chinese_keywords(self, tmp_path: Path) -> None:
        """中文关键词应正确解析。"""
        content = """\
---
name: zh_test
keywords: [采购, 供应商, 比价]
---
"""
        path = _write_skill_md(tmp_path, "zh_test", content)
        spec = load_skill_md(path)
        assert "采购" in spec.keywords
        assert "供应商" in spec.keywords

    def test_parse_weights_as_float(self, tmp_path: Path) -> None:
        """权重值应解析为 float。"""
        content = """\
---
name: wtest
keywords: [test]
weights:
  a: 0.5
  b: 0.3
  c: 0.2
---
"""
        path = _write_skill_md(tmp_path, "wtest", content)
        spec = load_skill_md(path)
        assert spec.weights["a"] == pytest.approx(0.5)
        assert sum(spec.weights.values()) == pytest.approx(1.0)


# ── scan_scenario_dir ──────────────────────────────────────


class TestScanScenarioDir:
    """测试场景目录扫描。"""

    def test_scan_multiple_skills(self, tmp_path: Path) -> None:
        """应扫描目录下所有 SKILL.md。"""
        _write_skill_md(tmp_path, "travel", "---\nname: travel\nkeywords: [travel]\n---\n")
        _write_skill_md(tmp_path, "tokencost", "---\nname: tokencost\nkeywords: [token]\n---\n")

        specs = scan_scenario_dir(tmp_path)
        assert "travel" in specs
        assert "tokencost" in specs
        assert specs["travel"].name == "travel"

    def test_scan_skips_dirs_without_skill_md(self, tmp_path: Path) -> None:
        """没有 SKILL.md 的目录应跳过。"""
        (tmp_path / "empty_dir").mkdir()
        _write_skill_md(tmp_path, "travel", "---\nname: travel\nkeywords: [travel]\n---\n")

        specs = scan_scenario_dir(tmp_path)
        assert len(specs) == 1
        assert "travel" in specs

    def test_scan_skips_invalid_skill_md(self, tmp_path: Path) -> None:
        """解析失败的 SKILL.md 应跳过，不影响其他。"""
        # 无效的 SKILL.md
        bad_dir = tmp_path / "bad"
        bad_dir.mkdir()
        (bad_dir / "SKILL.md").write_text("no frontmatter here", encoding="utf-8")

        # 有效的 SKILL.md
        _write_skill_md(tmp_path, "good", "---\nname: good\nkeywords: [test]\n---\n")

        specs = scan_scenario_dir(tmp_path)
        assert "good" in specs
        assert "bad" not in specs

    def test_scan_nonexistent_dir_returns_empty(self) -> None:
        """不存在的目录返回空字典。"""
        specs = scan_scenario_dir(Path("/nonexistent"))
        assert specs == {}

    def test_scan_project_scenarios(self) -> None:
        """验证项目内置场景全部可扫描。"""
        scenarios_dir = Path(__file__).resolve().parents[2] / "src" / "velaris_agent" / "scenarios"
        if not scenarios_dir.is_dir():
            pytest.skip("scenarios dir not found")

        specs = scan_scenario_dir(scenarios_dir)
        # 至少有 6 个核心场景
        expected = {"lifegoal", "travel", "hotel_biztravel", "tokencost", "robotclaw", "procurement"}
        assert expected.issubset(set(specs.keys())), f"Missing: {expected - set(specs.keys())}"
