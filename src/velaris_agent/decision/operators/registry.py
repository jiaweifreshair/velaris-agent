"""Decision operator registry。"""

from __future__ import annotations

from dataclasses import dataclass

from velaris_agent.decision.operators.base import OperatorSpec


@dataclass
class OperatorRegistry:
    """按场景维护 operator graph 的注册表。

    Phase 2 只让 procurement 接入新 graph，
    非 procurement 场景继续沿用 legacy 路径，因此这里故意不注册它们。
    """

    graphs: dict[str, list[OperatorSpec]]

    def get_graph(self, scenario: str) -> list[OperatorSpec]:
        """返回指定场景的算子链定义。"""

        return self.graphs[scenario]


def build_default_operator_registry() -> OperatorRegistry:
    """构造 procurement graph 的过渡态 registry。"""

    default_graph = [
        OperatorSpec("intent"),
        OperatorSpec("option_discovery"),
        OperatorSpec("normalization"),
        OperatorSpec("stakeholder"),
        OperatorSpec("feasibility"),
        OperatorSpec("optimization"),
        OperatorSpec("negotiation"),
        OperatorSpec("bias_audit"),
        OperatorSpec("explanation"),
    ]
    return OperatorRegistry(
        graphs={
            "procurement": list(default_graph),
        }
    )
