"""自进化评估数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class EvolutionAction(BaseModel):
    """一条可执行的自进化建议。"""

    action_id: str = Field(description="建议 ID")
    priority: Literal["high", "medium", "low"] = Field(description="优先级")
    title: str = Field(description="建议标题")
    reason: str = Field(description="建议原因")
    details: dict[str, float | str] = Field(default_factory=dict, description="结构化细节")


class SelfEvolutionReport(BaseModel):
    """一次自进化回顾报告。"""

    user_id: str = Field(description="用户 ID")
    scenario: str = Field(description="场景")
    generated_at: datetime = Field(description="生成时间")
    sample_size: int = Field(description="分析样本数")
    accepted_recommendation_rate: float | None = Field(default=None, description="接受推荐率")
    average_feedback: float | None = Field(default=None, description="平均满意度")
    top_preference_drift: dict[str, float] = Field(
        default_factory=dict, description="用户偏好漂移信号（维度 -> 漂移值）"
    )
    actions: list[EvolutionAction] = Field(default_factory=list, description="改进建议列表")
    report_path: str | None = Field(default=None, description="持久化报告路径")
