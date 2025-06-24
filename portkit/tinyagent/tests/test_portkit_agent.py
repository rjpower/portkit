#!/usr/bin/env python3

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from portkit.tinyagent.portkit_agent import PortKitAgent, get_portkit_tools
from portkit.tools.list_files import ListFilesResult
from portkit.tools.read_files import ReadFileResult


class MockConfig:

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def rust_src_path(self):
        return Path("rust/src")

    def rust_fuzz_root_path(self):
        return Path("rust/fuzz")

    @property
    def rust_src_dir(self):
        return "rust/src"

    @property 
    def fuzz_dir(self):
        return "rust/fuzz"


class TestPortKitAgent:
    def test_get_portkit_tools(self):
        """Test that expected tools are registered."""
        tools = get_portkit_tools()
        tool_names = [tool.name for tool in tools]

        expected_tools = [
            "edit_code",
            "read_files",
            "search_files",
            "replace_file",
            "list_files",
            "shell",
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Tool {expected} not found in registered tools. Found: {sorted(tool_names)}"

        # Don't assert exact length since other tools might be discovered
        assert len(tools) >= len(expected_tools)

    def test_agent_initialization(self):
        """Test PortKitAgent can be initialized with proper context."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            # Create mock context
            context = MagicMock()
            context.console = Console()
            context.project_root = project_root
            context.source_map = MagicMock()
            context.read_files = set()
            context.interrupt_handler = MagicMock()
            context.config = MockConfig(project_root)

            agent = PortKitAgent(context)

            # Test schemas can be generated
            schemas = agent.get_schemas()
            assert len(schemas) > 0

            # Verify all schemas have required OpenAI format
            for schema in schemas:
                assert "type" in schema
                assert schema["type"] == "function"
                assert "function" in schema
                assert "name" in schema["function"]
                assert "description" in schema["function"]
                assert "parameters" in schema["function"]

    def test_read_files_tool_call(self):
        """Test that read_files tool can be called through the agent."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            # Create a test file
            test_file = project_root / "test.txt"
            test_file.write_text("Hello, World!")

            # Create mock context
            context = MagicMock()
            context.console = Console()
            context.project_root = project_root
            context.source_map = MagicMock()
            context.read_files = set()
            context.interrupt_handler = MagicMock()
            context.config = MockConfig(project_root)

            agent = PortKitAgent(context)

            # Call read_files tool
            tool_call = {
                "name": "read_files",
                "arguments": {"paths": ["test.txt"]}
            }

            result = agent.call_tool(tool_call)
            result = ReadFileResult.model_validate(result)
            assert result.files["test.txt"] == "Hello, World!"

    def test_list_files_tool_call(self):
        """Test that list_files tool can be called through the agent."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            # Create some test files
            (project_root / "test.c").write_text("// C file")
            (project_root / "test.h").write_text("// Header file")
            (project_root / "test.rs").write_text("// Rust file")
            (project_root / "other.txt").write_text("// Text file")

            # Create mock context
            context = MagicMock()
            context.console = Console()
            context.project_root = project_root
            context.source_map = MagicMock()
            context.read_files = set()
            context.interrupt_handler = MagicMock()
            context.config = MockConfig(project_root)

            agent = PortKitAgent(context)

            # Call list_files tool
            tool_call = {
                "name": "list_files",
                "arguments": {"directory": ".", "extensions": ["c", "h", "rs"]}
            }

            result = agent.call_tool(tool_call)
            result = ListFilesResult.model_validate(result)
            files = result.files
            assert "test.c" in files
            assert "test.h" in files  
            assert "test.rs" in files
            assert "other.txt" not in files  # Should be filtered out


# No main execution to avoid conflicts with pytest
