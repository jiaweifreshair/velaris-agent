"""决策记忆数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DecisionRecord(BaseModel):
    """一次决策的完整快照。

    不只记录结果, 而是记录完整上下文:
    用户要什么 + 有哪些选项 + 系统推荐了什么 + 用户选了什么 + 结果如何。
    这些数据是偏好学习和自进化的基础。
    """

    decision_id: str = Field(description="决策唯一 ID")
    user_id: str = Field(description="用户 ID")
    scenario: str = Field(
        description="决策场景或领域, 如 travel / tokencost / robotclaw / career"
    )

    # 输入
    query: str = Field(description="原始意图文本")
    intent: dict[str, Any] = Field(default_factory=dict, description="结构化意图")

    # 过程
    options_discovered: list[dict[str, Any]] = Field(
        default_factory=list, description="发现的所有候选项"
    )
    options_after_filter: list[dict[str, Any]] = Field(
        default_factory=list, description="过滤后的候选项"
    )
    scores: list[dict[str, Any]] = Field(
        default_factory=list, description="评分结果"
    )
    weights_used: dict[str, float] = Field(
        default_factory=dict, description="本次使用的权重 (可能是个性化的)"
    )
    tools_called: list[str] = Field(
        default_factory=list, description="调用的工具列表"
    )

    # 输出
    recommended: dict[str, Any] = Field(
        default_factory=dict, description="系统推荐的选项"
    )
    alternatives: list[dict[str, Any]] = Field(
        default_factory=list, description="备选方案"
    )
    explanation: str = Field(default="", description="推荐理由")

    # 反馈 (异步回填)
    user_choice: dict[str, Any] | None = Field(
        default=None, description="用户最终选了什么 (可能不是推荐的)"
    )
    user_feedback: float | None = Field(
        default=None, ge=0, le=5, description="用户满意度 0-5"
    )
    outcome_notes: str | None = Field(
        default=None, description="结果备注"
    )

    # 元数据
    created_at: datetime = Field(description="创建时间")
    latency_ms: int = Field(default=0, ge=0, description="决策耗时 (毫秒)")


class UserPreferences(BaseModel):
    """用户在某场景下的偏好画像。

    从历史决策中计算得出, 不是用户手动设置的。
    """

    user_id: str = Field(description="用户 ID")
    scenario: str = Field(description="场景")

    # 个性化权重 (从历史选择中学习)
    weights: dict[str, float] = Field(
        default_factory=dict, description="个性化评分权重"
    )

    # 行为模式
    total_decisions: int = Field(default=0, description="总决策次数")
    accepted_recommendation_rate: float = Field(
        default=0.0, description="接受推荐比率 (0-1)"
    )
    average_satisfaction: float | None = Field(
        default=None, description="平均满意度"
    )

    # 常见选择特征
    common_patterns: list[str] = Field(
        default_factory=list,
        description="常见选择模式, 如 '偏好最低价', '偏好舒适', '预算敏感'"
    )

    # 元数据
    last_updated: datetime | None = Field(default=None, description="最后更新时间")
    confidence: float = Field(
        default=0.0, ge=0, le=1,
        description="偏好置信度 (决策越多越高)"
    )
