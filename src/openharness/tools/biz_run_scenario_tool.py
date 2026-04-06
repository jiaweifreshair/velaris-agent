"""Velaris 业务场景执行工具。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from velaris_agent.biz.engine import run_scenario
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class BizRunScenarioToolInput(BaseModel):
    """业务场景执行工具入参。"""

    scenario: str = Field(description="业务场景：travel / tokencost / robotclaw / lifegoal")
    payload: dict[str, Any] = Field(default_factory=dict, description="业务负载")


class BizRunScenarioTool(BaseTool):
    """执行 Velaris 业务场景并返回结构化结果。"""

    name = "biz_run_scenario"
    description = "Run a Velaris business scenario and return structured recommendations."
    input_model = BizRunScenarioToolInput

    def is_read_only(self, arguments: BizRunScenarioToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: BizRunScenarioToolInput, context: ToolExecutionContext) -> ToolResult:
        del context
        try:
            result = run_scenario(arguments.scenario, arguments.payload)
        except ValueError as exc:
            return ToolResult(output=str(exc), is_error=True)
        return ToolResult(output=json.dumps(result, ensure_ascii=False, sort_keys=True))
