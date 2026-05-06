"""UOW-4 测试：persistence factory OpenViking 支持。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from velaris_agent.persistence.factory import (
    _resolve_openviking_path,
    build_openviking_context,
)


class TestResolveOpenVikingPath:
    """OpenViking 路径解析测试。"""

    def test_explicit_path(self):
        """显式路径优先。"""
        result = _resolve_openviking_path("/data/viking", None)
        assert result == "/data/viking"

    def test_from_cwd(self):
        """从 cwd 推导默认路径。"""
        result = _resolve_openviking_path(None, "/project/myapp")
        assert result == str(Path("/project/myapp").resolve() / ".velaris" / "viking")

    def test_explicit_over_cwd(self):
        """显式路径优先于 cwd。"""
        result = _resolve_openviking_path("/data/viking", "/project/myapp")
        assert result == "/data/viking"

    def test_empty_path_returns_none(self):
        """空路径返回 None。"""
        result = _resolve_openviking_path("", None)
        assert result is None

    def test_none_returns_none(self):
        """None 路径返回 None。"""
        result = _resolve_openviking_path(None, None)
        assert result is None


class TestBuildOpenVikingContext:
    """构建 OpenVikingContext 工厂方法测试。"""

    def test_build_with_local_path(self):
        """指定本地路径时构建成功。"""
        ctx = build_openviking_context(
            openviking_path="/tmp/viking-test",
            agent_id="test-agent",
        )
        assert ctx is not None
        assert ctx.mode == "local"
        assert ctx.agent_id == "test-agent"

    def test_build_with_cwd(self):
        """从 cwd 推导路径时构建成功。"""
        ctx = build_openviking_context(cwd="/tmp/test-project")
        assert ctx is not None
        assert ctx.mode == "local"

    def test_build_with_base_url(self):
        """指定 base_url 时构建 HTTP 模式。"""
        ctx = build_openviking_context(
            base_url="http://localhost:8080",
            api_key="test-key",
        )
        assert ctx is not None
        assert ctx.mode == "http"

    def test_build_returns_none_when_no_config(self):
        """无任何配置时返回 None（回退到 SQLite）。"""
        ctx = build_openviking_context()
        assert ctx is None

    def test_local_priority_over_http(self):
        """同时指定 local 和 http 时优先本地模式。"""
        ctx = build_openviking_context(
            openviking_path="/tmp/viking-test",
            base_url="http://localhost:8080",
        )
        assert ctx is not None
        assert ctx.mode == "local"
