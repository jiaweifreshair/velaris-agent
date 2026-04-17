"""Velaris 商旅推荐工具。"""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from velaris_agent.adapters.travel import TravelSourceAdapter
from velaris_agent.biz.engine import run_scenario


class TravelRecommendToolInput(BaseModel):
    """商旅推荐工具入参。"""

    query: str = Field(default="", description="用户自然语言请求")
    user_id: str = Field(default="anonymous", description="用户 ID")
    session_id: str | None = Field(default=None, description="会话 ID")
    budget_max: float = Field(default=0, description="预算上限")
    direct_only: bool = Field(default=False, description="是否仅允许直飞")
    confirm: bool = Field(default=False, description="是否确认执行推荐方案")
    selected_option_id: str | None = Field(default=None, description="确认时选中的候选项 ID")
    proposal_id: str | None = Field(default=None, description="上一次提案 ID")
    external_ref: str | None = Field(default=None, description="可选：外部订单号")
    options: list[dict[str, Any]] = Field(default_factory=list, description="候选商旅方案")
    source: dict[str, Any] = Field(default_factory=dict, description="可选：数据源配置，支持 inline/file/http")


class TravelRecommendTool(BaseTool):
    """执行商旅方案筛选与推荐。"""

    name = "travel_recommend"
    description = "Recommend the best travel plan under budget, direct-flight, and comfort constraints."
    input_model = TravelRecommendToolInput

    def is_read_only(self, arguments: BaseModel) -> bool:
        del arguments
        return True

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        del context
        parsed_arguments = cast(TravelRecommendToolInput, arguments)
        source_type = str(parsed_arguments.source.get("type", "inline")) if parsed_arguments.source else "inline"
        payload = await TravelSourceAdapter().resolve_payload(
            source=parsed_arguments.source,
            overrides={
                "query": parsed_arguments.query,
                "user_id": parsed_arguments.user_id,
                "session_id": parsed_arguments.session_id,
                "budget_max": parsed_arguments.budget_max,
                "direct_only": parsed_arguments.direct_only,
                "confirm": parsed_arguments.confirm,
                "selected_option_id": parsed_arguments.selected_option_id,
                "proposal_id": parsed_arguments.proposal_id,
                "external_ref": parsed_arguments.external_ref,
                "options": parsed_arguments.options,
                "source_type": source_type,
            },
        )
        result = run_scenario("travel", payload)
        return ToolResult(output=json.dumps(result, ensure_ascii=False, sort_keys=True))
