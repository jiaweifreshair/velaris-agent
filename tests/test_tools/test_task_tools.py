"""Tests for task and team tools."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from openharness.tasks import get_task_manager
from openharness.tools.agent_tool import AgentTool, AgentToolInput
from openharness.tools.base import ToolExecutionContext
from openharness.tools.task_create_tool import TaskCreateTool, TaskCreateToolInput
from openharness.tools.task_output_tool import TaskOutputTool, TaskOutputToolInput
from openharness.tools.task_update_tool import TaskUpdateTool, TaskUpdateToolInput
from openharness.tools.team_create_tool import TeamCreateTool, TeamCreateToolInput


async def _drain_task(manager, task_id: str) -> None:
    """等待后台任务收口，避免测试结束时残留 subprocess transport。"""

    waiter = manager._waiters.get(task_id)  # type: ignore[attr-defined]
    if waiter is not None:
        await asyncio.wait_for(waiter, timeout=5)


@pytest.mark.asyncio
async def test_task_create_and_output_tool(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    context = ToolExecutionContext(cwd=tmp_path)

    create_result = await TaskCreateTool().execute(
        TaskCreateToolInput(
            type="local_bash",
            description="echo",
            command="printf 'tool task'",
        ),
        context,
    )
    assert create_result.is_error is False
    task_id = create_result.output.split()[2]

    manager = get_task_manager()
    for _ in range(20):
        if "tool task" in manager.read_task_output(task_id):
            break
        await asyncio.sleep(0.1)
    output_result = await TaskOutputTool().execute(
        TaskOutputToolInput(task_id=task_id),
        context,
    )
    assert "tool task" in output_result.output
    await _drain_task(manager, task_id)


@pytest.mark.asyncio
async def test_team_create_tool(tmp_path: Path):
    result = await TeamCreateTool().execute(
        TeamCreateToolInput(name="demo", description="test"),
        ToolExecutionContext(cwd=tmp_path),
    )
    assert result.is_error is False
    assert "Created team demo" == result.output


@pytest.mark.asyncio
async def test_task_update_tool_updates_metadata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    context = ToolExecutionContext(cwd=tmp_path)

    create_result = await TaskCreateTool().execute(
        TaskCreateToolInput(
            type="local_bash",
            description="updatable",
            command="printf 'tool task'",
        ),
        context,
    )
    task_id = create_result.output.split()[2]

    update_result = await TaskUpdateTool().execute(
        TaskUpdateToolInput(
            task_id=task_id,
            progress=60,
            status_note="waiting on verification",
            description="renamed task",
        ),
        context,
    )
    assert update_result.is_error is False

    task = get_task_manager().get_task(task_id)
    assert task is not None
    assert task.description == "renamed task"
    assert task.metadata["progress"] == "60"
    assert task.metadata["status_note"] == "waiting on verification"
    await _drain_task(get_task_manager(), task_id)


@pytest.mark.asyncio
async def test_agent_tool_supports_remote_and_teammate_modes(tmp_path: Path, monkeypatch):
    # 重置单例, 确保测试中使用同一个 manager
    from openharness.tasks import manager as _mgr_mod
    _mgr_mod._DEFAULT_MANAGER = None
    _mgr_mod._DEFAULT_MANAGER_KEY = None
    monkeypatch.setenv("VELARIS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    context = ToolExecutionContext(cwd=tmp_path)

    import re

    # 在没有 tmux 的环境下, 所有模式 fallback 到 in_process backend,
    # 第二次 spawn 会因 "already running" 失败, 因此只测试一次
    result = await AgentTool().execute(
        AgentToolInput(
            description="remote_agent smoke",
            prompt="ready",
            mode="remote_agent",
            command="python3 -u -c \"import sys; print(sys.stdin.readline().strip())\"",
        ),
        context,
    )
    assert result.is_error is False, f"spawn failed: {result.output}"
    m = re.search(r"task_id=(\S+?)[\s,)]", result.output)
    assert m is not None, f"Could not extract task_id from: {result.output}"
    assert len(m.group(1)) > 0
    assert "backend=" in result.output
    task = get_task_manager().get_task(m.group(1))
    if task is not None:
        await get_task_manager().stop_task(m.group(1))
        await _drain_task(get_task_manager(), m.group(1))
