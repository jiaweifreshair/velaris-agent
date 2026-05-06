"""Tests for ScenarioRegistry — 场景注册表核心。"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from velaris_agent.scenarios.registry import ScenarioRegistry


def _write_skill_md(directory: Path, name: str, content: str) -> Path:
    """辅助函数：在目录下创建 SKILL.md。"""
    scenario_dir = directory / name
    scenario_dir.mkdir(parents=True, exist_ok=True)
    skill_file = scenario_dir / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")
    return skill_file


# ── 发现 ──────────────────────────────────────────────


class TestDiscover:
    """测试场景发现。"""

    def test_discover_loads_all_scenarios(self, tmp_path: Path) -> None:
        """应加载目录下所有 SKILL.md。"""
        _write_skill_md(tmp_path, "travel", "---\nname: travel\nkeywords: [travel, flight]\n---\n")
        _write_skill_md(tmp_path, "tokencost", "---\nname: tokencost\nkeywords: [token]\n---\n")

        reg = ScenarioRegistry(scenarios_dir=tmp_path)
        names = reg.list_scenarios()
        assert "travel" in names
        assert "tokencost" in names

    def test_discover_returns_loaded_names(self, tmp_path: Path) -> None:
        """discover() 返回成功加载的场景名列表。"""
        _write_skill_md(tmp_path, "a", "---\nname: a\nkeywords: [a]\n---\n")
        _write_skill_md(tmp_path, "b", "---\nname: b\nkeywords: [b]\n---\n")

        loaded = ScenarioRegistry(scenarios_dir=tmp_path).discover(tmp_path)
        assert "a" in loaded
        assert "b" in loaded

    def test_discover_nonexistent_dir_returns_empty(self) -> None:
        """不存在的目录返回空列表。"""
        reg = ScenarioRegistry(scenarios_dir="/nonexistent")
        assert reg.list_scenarios() == []


# ── 匹配 ──────────────────────────────────────────────


class TestMatch:
    """测试场景匹配。"""

    @pytest.fixture()
    def registry(self, tmp_path: Path) -> ScenarioRegistry:
        """创建含多个场景的注册表。"""
        _write_skill_md(tmp_path, "travel", """\
---
name: travel
keywords: [travel, flight, hotel, trip, 商旅, 出差, 机票, 酒店]
weights:
  price: 0.40
  time: 0.35
  comfort: 0.25
---
""")
        _write_skill_md(tmp_path, "tokencost", """\
---
name: tokencost
keywords: [tokencost, token, openai, 降本, 成本优化]
risk_level: low
---
""")
        _write_skill_md(tmp_path, "robotclaw", """\
---
name: robotclaw
keywords: [robotclaw, dispatch, 派单, 运力]
risk_level: high
governance:
  requires_audit: true
  approval_mode: strict
  stop_profile: strict_approval
---
""")
        _write_skill_md(tmp_path, "procurement", """\
---
name: procurement
keywords: [procurement, 采购, 供应商, 比价]
risk_level: high
governance:
  requires_audit: true
  approval_mode: strict
  stop_profile: strict_approval
---
""")
        return ScenarioRegistry(scenarios_dir=tmp_path)

    def test_match_by_keyword(self, registry: ScenarioRegistry) -> None:
        """通过关键词匹配。"""
        spec = registry.match("帮我订机票")
        assert spec is not None
        assert spec.name == "travel"

    def test_match_chinese_keyword(self, registry: ScenarioRegistry) -> None:
        """中文关键词匹配。"""
        spec = registry.match("我想降本")
        assert spec is not None
        assert spec.name == "tokencost"

    def test_match_scenario_hint_priority(self, registry: ScenarioRegistry) -> None:
        """scenario_hint 优先于关键词匹配。"""
        spec = registry.match("随便聊聊", scenario_hint="travel")
        assert spec is not None
        assert spec.name == "travel"

    def test_match_scenario_hint_exact(self, registry: ScenarioRegistry) -> None:
        """scenario_hint 精确匹配场景名。"""
        spec = registry.match("anything", scenario_hint="robotclaw")
        assert spec is not None
        assert spec.name == "robotclaw"

    def test_match_no_match_returns_none(self, registry: ScenarioRegistry) -> None:
        """无匹配返回 None。"""
        spec = registry.match("今天天气真好")
        assert spec is None

    def test_match_longest_keyword_wins(self, tmp_path: Path) -> None:
        """关键词最长匹配优先。"""
        _write_skill_md(tmp_path, "travel", "---\nname: travel\nkeywords: [travel, 商旅]\n---\n")
        _write_skill_md(tmp_path, "hotel", "---\nname: hotel\nkeywords: [商旅礼宾]\n---\n")

        reg = ScenarioRegistry(scenarios_dir=tmp_path)
        spec = reg.match("商旅礼宾推荐")
        assert spec is not None
        assert spec.name == "hotel"

    def test_match_procurement_keyword(self, registry: ScenarioRegistry) -> None:
        """采购场景关键词匹配。"""
        spec = registry.match("采购比价")
        assert spec is not None
        assert spec.name == "procurement"


# ── 获取 ──────────────────────────────────────────────


class TestGet:
    """测试场景获取。"""

    @pytest.fixture()
    def registry(self, tmp_path: Path) -> ScenarioRegistry:
        _write_skill_md(tmp_path, "travel", """\
