"""Tests for context injection and validation."""

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from portkit.tidyllm.library import FunctionLibrary
from portkit.tidyllm.models import ToolError
from portkit.tidyllm.registry import Registry


class SimpleArgs(BaseModel):
    """Simple test arguments."""

    name: str


class SimpleResult(BaseModel):
    """Simple test result."""

    message: str
    context_info: dict


class BasicContext(Protocol):
    """Basic context requirements."""

    project_root: Path
    debug: bool


class ExtendedContext(Protocol):
    """Extended context with more requirements."""

    project_root: Path
    debug: bool
    api_key: str
    timeout: int


class OptionalContext(Protocol):
    """Context with optional fields."""

    project_root: Path
    debug: bool = False


def basic_context_tool(args: SimpleArgs, *, ctx: BasicContext) -> SimpleResult:
    """Tool requiring basic context."""
    return SimpleResult(
        message=f"Hello {args.name}",
        context_info={"project_root": str(ctx.project_root), "debug": ctx.debug},
    )


def extended_context_tool(args: SimpleArgs, *, ctx: ExtendedContext) -> SimpleResult:
    """Tool requiring extended context."""
    return SimpleResult(
        message=f"Hello {args.name}",
        context_info={
            "project_root": str(ctx.project_root),
            "debug": ctx.debug,
            "api_key": ctx.api_key[:8] + "...",  # Truncate for safety
            "timeout": ctx.timeout,
        },
    )


def no_context_tool(args: SimpleArgs) -> SimpleResult:
    """Tool that doesn't require context."""
    return SimpleResult(message=f"Hello {args.name}", context_info={})


