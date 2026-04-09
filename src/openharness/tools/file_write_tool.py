"""File writing tool."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from openharness.security import is_protected_write_path, resolve_tool_path
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class FileWriteToolInput(BaseModel):
    """Arguments for the file write tool."""

    path: str = Field(description="Path of the file to write")
    content: str = Field(description="Full file contents")
    create_directories: bool = Field(default=True)


class FileWriteTool(BaseTool):
    """Write complete file contents."""

    name = "write_file"
    description = "Create or overwrite a text file in the local repository."
    input_model = FileWriteToolInput

    async def execute(  # type: ignore[override]
        self,
        arguments: FileWriteToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        path = resolve_tool_path(context.cwd, arguments.path)
        if is_protected_write_path(path):
            return ToolResult(
                output=f"Write denied: {path} 是受保护的系统或凭据文件。",
                is_error=True,
            )
        if arguments.create_directories:
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(arguments.content, encoding="utf-8")
        return ToolResult(output=f"Wrote {path}")
