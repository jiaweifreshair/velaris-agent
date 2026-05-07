"""UOW-4 测试：三层加载策略。"""

from __future__ import annotations


from velaris_agent.context.loading_strategy import (
    LoadingTier,
    get_tier_token_budget,
    resolve_loading_tier,
    resolve_target_path,
    truncate_to_budget,
)
from velaris_agent.context.uri_scheme import build_viking_uri


class TestLoadingTierResolution:
    """加载层级决策测试。"""

    def test_l0_for_low_budget(self):
        """极低 token 预算 → L0。"""
        uri = build_viking_uri("user", "alice", "preferences")
        tier = resolve_loading_tier(uri=uri, token_budget=50)
        assert tier == LoadingTier.L0_SUMMARY

    def test_l0_for_budget_under_150(self):
        """token 预算 ≤ 150 → L0。"""
        uri = build_viking_uri("user", "alice", "preferences")
        tier = resolve_loading_tier(uri=uri, token_budget=150)
        assert tier == LoadingTier.L0_SUMMARY

    def test_l1_for_medium_budget(self):
        """token 预算 ≤ 2500 → L1。"""
        uri = build_viking_uri("user", "alice", "preferences")
        tier = resolve_loading_tier(uri=uri, token_budget=2500)
        assert tier == LoadingTier.L1_CONTEXT

    def test_l2_for_high_budget(self):
        """token 预算 > 2500 → L2。"""
        uri = build_viking_uri("user", "alice", "preferences")
        tier = resolve_loading_tier(uri=uri, token_budget=5000)
        assert tier == LoadingTier.L2_FULL

    def test_l0_for_zero_budget(self):
        """token 预算 = 0 → L0。"""
        uri = build_viking_uri("user", "alice", "preferences")
        tier = resolve_loading_tier(uri=uri, token_budget=0)
        assert tier == LoadingTier.L0_SUMMARY

    def test_scenario_routing_uses_l0(self):
        """路由场景 → L0。"""
        uri = build_viking_uri("user", "alice", "preferences")
        tier = resolve_loading_tier(uri=uri, scenario="routing")
        assert tier == LoadingTier.L0_SUMMARY

    def test_scenario_planning_uses_l1(self):
        """规划场景 → L1。"""
        uri = build_viking_uri("user", "alice", "preferences")
        tier = resolve_loading_tier(uri=uri, scenario="planning")
        assert tier == LoadingTier.L1_CONTEXT

    def test_scenario_execution_uses_l2(self):
        """执行场景 → L2。"""
        uri = build_viking_uri("user", "alice", "preferences")
        tier = resolve_loading_tier(uri=uri, scenario="execution")
        assert tier == LoadingTier.L2_FULL

    def test_default_is_l1(self):
        """无预算和场景时默认 L1。"""
        uri = build_viking_uri("user", "alice", "preferences")
        tier = resolve_loading_tier(uri=uri)
        assert tier == LoadingTier.L1_CONTEXT

    def test_budget_takes_priority_over_scenario(self):
        """显式 token_budget 优先于场景。"""
        uri = build_viking_uri("user", "alice", "preferences")
        # 场景是执行（L2），但预算很低（L0）
        tier = resolve_loading_tier(uri=uri, token_budget=50, scenario="execution")
        assert tier == LoadingTier.L0_SUMMARY


class TestTierTokenBudget:
    """Token 预算上限测试。"""

    def test_l0_budget(self):
        """L0 预算 = 100 tok。"""
        assert get_tier_token_budget(LoadingTier.L0_SUMMARY) == 100

    def test_l1_budget(self):
        """L1 预算 = 2000 tok。"""
        assert get_tier_token_budget(LoadingTier.L1_CONTEXT) == 2000

    def test_l2_budget_unlimited(self):
        """L2 无限制。"""
        assert get_tier_token_budget(LoadingTier.L2_FULL) == -1


class TestResolveTargetPath:
    """目标路径计算测试。"""

    def test_l0_targets_summary_file(self):
        """L0 指向摘要文件。"""
        uri = build_viking_uri("user", "alice", "preferences")
        path = resolve_target_path(uri, LoadingTier.L0_SUMMARY)
        assert path.endswith("_summary.md")

    def test_l1_targets_context_file(self):
        """L1 指向上下文文件。"""
        uri = build_viking_uri("user", "alice", "preferences")
        path = resolve_target_path(uri, LoadingTier.L1_CONTEXT)
        assert path.endswith("_context.md")

    def test_l2_targets_full_directory(self):
        """L2 指向完整目录。"""
        uri = build_viking_uri("user", "alice", "preferences")
        path = resolve_target_path(uri, LoadingTier.L2_FULL)
        assert path.endswith("/")


class TestTruncateToBudget:
    """内容截断测试。"""

    def test_short_content_not_truncated(self):
        """短内容不截断。"""
        content = "hello world"
        assert truncate_to_budget(content, LoadingTier.L0_SUMMARY) == content

    def test_long_content_truncated_for_l0(self):
        """L0 层级截断长内容。"""
        # L0: 100 tok × 2 chars/tok = 200 chars
        content = "x" * 500
        truncated = truncate_to_budget(content, LoadingTier.L0_SUMMARY)
        assert len(truncated) <= 203  # 200 + "..."
        assert truncated.endswith("...")

    def test_l2_never_truncates(self):
        """L2 永不截断。"""
        content = "x" * 100000
        assert truncate_to_budget(content, LoadingTier.L2_FULL) == content
