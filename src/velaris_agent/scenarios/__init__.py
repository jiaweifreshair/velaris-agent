"""Velaris 产品场景模块。

UOW-5: ScenarioRegistry + SKILL.md 插件化场景注册。
"""

from velaris_agent.scenarios.registry import ScenarioRegistry
from velaris_agent.scenarios.skill_loader import ScenarioSpec

__all__ = ["ScenarioRegistry", "ScenarioSpec"]
