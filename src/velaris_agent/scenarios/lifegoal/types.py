"""人生目标决策数据模型。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LifeDomain(str, Enum):
    """人生决策领域。"""

    CAREER = "career"           # 职业: 跳槽/转行/创业/升学
    FINANCE = "finance"         # 财务: 投资/购房/保险/理财
    HEALTH = "health"           # 健康: 运动/饮食/医疗/心理
    EDUCATION = "education"     # 教育: 技能/考证/留学/培训
    LIFESTYLE = "lifestyle"     # 生活: 城市/居住/时间分配
    RELATIONSHIP = "relationship"  # 关系: 社交/家庭/合作


class DecisionType(str, Enum):
    """决策类型。"""

    BINARY = "binary"           # 是/否 (该不该跳槽?)
    COMPARISON = "comparison"   # A vs B (offer A 还是 B?)
    PLANNING = "planning"       # 如何实现 (怎么转行做 AI?)
    EVALUATION = "evaluation"   # 评估现状 (我的职业状态健康吗?)


class LifeGoalIntent(BaseModel):
    """人生目标决策意图。"""

    query: str = Field(description="用户原始问题")
    domain: LifeDomain = Field(description="决策领域")
    decision_type: DecisionType = Field(description="决策类型")
    context: str = Field(default="", description="背景信息")
    constraints: list[str] = Field(
        default_factory=list,
        description="约束条件, 如 '有房贷', '孩子明年上学', '签证限制'"
    )
    time_horizon: str = Field(
        default="medium",
        description="时间跨度: short(1-3月), medium(1-2年), long(3-10年)"
    )
    risk_tolerance: str = Field(
        default="moderate",
        description="风险偏好: conservative, moderate, aggressive"
    )


class LifeOption(BaseModel):
    """一个人生选项。"""

    id: str = Field(description="选项 ID")
    label: str = Field(description="选项标签, 如 '接受 Offer A'")
    description: str = Field(default="", description="详细描述")
    domain: LifeDomain = Field(description="所属领域")

    # 多维评分 (0-1, 由 Agent 或用户填充)
    dimensions: dict[str, float] = Field(
        default_factory=dict,
        description="评分维度, 如 {income: 0.8, growth: 0.9, balance: 0.6}"
    )

    # 元数据 (领域专属)
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="领域专属数据, 如 {salary: 50000, company: 'xxx', location: '上海'}"
    )

    # 风险与机会
    risks: list[str] = Field(default_factory=list, description="风险点")
    opportunities: list[str] = Field(default_factory=list, description="机会点")


class LifeGoalRecommendation(BaseModel):
    """人生目标推荐结果。"""

    recommended: LifeOption = Field(description="推荐选项")
    alternatives: list[LifeOption] = Field(
        default_factory=list, description="备选方案"
    )
    explanation: str = Field(description="推荐理由 (详细, 有针对性)")
    score_breakdown: dict[str, float] = Field(
        default_factory=dict, description="各维度得分明细"
    )
    action_plan: list[str] = Field(
        default_factory=list, description="可执行的行动清单"
    )
    review_date: str | None = Field(
        default=None,
        description="建议回顾日期 (用于反馈闭环)"
    )
    confidence: float = Field(
        default=0.5, ge=0, le=1,
        description="推荐置信度 (历史数据越多越高)"
    )


# 各领域默认评分维度和权重
DOMAIN_DIMENSIONS: dict[str, dict[str, float]] = {
    "career": {
        "income": 0.25,
        "growth": 0.25,
        "fulfillment": 0.20,
        "stability": 0.15,
        "work_life_balance": 0.15,
    },
    "finance": {
        "expected_return": 0.30,
        "risk": 0.25,
        "liquidity": 0.20,
        "tax_efficiency": 0.15,
        "simplicity": 0.10,
    },
    "health": {
        "effectiveness": 0.30,
        "sustainability": 0.25,
        "cost": 0.15,
        "enjoyment": 0.20,
        "time_required": 0.10,
    },
    "education": {
        "career_impact": 0.30,
        "cost": 0.20,
        "time_investment": 0.20,
        "interest_alignment": 0.20,
        "credential_value": 0.10,
    },
    "lifestyle": {
        "quality_of_life": 0.25,
        "cost_of_living": 0.20,
        "career_opportunity": 0.20,
        "social_network": 0.15,
        "environment": 0.10,
        "convenience": 0.10,
    },
    "relationship": {
        "trust": 0.25,
        "growth": 0.20,
        "compatibility": 0.20,
        "investment": 0.15,
        "reciprocity": 0.20,
    },
}
