"""TidyAgent - Clean tool management for LLMs."""

from portkit.tidyllm.cli import cli_main
from portkit.tidyllm.discover import (
    discover_tools_in_directory,
    discover_tools_in_package,
)
from portkit.tidyllm.library import FunctionLibrary
from portkit.tidyllm.models import ToolError, ToolResult
from portkit.tidyllm.prompt import read_prompt
from portkit.tidyllm.registry import REGISTRY, register
from portkit.tidyllm.schema import FunctionDescription

__all__ = [
    "ToolError",
    "ToolResult",
    "register",
    "read_prompt",
    "REGISTRY",
    "FunctionLibrary",
    "FunctionDescription",
    "cli_main",
    "discover_tools_in_directory",
    "discover_tools_in_package",
]
