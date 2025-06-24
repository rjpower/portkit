"""Core data models for tidyagent tools."""

from typing import Any

from pydantic import BaseModel


class ToolError(BaseModel):
    """Error response from a tool."""

    error: str
    details: dict[str, Any] | None = None


# Tool results can be errors or any JSON-serializable success value
ToolResult = ToolError | Any
