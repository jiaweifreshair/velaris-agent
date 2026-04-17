"""Shared test fixtures."""

from __future__ import annotations

import asyncio
import contextlib

import pytest
import pytest_asyncio


@pytest.fixture(autouse=True)
def cleanup_global_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """隔离宿主机的全局 base_url 环境变量，避免测试被本地配置污染。"""

    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("VELARIS_BASE_URL", raising=False)
    monkeypatch.delenv("OPENHARNESS_BASE_URL", raising=False)


@pytest_asyncio.fixture(autouse=True)
async def cleanup_global_runtime_state():
    """在每个测试后统一回收全局后台资源，避免 subprocess 泄漏到后续测试。"""

    yield

    from openharness.bridge import manager as bridge_manager_module
    from openharness.swarm import registry as backend_registry_module
    from openharness.tasks import manager as task_manager_module

    registry = backend_registry_module._registry
    if registry is not None:
        with contextlib.suppress(KeyError):
            in_process_backend = registry.get_executor("in_process")
            shutdown_all = getattr(in_process_backend, "shutdown_all", None)
            if callable(shutdown_all):
                await shutdown_all(force=True, timeout=1.0)
        backend_registry_module._registry = None

    task_manager = task_manager_module._DEFAULT_MANAGER
    if task_manager is not None:
        for task_id in list(task_manager._tasks.keys()):  # type: ignore[attr-defined]
            with contextlib.suppress(Exception):
                await task_manager.stop_task(task_id)
        for waiter in list(task_manager._waiters.values()):  # type: ignore[attr-defined]
            with contextlib.suppress(Exception):
                await asyncio.wait_for(waiter, timeout=1.0)
        task_manager_module._DEFAULT_MANAGER = None
        task_manager_module._DEFAULT_MANAGER_KEY = None

    bridge_manager = bridge_manager_module._DEFAULT_MANAGER
    if bridge_manager is not None:
        for session_id in list(bridge_manager._sessions.keys()):  # type: ignore[attr-defined]
            with contextlib.suppress(Exception):
                await bridge_manager.stop(session_id)
        for copy_task in list(bridge_manager._copy_tasks.values()):  # type: ignore[attr-defined]
            with contextlib.suppress(Exception):
                await asyncio.wait_for(copy_task, timeout=1.0)
        bridge_manager_module._DEFAULT_MANAGER = None
