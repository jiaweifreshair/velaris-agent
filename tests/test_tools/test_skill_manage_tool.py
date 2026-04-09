"""技能管理工具测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.skill_manage_tool import SkillManageInput, SkillManageTool
from openharness.tools.skill_tool import SkillTool, SkillToolInput


def _context(tmp_path: Path) -> ToolExecutionContext:
    """构造基础工具上下文。"""

    return ToolExecutionContext(cwd=tmp_path)


@pytest.mark.asyncio
async def test_skill_manage_create_and_patch(tmp_path: Path, monkeypatch) -> None:
    """应能创建技能并对 SKILL.md 做定向 patch。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    tool = SkillManageTool()
    context = _context(tmp_path)
    content = (
        "---\n"
        "name: deploy-checklist\n"
        "description: 发布前检查清单\n"
        "---\n\n"
        "# Deploy Checklist\n\n"
        "先运行测试。\n"
    )

    created = await tool.execute(
        SkillManageInput(action="create", name="deploy-checklist", content=content),
        context,
    )
    assert created.is_error is False
    created_payload = json.loads(created.output)
    assert created_payload["success"] is True

    patched = await tool.execute(
        SkillManageInput(
            action="patch",
            name="deploy-checklist",
            old_string="先运行测试。",
            new_string="先运行测试并检查迁移脚本。",
        ),
        context,
    )
    assert patched.is_error is False
    patched_payload = json.loads(patched.output)
    assert patched_payload["success"] is True

    read_result = await SkillTool().execute(
        SkillToolInput(name="deploy-checklist"),
        context,
    )
    assert "检查迁移脚本" in read_result.output


@pytest.mark.asyncio
async def test_skill_manage_support_file_roundtrip(tmp_path: Path, monkeypatch) -> None:
    """应能写入并读取技能支持文件。"""

    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    tool = SkillManageTool()
    context = _context(tmp_path)
    content = (
        "---\n"
        "name: api-migration\n"
        "description: API 迁移流程\n"
        "---\n\n"
        "# API Migration\n\n"
        "主技能内容。\n"
    )
    await tool.execute(
        SkillManageInput(action="create", name="api-migration", content=content),
        context,
    )

    written = await tool.execute(
        SkillManageInput(
            action="write_file",
            name="api-migration",
            file_path="references/checklist.md",
            file_content="1. diff schema\n2. run smoke tests\n",
        ),
        context,
    )
    assert written.is_error is False
    payload = json.loads(written.output)
    assert payload["success"] is True

    support = await SkillTool().execute(
        SkillToolInput(name="api-migration", file_path="references/checklist.md"),
        context,
    )
    assert support.is_error is False
    assert "run smoke tests" in support.output
