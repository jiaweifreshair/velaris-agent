"""Velaris 商旅对比工具。

这是对 `travel_recommend` 的协议化别名，强调“自然语言输入 -> 候选方案 -> 确认执行”。
"""

from __future__ import annotations

from openharness.tools.travel_recommend_tool import TravelRecommendTool


class TravelCompareTool(TravelRecommendTool):
    """提供更贴近 Demo 语义的商旅工具名。"""

    name = "travel_compare"
    description = (
        "Compare travel options from natural language, return a confirmable proposal, "
        "and optionally finalize the selected option."
    )
