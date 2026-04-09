"""后台技能复盘测试。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from openharness.api.client import ApiMessageCompleteEvent, ApiTextDeltaEvent
from openharness.api.usage import UsageSnapshot
from openharness.config.settings import PermissionSettings
from openharness.engine.messages import ConversationMessage, TextBlock, ToolUseBlock
from openharness.engine.query_engine import QueryEngine
from openharness.permissions import PermissionChecker
from openharness.tools import create_default_tool_registry


@dataclass
class _FakeResponse:
    """单轮固定响应。"""

    message: ConversationMessage
    usage: UsageSnapshot


class QueueApiClient:
    """按顺序消费响应的假客户端。"""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)

    async def stream_message(self, request):
        del request
        response = self._responses.pop(0)
        for block in response.message.content:
            if isinstance(block, TextBlock) and block.text:
                yield ApiTextDeltaEvent(text=block.text)
        yield ApiMessageCompleteEvent(
            message=response.message,
            usage=response.usage,
            stop_reason=None,
        )


@pytest.mark.asyncio
async def test_query_engine_runs_background_skill_review(tmp_path: Path, monkeypatch) -> None:
    """达到阈值后应在后台创建技能文件。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    sample = tmp_path / "notes.txt"
    sample.write_text("alpha\nbeta\n", encoding="utf-8")

    review_content = (
        "---\n"
        "name: file-inspection\n"
        "description: 文件排查与结果确认流程\n"
        "---\n\n"
        "# File Inspection\n\n"
        "先读取文件，再总结关键内容。\n"
    )
    api_client = QueueApiClient(
        [
            _FakeResponse(
                message=ConversationMessage(
                    role="assistant",
                    content=[
                        ToolUseBlock(
                            id="toolu_main",
                            name="read_file",
                            input={"path": str(sample), "offset": 0, "limit": 5},
                        )
                    ],
                ),
                usage=UsageSnapshot(input_tokens=3, output_tokens=2),
            ),
            _FakeResponse(
                message=ConversationMessage(
                    role="assistant",
                    content=[TextBlock(text="The file contains alpha and beta.")],
                ),
                usage=UsageSnapshot(input_tokens=3, output_tokens=3),
            ),
            _FakeResponse(
                message=ConversationMessage(
                    role="assistant",
                    content=[
                        ToolUseBlock(
                            id="toolu_review",
                            name="skill_manage",
                            input={
                                "action": "create",
                                "name": "file-inspection",
                                "content": review_content,
                            },
                        )
                    ],
                ),
                usage=UsageSnapshot(input_tokens=2, output_tokens=2),
            ),
            _FakeResponse(
                message=ConversationMessage(
                    role="assistant",
                    content=[TextBlock(text="saved")],
                ),
                usage=UsageSnapshot(input_tokens=2, output_tokens=1),
            ),
        ]
    )

    engine = QueryEngine(
        api_client=api_client,
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        skill_review_interval=1,
    )

    _ = [event async for event in engine.submit_message("inspect this file")]

    target = tmp_path / "config" / "skills" / "file-inspection" / "SKILL.md"
    for _ in range(50):
        if target.exists():
            break
        await asyncio.sleep(0.01)

    assert target.exists()
    assert "先读取文件" in target.read_text(encoding="utf-8")
