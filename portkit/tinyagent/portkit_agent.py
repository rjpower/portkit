#!/usr/bin/env python3

from typing import Any

from pydantic import BaseModel

from portkit.tidyllm import FunctionLibrary

# Import all tools to register them
from portkit.tinyagent.context import PortKitContext


def get_portkit_tools():
    """Get all registered PortKit tools as FunctionDescription objects."""
    from pathlib import Path

    from portkit.tidyllm.discover import discover_tools_in_directory
    
    # Use improved directory discovery that returns all tools from discovered files
    # Point to the new unified tools directory
    tools_dir = Path(__file__).parent.parent / "tools"
    return discover_tools_in_directory(
        tools_dir, 
        recursive=True,
        exclude_patterns=["test_*.py", "__pycache__", "*.pyc", "tests/", "__main__.py"]
    )


class PortKitAgent:
    """PortKit-specific agent using TidyLLM foundation."""

    def __init__(self, context: PortKitContext):
        self.context = context

        # Create function library with PortKit tools
        self.library = FunctionLibrary(
            function_descriptions=get_portkit_tools(),
            context=self._create_context_dict(context)
        )

    def _create_context_dict(self, context: PortKitContext) -> dict[str, Any]:
        """Convert PortKitContext to dict for FunctionLibrary."""
        return {
            "console": context.console,
            "project_root": context.project_root,
            "source_map": context.source_map,
            "read_files": context.read_files,
            "interrupt_handler": context.interrupt_handler,
            "config": context.config,
        }

    def get_schemas(self) -> list[dict]:
        """Get OpenAI-compatible tool schemas."""
        return self.library.get_schemas()

    def call_tool(self, tool_call: dict) -> dict:
        """Execute a tool call and return the result."""
        result = self.library.call(tool_call)
        if isinstance(result, BaseModel):
            return result.model_dump()
        return result
