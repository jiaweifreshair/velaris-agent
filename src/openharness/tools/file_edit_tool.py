"""String-based file editing tool."""

from __future__ import annotations


from pydantic import BaseModel, Field

from openharness.security import is_protected_write_path, resolve_tool_path
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class FileEditToolInput(BaseModel):
    """Arguments for the file edit tool."""

    path: str = Field(description="Path of the file to edit")
    old_str: str = Field(description="Existing text to replace")
    new_str: str = Field(description="Replacement text")
    replace_all: bool = Field(default=False)


class FileEditTool(BaseTool):
    """Replace text in an existing file."""

    name = "edit_file"
    description = "Edit an existing file by replacing a string."
    input_model = FileEditToolInput

    async def execute(  # type: ignore[override]
        self,
        arguments: FileEditToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        path = resolve_tool_path(context.cwd, arguments.path)
        if is_protected_write_path(path):
            return ToolResult(
                output=f"Write denied: {path} 是受保护的系统或凭据文件。",
                is_error=True,
            )
        if not path.exists():
            return ToolResult(output=f"File not found: {path}", is_error=True)

        original = path.read_text(encoding="utf-8")
        if arguments.old_str not in original:
            return ToolResult(output="old_str was not found in the file", is_error=True)

        if arguments.replace_all:
            updated = original.replace(arguments.old_str, arguments.new_str)
        else:
            updated = original.replace(arguments.old_str, arguments.new_str, 1)

        path.write_text(updated, encoding="utf-8")
        return ToolResult(output=f"Updated {path}")
