"""Tests for @register decorator."""

from typing import Protocol

import pytest
from pydantic import BaseModel

from portkit.tidyllm.prompt import read_prompt
from portkit.tidyllm.registry import REGISTRY, register


class DecoratorTestArgs(BaseModel):
    """Test arguments."""

    name: str
    value: int = 10


class DecoratorTestResult(BaseModel):
    """Test result."""

    message: str
    computed: int


class DecoratorTestContext(Protocol):
    """Test context protocol."""

    project_root: str
    debug: bool


class TestRegisterDecorator:
    """Test @register decorator functionality."""

    def setup_method(self):
        """Save registry state before each test."""
        self._saved_tools = REGISTRY._tools.copy()

    def teardown_method(self):
        """Restore registry state after each test."""
        REGISTRY._tools = self._saved_tools

    def test_register_simple_function(self):
        """Test registering a simple function."""

        @register()
        def simple_tool(
            args: DecoratorTestArgs, *, ctx: DecoratorTestContext
        ) -> DecoratorTestResult:
            """A simple test tool."""
            return DecoratorTestResult(message=f"Hello {args.name}", computed=args.value * 2)

        # Check function is registered
        assert "simple_tool" in REGISTRY.list_tools()
        func_desc = REGISTRY.get("simple_tool")
        assert func_desc.function is simple_tool

        # Check metadata is attached
        assert hasattr(simple_tool, "__tool_schema__")
        schema = simple_tool.__tool_schema__
        assert schema["function"]["name"] == "simple_tool"
        assert schema["function"]["description"] == "A simple test tool."

    def test_register_with_custom_doc(self):
        """Test registering with custom documentation."""
        custom_doc = "Custom documentation for this tool"

        @register(doc=custom_doc)
        def documented_tool(
            args: DecoratorTestArgs, *, ctx: DecoratorTestContext
        ) -> DecoratorTestResult:
            """Original docstring."""
            return DecoratorTestResult(message="test", computed=42)

        schema = documented_tool.__tool_schema__
        assert schema["function"]["description"] == custom_doc

    def test_register_with_custom_name(self):
        """Test registering with custom name."""

        @register(name="custom_name")
        def original_name_tool(
            args: DecoratorTestArgs, *, ctx: DecoratorTestContext
        ) -> DecoratorTestResult:
            """A renamed tool."""
            return DecoratorTestResult(message="renamed", computed=1)

        # Should be registered under custom name
        assert "custom_name" in REGISTRY.list_tools()
        assert "original_name_tool" not in REGISTRY.list_tools()

        # Function name should be updated
        assert original_name_tool.__name__ == "custom_name"

        schema = original_name_tool.__tool_schema__
        assert schema["function"]["name"] == "custom_name"

    def test_register_without_context_auto_inferred(self):
        """Test registering function without context (auto-inferred)."""

        @register()
        def no_ctx_tool(args: DecoratorTestArgs) -> DecoratorTestResult:
            """Tool without context."""
            return DecoratorTestResult(message=args.name, computed=args.value)

        assert "no_ctx_tool" in REGISTRY.list_tools()
        # Context type should be None for functions without context
        func_desc = REGISTRY.get("no_ctx_tool")
        assert func_desc.context_type is None

    def test_register_context_auto_inferred_success(self):
        """Test that context requirements are properly auto-inferred."""

        # Function without context - should work fine
        @register()
        def no_context_tool(args: DecoratorTestArgs) -> DecoratorTestResult:
            """Tool without context."""
            return DecoratorTestResult(message="test", computed=1)

        assert "no_context_tool" in REGISTRY.list_tools()

        # Function with context - should also work fine
        @register()
        def with_context_tool(
            args: DecoratorTestArgs, *, ctx: DecoratorTestContext
        ) -> DecoratorTestResult:
            """Tool with context."""
            return DecoratorTestResult(message="test", computed=1)

        assert "with_context_tool" in REGISTRY.list_tools()

    def test_register_ctx_not_keyword_only(self):
        """Test error when ctx parameter is not keyword-only."""
        with pytest.raises(ValueError, match="ctx parameter must be keyword-only"):

            @register()
            def bad_ctx_tool(
                args: DecoratorTestArgs, ctx: DecoratorTestContext
            ) -> DecoratorTestResult:
                """Tool with positional ctx."""
                return DecoratorTestResult(message="test", computed=1)

    def test_register_extracts_context_type(self):
        """Test that context type is properly extracted."""

        @register()
        def typed_ctx_tool(
            args: DecoratorTestArgs, *, ctx: DecoratorTestContext
        ) -> DecoratorTestResult:
            """Tool with typed context."""
            return DecoratorTestResult(message="test", computed=1)

        # Context type should be properly extracted from type hints
        func_desc = REGISTRY.get("typed_ctx_tool")
        assert func_desc.context_type is DecoratorTestContext

    def test_register_with_prompt_file(self):
        """Test registering with prompt file using read_prompt."""
        # This test would need a temporary file
        # For now, test the interface
        try:

            @register(doc=read_prompt("./nonexistent.md"))
            def prompt_tool(
                args: DecoratorTestArgs, *, ctx: DecoratorTestContext
            ) -> DecoratorTestResult:
                """Tool with prompt file."""
                return DecoratorTestResult(message="test", computed=1)

        except FileNotFoundError:
            # Expected when file doesn't exist
            pass

    def test_register_preserves_original_function(self):
        """Test that decorator preserves original function behavior."""

        @register()
        def preserved_tool(
            args: DecoratorTestArgs, *, ctx: DecoratorTestContext
        ) -> DecoratorTestResult:
            """Original behavior preserved."""
            return DecoratorTestResult(message=f"Processed {args.name}", computed=args.value + 100)

        # Should still be callable with original signature
        test_args = DecoratorTestArgs(name="test", value=5)

        class MockContext:
            project_root = "/test"
            debug = False

        result = preserved_tool(test_args, ctx=MockContext())
        assert result.message == "Processed test"
        assert result.computed == 105

    def test_register_function_returns_self(self):
        """Test that register decorator returns the original function."""

        def original_function(
            args: DecoratorTestArgs, *, ctx: DecoratorTestContext
        ) -> DecoratorTestResult:
            """Original function."""
            return DecoratorTestResult(message="original", computed=1)

        decorated = register()(original_function)
        assert decorated is original_function

    def test_register_with_optional_context_type(self):
        """Test registering with optional context type annotation."""

        @register()
        def optional_ctx_tool(
            args: DecoratorTestArgs, *, ctx: DecoratorTestContext | None = None
        ) -> DecoratorTestResult:
            """Tool with optional context."""
            message = "no context" if ctx is None else f"has context: {ctx.project_root}"
            return DecoratorTestResult(message=message, computed=1)

        # Should extract the inner type from Optional
        func_desc = REGISTRY.get("optional_ctx_tool")
        assert func_desc
        # This behavior would need to be defined in implementation
        assert func_desc.context_type is not None

    def test_multiple_registrations(self):
        """Test registering multiple functions."""

        @register()
        def tool_one(args: DecoratorTestArgs, *, ctx: DecoratorTestContext) -> DecoratorTestResult:
            """First tool."""
            return DecoratorTestResult(message="one", computed=1)

        @register()
        def tool_two(args: DecoratorTestArgs, *, ctx: DecoratorTestContext) -> DecoratorTestResult:
            """Second tool."""
            return DecoratorTestResult(message="two", computed=2)

        tools = REGISTRY.list_tools()
        initial_count = len(self._saved_tools)
        assert len(tools) == initial_count + 2
        assert "tool_one" in tools
        assert "tool_two" in tools