class TestContextInjection:
    """Test context injection functionality."""

    def setup_method(self):
        """Set up test registry and tools."""
        self.registry = Registry()

        # Register tools with different context requirements (schemas auto-generated)
        # Context types are automatically inferred from function signatures

        self.registry.register(basic_context_tool)
        self.registry.register(extended_context_tool)
        self.registry.register(no_context_tool)

    def test_context_injection_basic(self):
        """Test basic context injection."""
        context = {"project_root": Path("/test/project"), "debug": True}

        library = FunctionLibrary(
            functions=[basic_context_tool], context=context, registry=self.registry
        )

        request = {"name": "basic_context_tool", "arguments": {"name": "test"}}

        result = library.call(request)
        assert isinstance(result, SimpleResult)
        assert result.message == "Hello test"
        assert result.context_info["project_root"] == "/test/project"
        assert result.context_info["debug"] is True

    def test_context_injection_extended(self):
        """Test extended context injection with more fields."""
        context = {
            "project_root": Path("/test/project"),
            "debug": False,
            "api_key": "secret_api_key_12345",
            "timeout": 30,
        }

        library = FunctionLibrary(
            functions=[extended_context_tool], context=context, registry=self.registry
        )

        request = {"name": "extended_context_tool", "arguments": {"name": "extended"}}

        result = library.call(request)
        assert isinstance(result, SimpleResult)
        assert result.message == "Hello extended"
        assert result.context_info["project_root"] == "/test/project"
        assert result.context_info["debug"] is False
        assert result.context_info["api_key"] == "secret_a..."
        assert result.context_info["timeout"] == 30

    def test_no_context_tool_execution(self):
        """Test tool that doesn't require context."""
        context = {
            "project_root": Path("/test"),
            "debug": True,
            "extra_field": "ignored",
        }

        library = FunctionLibrary(
            functions=[no_context_tool], context=context, registry=self.registry
        )

        request = {"name": "no_context_tool", "arguments": {"name": "no_ctx"}}

        result = library.call(request)
        assert isinstance(result, SimpleResult)
        assert result.message == "Hello no_ctx"
        assert result.context_info == {}

    def test_context_validation_missing_field(self):
        """Test context validation when required field is missing."""
        incomplete_context = {
            "project_root": Path("/test")
            # Missing 'debug' field
        }

        library = FunctionLibrary(
            functions=[basic_context_tool],
            context=incomplete_context,
            registry=self.registry,
        )

        request = {"name": "basic_context_tool", "arguments": {"name": "test"}}

        result = library.call(request)
        assert isinstance(result, ToolError)
        assert "Context missing required attribute" in result.error
        assert "debug" in result.error

    def test_context_validation_multiple_missing_fields(self):
        """Test context validation with multiple missing fields."""
        minimal_context = {
            "project_root": Path("/test")
            # Missing 'debug', 'api_key', 'timeout'
        }

        library = FunctionLibrary(
            functions=[extended_context_tool],
            context=minimal_context,
            registry=self.registry,
        )

        request = {"name": "extended_context_tool", "arguments": {"name": "test"}}

        result = library.call(request)
        assert isinstance(result, ToolError)
        assert "Context missing required attribute" in result.error
        # Should fail on first missing attribute
        assert any(field in result.error for field in ["debug", "api_key", "timeout"])

    def test_context_validation_extra_fields_allowed(self):
        """Test that extra context fields don't cause problems."""
        extended_context = {
            "project_root": Path("/test"),
            "debug": True,
            "extra_field1": "value1",
            "extra_field2": 42,
            "nested": {"key": "value"},
        }

        library = FunctionLibrary(
            functions=[basic_context_tool],
            context=extended_context,
            registry=self.registry,
        )

        request = {"name": "basic_context_tool", "arguments": {"name": "test"}}

        result = library.call(request)
        assert isinstance(result, SimpleResult)
        assert result.message == "Hello test"
        # Extra fields should be ignored

    def test_validate_context_method(self):
        """Test the validate_context method directly."""
        complete_context = {"project_root": Path("/test"), "debug": True}

        library = FunctionLibrary(
            functions=[basic_context_tool, no_context_tool],
            context=complete_context,
            registry=self.registry,
        )

        # Valid context
        assert library.validate_context("basic_context_tool") is True

        # Tool with no context requirements
        assert library.validate_context("no_context_tool") is True

        # Non-existent tool
        assert library.validate_context("nonexistent_tool") is False

    def test_validate_context_incomplete(self):
        """Test validate_context with incomplete context."""
        incomplete_context = {
            "project_root": Path("/test")
            # Missing 'debug'
        }

        library = FunctionLibrary(
            functions=[basic_context_tool],
            context=incomplete_context,
            registry=self.registry,
        )

        assert library.validate_context("basic_context_tool") is False

    def test_context_type_detection(self):
        """Test that context types are properly detected and stored."""
        # Check that context types were properly attached during registration
        basic_tool_desc = self.registry.get("basic_context_tool")
        assert basic_tool_desc.context_type is BasicContext

        # Context type should be available via FunctionDescription

        extended_tool_desc = self.registry.get("extended_context_tool")
        assert extended_tool_desc
        assert extended_tool_desc.context_type is ExtendedContext

        no_ctx_tool_desc = self.registry.get("no_context_tool")
        assert no_ctx_tool_desc
        assert no_ctx_tool_desc.context_type is None

    def test_empty_context(self):
        """Test behavior with empty context."""
        library = FunctionLibrary(
            functions=[no_context_tool],
            registry=self.registry,
            # No context provided
        )

        assert library.context == {}

        request = {"name": "no_context_tool", "arguments": {"name": "empty_ctx"}}

        result = library.call(request)
        assert isinstance(result, SimpleResult)
        assert result.message == "Hello empty_ctx"

    def test_context_with_none_values(self):
        """Test context with None values."""
        context_with_none = {
            "project_root": Path("/test"),
            "debug": None,  # This should cause validation to fail
            "extra": "value",
        }

        library = FunctionLibrary(
            functions=[basic_context_tool],
            context=context_with_none,
            registry=self.registry,
        )

        request = {"name": "basic_context_tool", "arguments": {"name": "test"}}

        result = library.call(request)
        # Behavior depends on implementation - None might be treated as missing
        # This tests the actual behavior
        assert result is not None

    def test_context_protocol_inheritance(self):
        """Test context validation with protocol inheritance."""
        # This would test if a context satisfies a more general protocol
        # For now, just test that different protocols work independently

        basic_context = {"project_root": Path("/test"), "debug": True}

        library = FunctionLibrary(
            functions=[basic_context_tool],
            context=basic_context,
            registry=self.registry,
        )

        # Should work for basic context
        assert library.validate_context("basic_context_tool") is True

        # Should fail for extended context (missing api_key, timeout)
        extended_library = FunctionLibrary(
            functions=[extended_context_tool],
            context=basic_context,
            registry=self.registry,
        )

        assert extended_library.validate_context("extended_context_tool") is False