---
name: travel
keywords: [travel]
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
""")
        return ScenarioRegistry(scenarios_dir=tmp_path)

    def test_get_existing(self, registry: ScenarioRegistry) -> None:
        spec = registry.get("travel")
        assert spec is not None
        assert spec.name == "travel"

    def test_get_nonexistent_returns_none(self, registry: ScenarioRegistry) -> None:
        assert registry.get("nonexistent") is None

    def test_get_required_existing(self, registry: ScenarioRegistry) -> None:
        spec = registry.get_required("travel")
        assert spec.name == "travel"

    def test_get_required_nonexistent_raises(self, registry: ScenarioRegistry) -> None:
        with pytest.raises(KeyError, match="Scenario not found"):
            registry.get_required("nonexistent")


# ── 便捷访问器 ────────────────────────────────────────


class TestAccessors:
    """测试便捷访问器。"""

    @pytest.fixture()
    def registry(self, tmp_path: Path) -> ScenarioRegistry:
        _write_skill_md(tmp_path, "travel", """\
---
name: travel
keywords: [travel, 机票]
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
""")
        _write_skill_md(tmp_path, "general", """\
---
name: general
keywords: []
recommended_tools:
  - biz_execute
  - biz_plan
  - biz_score
---
""")
        return ScenarioRegistry(scenarios_dir=tmp_path)

    def test_get_keywords(self, registry: ScenarioRegistry) -> None:
        kws = registry.get_keywords("travel")
        assert "机票" in kws

    def test_get_keywords_nonexistent(self, registry: ScenarioRegistry) -> None:
        assert registry.get_keywords("nonexistent") == ()

    def test_get_capabilities(self, registry: ScenarioRegistry) -> None:
        caps = registry.get_capabilities("travel")
        assert "intent_parse" in caps

    def test_get_capabilities_nonexistent_default(self, registry: ScenarioRegistry) -> None:
        caps = registry.get_capabilities("nonexistent")
        assert "generic_analysis" in caps

    def test_get_weights(self, registry: ScenarioRegistry) -> None:
        weights = registry.get_weights("travel")
        assert weights["price"] == pytest.approx(0.40)

    def test_get_weights_nonexistent_default(self, registry: ScenarioRegistry) -> None:
        weights = registry.get_weights("nonexistent")
        assert weights == {"quality": 0.5, "cost": 0.3, "speed": 0.2}

    def test_get_governance(self, registry: ScenarioRegistry) -> None:
        gov = registry.get_governance("travel")
        assert gov["requires_audit"] is False
        assert gov["approval_mode"] == "default"

    def test_get_governance_nonexistent_default(self, registry: ScenarioRegistry) -> None:
        gov = registry.get_governance("nonexistent")
        assert gov["requires_audit"] is False

    def test_get_recommended_tools(self, registry: ScenarioRegistry) -> None:
        tools = registry.get_recommended_tools("travel")
        assert "biz_execute" in tools

    def test_get_recommended_tools_falls_to_general(self, registry: ScenarioRegistry) -> None:
        tools = registry.get_recommended_tools("nonexistent")
        assert "biz_execute" in tools

    def test_get_risk_level(self, registry: ScenarioRegistry) -> None:
        assert registry.get_risk_level("travel") == "medium"

    def test_get_risk_level_nonexistent(self, registry: ScenarioRegistry) -> None:
        assert registry.get_risk_level("nonexistent") == "medium"


# ── 热加载 ────────────────────────────────────────────


class TestReload:
    """测试热加载。"""

    def test_reload_picks_up_new_scenario(self, tmp_path: Path) -> None:
        """reload() 后新场景可被发现。"""
        _write_skill_md(tmp_path, "travel", "---\nname: travel\nkeywords: [travel]\n---\n")
        reg = ScenarioRegistry(scenarios_dir=tmp_path)
        assert "travel" in reg.list_scenarios()
        assert "new_one" not in reg.list_scenarios()

        # 添加新场景
        _write_skill_md(tmp_path, "new_one", "---\nname: new_one\nkeywords: [new]\n---\n")
        reg.reload()
        assert "new_one" in reg.list_scenarios()

    def test_reload_returns_loaded_names(self, tmp_path: Path) -> None:
        """reload() 返回所有成功加载的场景名。"""
        _write_skill_md(tmp_path, "travel", "---\nname: travel\nkeywords: [travel]\n---\n")
        reg = ScenarioRegistry(scenarios_dir=tmp_path)
        _write_skill_md(tmp_path, "new_one", "---\nname: new_one\nkeywords: [new]\n---\n")
        loaded = reg.reload()
        assert "travel" in loaded
        assert "new_one" in loaded


# ── 项目内置场景验证 ──────────────────────────────────


class TestBuiltinScenarios:
    """验证项目内置场景与原硬编码数据一致。"""

    @pytest.fixture()
    def registry(self) -> ScenarioRegistry:
        """使用项目内置场景目录。"""
        return ScenarioRegistry()

    def test_travel_scenario(self, registry: ScenarioRegistry) -> None:
        spec = registry.get_required("travel")
        assert "intent_parse" in spec.capabilities
        assert spec.weights["price"] == pytest.approx(0.40)
        assert spec.risk_level == "medium"
        assert spec.governance["requires_audit"] is False

    def test_robotclaw_scenario(self, registry: ScenarioRegistry) -> None:
        spec = registry.get_required("robotclaw")
        assert "proposal_score" in spec.capabilities
        assert spec.weights["safety"] == pytest.approx(0.40)
        assert spec.risk_level == "high"
        assert spec.governance["requires_audit"] is True

    def test_procurement_scenario(self, registry: ScenarioRegistry) -> None:
        spec = registry.get_required("procurement")
        assert "compliance_review" in spec.capabilities
        assert spec.weights["cost"] == pytest.approx(0.28)
        assert spec.risk_level == "high"

    def test_tokencost_scenario(self, registry: ScenarioRegistry) -> None:
        spec = registry.get_required("tokencost")
        assert spec.weights["cost"] == pytest.approx(0.50)
        assert spec.risk_level == "low"

    def test_lifegoal_scenario(self, registry: ScenarioRegistry) -> None:
        spec = registry.get_required("lifegoal")
        assert spec.weights["growth"] == pytest.approx(0.25)
        assert "option_discovery" in spec.capabilities

    def test_hotel_biztravel_scenario(self, registry: ScenarioRegistry) -> None:
        spec = registry.get_required("hotel_biztravel")
        assert "bundle_planning" in spec.capabilities
        assert spec.weights["eta"] == pytest.approx(0.30)

    def test_general_scenario(self, registry: ScenarioRegistry) -> None:
        spec = registry.get_required("general")
        assert "generic_analysis" in spec.capabilities
        assert "biz_execute" in spec.recommended_tools

    def test_infer_scenario_travel(self, registry: ScenarioRegistry) -> None:
        """infer_scenario 通过 registry 匹配 travel。"""
        from velaris_agent.biz.engine import infer_scenario
        assert infer_scenario("帮我订机票") == "travel"

    def test_infer_scenario_tokencost(self, registry: ScenarioRegistry) -> None:
        from velaris_agent.biz.engine import infer_scenario
        assert infer_scenario("模型成本优化") == "tokencost"

    def test_infer_scenario_procurement(self, registry: ScenarioRegistry) -> None:
        from velaris_agent.biz.engine import infer_scenario
        assert infer_scenario("采购比价") == "procurement"

    def test_infer_scenario_general(self, registry: ScenarioRegistry) -> None:
        from velaris_agent.biz.engine import infer_scenario
        assert infer_scenario("今天天气真好") == "general"

    def test_infer_scenario_explicit(self, registry: ScenarioRegistry) -> None:
        from velaris_agent.biz.engine import infer_scenario
        assert infer_scenario("anything", scenario="tokencost") == "tokencost"
