"""UOW-4 测试：OpenVikingContext 核心类。

注意：OpenViking SDK 依赖本地存储引擎，部分测试使用 mock 来隔离。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from velaris_agent.context.loading_strategy import LoadingTier
from velaris_agent.context.openviking_context import OpenVikingContext
from velaris_agent.context.uri_scheme import VikingResource, VikingSubject, build_viking_uri


class TestOpenVikingContextInit:
    """OpenVikingContext 初始化测试。"""

    def test_local_mode_default(self):
        """无参数时默认本地模式。"""
        ctx = OpenVikingContext()
        assert ctx.mode == "local"

    def test_local_mode_with_path(self):
        """指定 local_path 时本地模式。"""
        ctx = OpenVikingContext(local_path="/tmp/viking-test")
        assert ctx.mode == "local"

    def test_http_mode_with_base_url(self):
        """指定 base_url 时 HTTP 模式。"""
        ctx = OpenVikingContext(base_url="http://localhost:8080")
        assert ctx.mode == "http"

    def test_local_priority_over_http(self):
        """同时指定 local_path 和 base_url 时优先本地模式。"""
        ctx = OpenVikingContext(
            local_path="/tmp/viking-test",
            base_url="http://localhost:8080",
        )
        assert ctx.mode == "local"

    def test_agent_id_default(self):
        """默认 Agent ID。"""
        ctx = OpenVikingContext()
        assert ctx.agent_id == "velaris-default"

    def test_agent_id_custom(self):
        """自定义 Agent ID。"""
        ctx = OpenVikingContext(agent_id="my-agent")
        assert ctx.agent_id == "my-agent"


class TestOpenVikingContextWriteRead:
    """OpenVikingContext 读写测试（使用 mock）。"""

    def _make_mock_context(self) -> tuple[OpenVikingContext, MagicMock]:
        """创建使用 mock client 的 OpenVikingContext。"""
        ctx = OpenVikingContext(local_path="/tmp/viking-test", agent_id="test-agent")
        mock_client = MagicMock()
        ctx._client = mock_client
        return ctx, mock_client

    def test_write_string_content(self):
        """写入字符串内容。"""
        ctx, mock_client = self._make_mock_context()
        ctx.write("viking://user/alice/preferences/", "hello")
        # 应写入 3 个文件：data.json, _summary.md, _context.md
        assert mock_client.write.call_count == 3

    def test_write_dict_content(self):
        """写入字典内容（自动 JSON 序列化）。"""
        ctx, mock_client = self._make_mock_context()
        ctx.write("viking://user/alice/preferences/", {"theme": "dark"})
        # 验证 data.json 被写入
        data_call = mock_client.write.call_args_list[0]
        content = data_call[0][1]  # 第二个位置参数 = content
        assert json.loads(content) == {"theme": "dark"}

    def test_read_l1_default(self):
        """默认 L1 读取。"""
        ctx, mock_client = self._make_mock_context()
        mock_client.read.return_value = "test content"
        result = ctx.read("viking://user/alice/preferences/")
        mock_client.read.assert_called_once()
        assert result == "test content"

    def test_read_l0_summary(self):
        """L0 读取摘要。"""
        ctx, mock_client = self._make_mock_context()
        mock_client.read.return_value = "summary content"
        result = ctx.read("viking://user/alice/preferences/", tier=LoadingTier.L0_SUMMARY)
        assert result == "summary content"

    def test_read_fallback_on_failure(self):
        """读取失败时降级到 L0。"""
        ctx, mock_client = self._make_mock_context()
        # 第一次读取（L1）失败，第二次（L0 fallback）成功
        mock_client.read.side_effect = [Exception("L1 failed"), "fallback content"]
        result = ctx.read("viking://user/alice/preferences/", tier=LoadingTier.L1_CONTEXT)
        assert result == "fallback content"

    def test_read_returns_empty_on_all_failures(self):
        """所有层级读取失败时返回空字符串。"""
        ctx, mock_client = self._make_mock_context()
        mock_client.read.side_effect = Exception("all failed")
        result = ctx.read("viking://user/alice/preferences/", tier=LoadingTier.L0_SUMMARY)
        assert result == ""

    def test_context_manager(self):
        """上下文管理器协议。"""
        ctx = OpenVikingContext(local_path="/tmp/viking-test")
        mock_client = MagicMock()
        ctx._client = mock_client
        with ctx:
            pass
        mock_client.close.assert_called_once()


class TestOpenVikingContextSnapshots:
    """快照存取测试。"""

    def _make_mock_context(self) -> tuple[OpenVikingContext, MagicMock]:
        ctx = OpenVikingContext(local_path="/tmp/viking-test", agent_id="test-agent")
        mock_client = MagicMock()
        ctx._client = mock_client
        return ctx, mock_client

    def test_save_snapshot_returns_uri(self):
        """保存快照返回 viking:// URI。"""
        ctx, mock_client = self._make_mock_context()
        uri = ctx.save_snapshot("exec-abc123", {"plan": "test"})
        assert uri == "viking://agent/test-agent/snapshots/exec-abc123/"

    def test_save_snapshot_with_custom_agent_id(self):
        """保存快照使用自定义 agent_id。"""
        ctx, mock_client = self._make_mock_context()
        uri = ctx.save_snapshot("exec-abc123", {"plan": "test"}, agent_id="custom-agent")
        assert uri == "viking://agent/custom-agent/snapshots/exec-abc123/"

    def test_load_snapshot_returns_dict(self):
        """加载快照返回字典。"""
        ctx, mock_client = self._make_mock_context()
        mock_client.read.return_value = json.dumps({"plan": "test"})
        result = ctx.load_snapshot("exec-abc123")
        assert result == {"plan": "test"}

    def test_load_snapshot_returns_none_when_empty(self):
        """快照不存在时返回 None。"""
        ctx, mock_client = self._make_mock_context()
        mock_client.read.side_effect = Exception("not found")
        result = ctx.load_snapshot("exec-abc123")
        assert result is None


class TestOpenVikingContextPreferences:
    """偏好存取测试。"""

    def _make_mock_context(self) -> tuple[OpenVikingContext, MagicMock]:
        ctx = OpenVikingContext(local_path="/tmp/viking-test", agent_id="test-agent")
        mock_client = MagicMock()
        ctx._client = mock_client
        return ctx, mock_client

    def test_save_preferences_returns_uri(self):
        """保存偏好返回 viking:// URI。"""
        ctx, mock_client = self._make_mock_context()
        uri = ctx.save_preferences("alice", {"theme": "dark"})
        assert uri == "viking://user/alice/preferences/"

    def test_load_preferences_returns_dict(self):
        """加载偏好返回字典。"""
        ctx, mock_client = self._make_mock_context()
        mock_client.read.return_value = json.dumps({"theme": "dark"})
        result = ctx.load_preferences("alice")
        assert result == {"theme": "dark"}

    def test_load_preferences_returns_none_when_empty(self):
        """偏好不存在时返回 None。"""
        ctx, mock_client = self._make_mock_context()
        mock_client.read.side_effect = Exception("not found")
        result = ctx.load_preferences("alice")
        assert result is None
