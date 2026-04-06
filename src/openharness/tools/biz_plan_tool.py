"""Velaris 业务能力规划工具。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from velaris_agent.biz.engine import build_capability_plan
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class BizPlanToolInput(BaseModel):
    """业务能力规划工具入参。"""

    query: str = Field(description="业务查询或目标描述")
    scenario: str | None = Field(default=None, description="可选：显式指定场景")
    constraints: dict[str, Any] = Field(default_factory=dict, description="业务约束")


class BizPlanTool(BaseTool):
    """输出 Velaris 业务能力计划。"""

    name = "biz_plan"
    description = "Build a Velaris business capability plan for lifegoal, travel, tokencost, or robotclaw scenarios."
    input_model = BizPlanToolInput

    def is_read_only(self, arguments: BizPlanToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: BizPlanToolInput, context: ToolExecutionContext) -> ToolResult:
        del context
        plan = build_capability_plan(
            query=arguments.query,
            constraints=arguments.constraints,
            scenario=arguments.scenario,
        )
        return ToolResult(output=json.dumps(plan, ensure_ascii=False, sort_keys=True))
