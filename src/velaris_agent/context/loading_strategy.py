"""三层加载策略 (L0/L1/L2)。

OpenViking 的核心优化：根据使用场景按需加载不同粒度的上下文，
大幅减少 Token 消耗（相比全量加载可节省 83-96%）。

- L0_SUMMARY (100tok): 快速摘要，用于路由决策
- L1_CONTEXT (2ktok):  上下文摘要，用于规划
- L2_FULL (full):      完整数据，用于执行
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from velaris_agent.context.uri_scheme import VikingURI


class LoadingTier(str, Enum):
    """加载层级。"""

    L0_SUMMARY = "L0"
    L1_CONTEXT = "L1"
    L2_FULL = "L2"


# 各层级的 Token 预算上限
_TIER_TOKEN_BUDGET: dict[LoadingTier, int] = {
    LoadingTier.L0_SUMMARY: 100,
    LoadingTier.L1_CONTEXT: 2000,
    LoadingTier.L2_FULL: -1,  # 无限制
}


# 各层级与 Viking 资源类型的默认映射
# L0 只加载摘要文件（_summary.md）
# L1 加载摘要 + 关键上下文（_context.md）
# L2 加载完整数据
_TIER_FILE_SUFFIX: dict[LoadingTier, str] = {
    LoadingTier.L0_SUMMARY: "_summary.md",
    LoadingTier.L1_CONTEXT: "_context.md",
    LoadingTier.L2_FULL: "",
}


def resolve_loading_tier(
    *,
    uri: VikingURI,
    token_budget: int | None = None,
    scenario: str | None = None,
) -> LoadingTier:
    """根据上下文信息决定加载层级。

    决策逻辑：
    1. 显式 token_budget 优先：预算 < 150 → L0，< 2500 → L1，否则 L2
    2. 场景感知：路由阶段 → L0，规划阶段 → L1，执行阶段 → L2
    3. 默认：L1（上下文摘要）

    Args:
        uri: 目标 VikingURI
        token_budget: 可选的 Token 预算上限
        scenario: 可选的场景提示

    Returns:
        推荐的加载层级
    """
    if token_budget is not None:
        if token_budget <= 0:
            return LoadingTier.L0_SUMMARY
        if token_budget <= _TIER_TOKEN_BUDGET[LoadingTier.L0_SUMMARY] + 50:
            return LoadingTier.L0_SUMMARY
        if token_budget <= _TIER_TOKEN_BUDGET[LoadingTier.L1_CONTEXT] + 500:
            return LoadingTier.L1_CONTEXT
        return LoadingTier.L2_FULL

    # 场景感知
    if scenario in ("routing", "route", "gate"):
        return LoadingTier.L0_SUMMARY
    if scenario in ("planning", "plan", "score"):
        return LoadingTier.L1_CONTEXT
    if scenario in ("execution", "execute", "run"):
        return LoadingTier.L2_FULL

    # 默认 L1
    return LoadingTier.L1_CONTEXT


def get_tier_token_budget(tier: LoadingTier) -> int:
    """获取指定层级的 Token 预算上限。

    Returns -1 表示无限制（L2_FULL）。
    """
    return _TIER_TOKEN_BUDGET[tier]


def resolve_target_path(uri: VikingURI, tier: LoadingTier) -> str:
    """根据加载层级计算 OpenViking 中的目标路径。

    L0 加载摘要文件，L1 加载上下文文件，L2 加载完整目录。

    Args:
        uri: VikingURI
        tier: 加载层级

    Returns:
        OpenViking 中的目标路径
    """
    base = uri.to_openviking_path().rstrip("/")
    suffix = _TIER_FILE_SUFFIX[tier]

    if suffix:
        # L0/L1: 指向特定摘要文件
        return f"{base}{suffix}"
    # L2: 指向完整目录
    return f"{base}/"


def truncate_to_budget(content: str, tier: LoadingTier) -> str:
    """将内容截断到指定层级的 Token 预算内。

    粗略估算：1 token ≈ 4 字符（英文）或 1.5 字符（中文），
    取 2 字符/token 作为混合折中。

    Args:
        content: 原始内容
        tier: 加载层级

    Returns:
        截断后的内容
    """
    budget = _TIER_TOKEN_BUDGET[tier]
    if budget <= 0:
        return content  # L2 无限制

    # 混合估算：2 字符/token
    max_chars = budget * 2
    if len(content) <= max_chars:
        return content

    # 截断并加省略标记
    return content[: max_chars - 3] + "..."
