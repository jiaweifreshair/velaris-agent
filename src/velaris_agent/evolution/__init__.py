"""Velaris 自进化评估模块。

v2.0 新增：SkillEvolutionLoop（执行型进化循环）、CostOptimizer（Token 成本优化）。
"""

from velaris_agent.evolution.cost_optimizer import CostOptimizer, LoadingTier, ComplexityLevel
from velaris_agent.evolution.self_evolution import SelfEvolutionEngine
from velaris_agent.evolution.skill_evolution import SkillEvolutionLoop
from velaris_agent.evolution.types import EvolutionAction, SelfEvolutionReport

__all__ = [
    "SelfEvolutionEngine",
    "SelfEvolutionReport",
    "EvolutionAction",
    "SkillEvolutionLoop",
    "CostOptimizer",
    "LoadingTier",
    "ComplexityLevel",
]
