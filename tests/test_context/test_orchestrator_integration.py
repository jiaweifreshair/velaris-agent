"""UOW-4 测试：orchestrator OpenViking 集成。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from velaris_agent.velaris.orchestrator import VelarisBizOrchestrator


class TestOrchestratorOpenVikingIntegration:
    """编排器 OpenViking 集成测试。"""

    def test_orchestrator_accepts_openviking_context(self):
        """编排器接受 openviking_context 参数。"""
        mock_ctx = MagicMock()
        orchestrator = VelarisBizOrchestrator(openviking_context=mock_ctx)
        assert orchestrator.openviking_context is mock_ctx

    def test_orchestrator_default_no_openviking(self):
        """编排器默认不配置 OpenViking。"""
        # 使用 sqlite_database_path 避免初始化问题
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = VelarisBizOrchestrator(
                sqlite_database_path=f"{tmpdir}/test.db"
            )
            assert orchestrator.openviking_context is None

    def test_persist_snapshot_to_viking_without_context(self):
        """无 OpenViking 上下文时快照持久化返回 None。"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = VelarisBizOrchestrator(
                sqlite_database_path=f"{tmpdir}/test.db"
            )
            result = orchestrator._persist_snapshot_to_viking(
                execution_id="exec-123",
                snapshot={"plan": "test"},
            )
            assert result is None

    def test_persist_snapshot_to_viking_with_context(self):
        """有 OpenViking 上下文时快照持久化返回 URI。"""
        mock_ctx = MagicMock()
        mock_ctx.save_snapshot.return_value = "viking://agent/test/snapshots/exec-123/"
        orchestrator = VelarisBizOrchestrator(openviking_context=mock_ctx)
        result = orchestrator._persist_snapshot_to_viking(
            execution_id="exec-123",
            snapshot={"plan": "test"},
        )
        assert result == "viking://agent/test/snapshots/exec-123/"
        mock_ctx.save_snapshot.assert_called_once_with(
            execution_id="exec-123",
            snapshot={"plan": "test"},
        )

    def test_persist_snapshot_to_viking_handles_failure(self):
        """OpenViking 写入失败时不影响主流程。"""
        mock_ctx = MagicMock()
        mock_ctx.save_snapshot.side_effect = Exception("OpenViking down")
        orchestrator = VelarisBizOrchestrator(openviking_context=mock_ctx)
        # 不应抛出异常
        result = orchestrator._persist_snapshot_to_viking(
            execution_id="exec-123",
            snapshot={"plan": "test"},
        )
        assert result is None
