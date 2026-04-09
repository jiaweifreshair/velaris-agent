"""自进化复盘工具。"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class SelfEvolutionReviewInput(BaseModel):
    """自进化复盘入参。"""

    user_id: str = Field(description="用户 ID")
    scenario: str = Field(description="决策场景")
    window: int = Field(default=20, ge=3, le=200, description="回顾窗口，按最近 N 条记录统计")
    persist_report: bool = Field(default=True, description="是否持久化报告")


class SelfEvolutionReviewTool(BaseTool):
    """基于历史决策反馈生成结构化优化建议。"""

    name = "self_evolution_review"
    description = (
        "Review historical decision outcomes and generate self-evolution actions. "
        "Returns acceptance rate, satisfaction trend, and actionable improvements."
    )
    input_model = SelfEvolutionReviewInput

    def is_read_only(self, arguments: SelfEvolutionReviewInput) -> bool:
        """仅在持久化报告时写磁盘。"""
        return not arguments.persist_report

    async def execute(
        self, arguments: SelfEvolutionReviewInput, context: ToolExecutionContext
    ) -> ToolResult:
        """执行自进化复盘。"""
        try:
            from velaris_agent.evolution.self_evolution import SelfEvolutionEngine
            from velaris_agent.memory.decision_memory import DecisionMemory

            memory_dir = context.metadata.get("decision_memory_dir")
            report_dir = context.metadata.get("evolution_report_dir")
            memory = DecisionMemory(base_dir=memory_dir)
            engine = SelfEvolutionEngine(memory=memory, report_dir=report_dir)

            report = engine.review(
                user_id=arguments.user_id,
                scenario=arguments.scenario,
                window=arguments.window,
                persist_report=arguments.persist_report,
            )
            return ToolResult(output=json.dumps(report.model_dump(mode="json"), ensure_ascii=False))
        except Exception as exc:
            return ToolResult(output=f"自进化复盘失败: {exc}", is_error=True)
