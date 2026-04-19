"""File reading tool."""

from __future__ import annotations


from pydantic import BaseModel, Field

from openharness.config.settings import SecuritySettings
from openharness.security import (
    looks_like_sensitive_read_path,
    redact_sensitive_text,
    resolve_tool_path,
)
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class FileReadToolInput(BaseModel):
    """Arguments for the file read tool."""

    path: str = Field(description="Path of the file to read")
    offset: int = Field(default=0, ge=0, description="Zero-based starting line")
    limit: int = Field(default=200, ge=1, le=2000, description="Number of lines to return")


class FileReadTool(BaseTool):
    """Read a UTF-8 text file with line numbers."""

    name = "read_file"
    description = "Read a text file from the local repository."
    input_model = FileReadToolInput

    def is_read_only(self, arguments: FileReadToolInput) -> bool:  # type: ignore[override]
        del arguments
        return True

    async def execute(  # type: ignore[override]
        self,
        arguments: FileReadToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        security_settings_raw = context.metadata.get("security_settings")
        if isinstance(security_settings_raw, SecuritySettings):
            security_settings = security_settings_raw
        elif isinstance(security_settings_raw, dict):
            security_settings = SecuritySettings.model_validate(security_settings_raw)
        else:
            security_settings = SecuritySettings()

        path = resolve_tool_path(context.cwd, arguments.path)
        if not path.exists():
            return ToolResult(output=f"File not found: {path}", is_error=True)
        if path.is_dir():
            return ToolResult(output=f"Cannot read directory: {path}", is_error=True)

        raw = path.read_bytes()
        if b"\x00" in raw:
            return ToolResult(output=f"Binary file cannot be read as text: {path}", is_error=True)

        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        selected = lines[arguments.offset : arguments.offset + arguments.limit]
        numbered = [
            f"{arguments.offset + index + 1:>6}\t{line}"
            for index, line in enumerate(selected)
        ]
        if not numbered:
            return ToolResult(output=f"(no content in selected range for {path})")
        output = "\n".join(numbered)
        if security_settings.redact_secrets or looks_like_sensitive_read_path(path):
            output = redact_sensitive_text(output, enabled=True)
        return ToolResult(output=output)
