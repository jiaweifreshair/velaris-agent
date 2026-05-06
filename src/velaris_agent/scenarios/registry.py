"""ScenarioRegistry — SKILL.md 驱动的场景注册表。

替代 engine.py 中的 _SCENARIO_KEYWORDS / _SCENARIO_CAPABILITIES /
_SCENARIO_WEIGHTS / _SCENARIO_GOVERNANCE / _SCENARIO_RECOMMENDED_TOOLS
五个硬编码字典。新场景只需添加 SKILL.md 目录，零代码修改。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from velaris_agent.scenarios.skill_loader import ScenarioSpec, load_skill_md


@dataclass
class _RegistryState:
    """注册表内部状态，支持 reload 时整体替换。"""

    specs: dict[str, ScenarioSpec] = field(default_factory=dict)
    keyword_index: dict[str, str] = field(default_factory=dict)  # keyword -> scenario_name


class ScenarioRegistry:
    """SKILL.md 驱动的场景注册表。

    核心方法：
    - discover(scenarios_dir): 扫描目录，加载所有 SKILL.md
    - match(query): 根据关键词匹配场景
    - get(name): 按名称获取场景规格
    - reload(): 热加载，重新扫描目录

    设计原则：
    - 失败不冒泡：SKILL.md 解析失败仅 warning，不影响其他场景
    - 线程安全：reload() 通过整体替换 _state 实现
    - 向后兼容：默认值与原硬编码完全一致
    """

    def __init__(self, scenarios_dir: Path | str | None = None) -> None:
        self._scenarios_dir = Path(scenarios_dir) if scenarios_dir else self._resolve_default_dir()
        self._state = _RegistryState()
        self.discover(self._scenarios_dir)

    # ── 公共接口 ──────────────────────────────────────────────

    def discover(self, scenarios_dir: Path | str) -> list[str]:
        """扫描目录，加载所有 SKILL.md，返回成功加载的场景名列表。"""
        dir_path = Path(scenarios_dir)
        if not dir_path.is_dir():
            return []

        loaded: list[str] = []
        new_specs: dict[str, ScenarioSpec] = dict(self._state.specs)  # 保留已有
        new_keywords: dict[str, str] = {}

        for child in sorted(dir_path.iterdir()):
            if not child.is_dir():
                continue
            skill_file = child / "SKILL.md"
            if not skill_file.is_file():
                continue
            try:
                spec = load_skill_md(skill_file)
            except Exception:
                # 解析失败仅跳过，不阻断其他场景
                continue
            # 索引关键词
            for kw in spec.keywords:
                kw_lower = kw.lower()
                if kw_lower not in new_keywords:
                    new_keywords[kw_lower] = spec.name
            new_specs[spec.name] = spec
            loaded.append(spec.name)

        self._state = _RegistryState(specs=new_specs, keyword_index=new_keywords)
        return loaded

    def match(self, query: str, scenario_hint: str | None = None) -> ScenarioSpec | None:
        """根据查询文本匹配场景。

        匹配优先级：
        1. scenario_hint 精确匹配场景名
        2. 关键词最长匹配（优先匹配更具体的关键词）
        3. None（无匹配）
        """
        # 优先级 1：显式指定
        if scenario_hint and scenario_hint in self._state.specs:
            return self._state.specs[scenario_hint]

        # 优先级 2：关键词匹配（最长匹配优先）
        lowered = query.lower()
        best_match: str | None = None
        best_len = 0
        for keyword, scenario_name in self._state.keyword_index.items():
            if keyword in lowered and len(keyword) > best_len:
                best_match = scenario_name
                best_len = len(keyword)

        if best_match and best_match in self._state.specs:
            return self._state.specs[best_match]
        return None

    def get(self, name: str) -> ScenarioSpec | None:
        """按名称获取场景规格，不存在返回 None。"""
        return self._state.specs.get(name)

    def get_required(self, name: str) -> ScenarioSpec:
        """按名称获取场景规格，不存在则抛出 KeyError。"""
        spec = self._state.specs.get(name)
        if spec is None:
            raise KeyError(f"Scenario not found: {name}")
        return spec

    def reload(self) -> list[str]:
        """热加载：重新扫描场景目录，返回新加载的场景名列表。"""
        return self.discover(self._scenarios_dir)

    def list_scenarios(self) -> list[str]:
        """返回所有已注册场景名称。"""
        return sorted(self._state.specs.keys())

    # ── 便捷访问器（替代原 _SCENARIO_* 字典的直接访问）──

    def get_keywords(self, name: str) -> tuple[str, ...]:
        """获取场景关键词，不存在返回空元组。"""
        spec = self.get(name)
        return spec.keywords if spec else ()

    def get_capabilities(self, name: str) -> list[str]:
        """获取场景能力列表，不存在返回默认值。"""
        spec = self.get(name)
        return spec.capabilities if spec else ["generic_analysis", "option_score"]

    def get_weights(self, name: str) -> dict[str, float]:
        """获取场景权重，不存在返回默认值。"""
        spec = self.get(name)
        return spec.weights if spec else {"quality": 0.5, "cost": 0.3, "speed": 0.2}

    def get_governance(self, name: str) -> dict[str, Any]:
        """获取场景治理配置，不存在返回默认值。"""
        spec = self.get(name)
        if spec:
            return {
                "requires_audit": spec.governance.get("requires_audit", False),
                "approval_mode": spec.governance.get("approval_mode", "default"),
                "stop_profile": spec.governance.get("stop_profile", "balanced"),
            }
        return {"requires_audit": False, "approval_mode": "default", "stop_profile": "balanced"}

    def get_recommended_tools(self, name: str) -> list[str]:
        """获取场景推荐工具列表，不存在返回 general 默认值。"""
        spec = self.get(name)
        if spec and spec.recommended_tools:
            return spec.recommended_tools
        general = self.get("general")
        if general and general.recommended_tools:
            return general.recommended_tools
        return ["biz_execute", "biz_plan", "biz_score", "biz_run_scenario"]

    def get_risk_level(self, name: str) -> str:
        """获取场景风险等级，不存在返回 'medium'。"""
        spec = self.get(name)
        return spec.risk_level if spec else "medium"

    # ── 私有方法 ──────────────────────────────────────────────

    @staticmethod
    def _resolve_default_dir() -> Path:
        """默认场景目录：src/velaris_agent/scenarios/。"""
        return Path(__file__).resolve().parent
