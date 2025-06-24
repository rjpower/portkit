"""Tests for context injection and validation."""

from dataclasses import dataclass
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

@dataclass
class BasicContextImpl:
  project_root: Path
  debug: bool

@dataclass
class ExtendedContextImpl:
  project_root: Path
  debug: bool
  api_key: str
  timeout: int

@dataclass
class OptionalContextImpl:
  project_root: Path
  debug: bool | None


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
        context = BasicContextImpl(project_root=Path("/test/project"), debug=True)

        library = FunctionLibrary(
            functions=[basic_context_tool], context=context, registry=self.registry
        )

        result = library.call("basic_context_tool", {"name": "test"})
        assert result.message == "Hello test"
        assert result.context_info["project_root"] == "/test/project"
        assert result.context_info["debug"] is True

    def test_context_injection_extended(self):
        """Test extended context injection with more fields."""
        context = ExtendedContextImpl(project_root=Path("/test/project"), debug=False, api_key="secret_api_key_12345", timeout=30)

        library = FunctionLibrary(
            functions=[extended_context_tool], context=context, registry=self.registry
        )

        result = library.call("extended_context_tool", {"name": "extended"})
        assert result.message == "Hello extended"
        assert result.context_info["project_root"] == "/test/project"
        assert result.context_info["debug"] is False
        assert result.context_info["api_key"] == "secret_a..."
        assert result.context_info["timeout"] == 30

    def test_no_context_tool_execution(self):
        """Test tool that doesn't require context."""
        context = OptionalContextImpl(project_root=Path("/test"), debug=True)

        library = FunctionLibrary(
            functions=[no_context_tool], context=context, registry=self.registry
        )

        result = library.call("no_context_tool", {"name": "no_ctx"})
        assert result.message == "Hello no_ctx"
        assert result.context_info == {}

    def test_context_validation_extra_fields_allowed(self):
        """Test that extra context fields don't cause problems."""
        extended_context = ExtendedContextImpl(project_root=Path("/test"), debug=True, api_key="", timeout=0)

        library = FunctionLibrary(
            functions=[basic_context_tool],
            context=extended_context,
            registry=self.registry,
        )

        result = library.call("basic_context_tool", {"name": "test"})
        assert result.message == "Hello test"
        # Extra fields should be ignored

    def test_empty_context(self):
        """Test behavior with empty context."""
        library = FunctionLibrary(
            functions=[no_context_tool],
            registry=self.registry,
            # No context provided
        )

        assert library.context == {}

        result = library.call("no_context_tool", {"name": "empty_ctx"})
        assert result.message == "Hello empty_ctx"

    def test_context_with_none_values(self):
        """Test context with None values."""
        context_with_none = OptionalContextImpl(project_root=Path("/test"), debug=False)

        library = FunctionLibrary(
            functions=[basic_context_tool],
            context=context_with_none,
            registry=self.registry,
        )

        result = library.call("basic_context_tool", {"name": "test"})
        assert result.message == "Hello test"
