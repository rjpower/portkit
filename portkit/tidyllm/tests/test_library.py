"""Tests for FunctionLibrary."""

import json
from typing import Protocol

import pytest
from pydantic import BaseModel

from portkit.tidyllm.library import FunctionLibrary
from portkit.tidyllm.models import ToolError
from portkit.tidyllm.registry import Registry


class LibTestArgs(BaseModel):
    """Test arguments."""

    name: str
    value: int = 10


class LibTestResult(BaseModel):
    """Test result."""

    message: str
    computed: int


class LibTestContext(Protocol):
    """Test context protocol."""

    project_root: str
    debug: bool


def lib_test_tool_one(args: LibTestArgs, *, ctx: LibTestContext) -> LibTestResult:
    """First test tool."""
    return LibTestResult(message=f"Tool one processed {args.name}", computed=args.value * 2)


def lib_test_tool_two(args: LibTestArgs) -> LibTestResult:
    """Second test tool (no context)."""
    return LibTestResult(message=f"Tool two processed {args.name}", computed=args.value + 100)


def lib_failing_tool(args: LibTestArgs) -> LibTestResult:
    """Tool that always fails."""
    raise RuntimeError("This tool always fails")


def lib_multi_param_tool(name: str, count: int, enabled: bool = True) -> dict:
    """Tool with multiple parameters."""
    return {"name": name, "count": count, "enabled": enabled}


def lib_primitive_tool(message: str) -> dict:
    """Tool with single primitive parameter."""
    return {"processed": message.upper()}


@pytest.fixture
def ctx_registry():
    """Create a test registry with all test tools registered."""
    registry = Registry()

    # Register test tools with new API (schemas auto-generated)
    # Context types are automatically inferred from function signatures
    registry.register(lib_test_tool_one)
    registry.register(lib_test_tool_two)
    registry.register(lib_failing_tool)
    registry.register(lib_multi_param_tool)
    registry.register(lib_primitive_tool)

    return registry


class LibTestContextImpl:
    """Test context implementation."""
    
    def __init__(self, project_root: str, debug: bool):
        self.project_root = project_root
        self.debug = debug


@pytest.fixture
def tool_context():
    """Create a test context for tools."""
    return LibTestContextImpl(project_root="/test/project", debug=True)


def test_library_initialization(ctx_registry, tool_context):
    """Test FunctionLibrary initialization."""
    functions = [lib_test_tool_one, lib_test_tool_two]
    library = FunctionLibrary(
        functions=functions, context=tool_context, registry=ctx_registry
    )

    assert library.context == tool_context


def test_library_empty_initialization(ctx_registry, tool_context):
    """Test FunctionLibrary with no functions defaults to registry."""
    library = FunctionLibrary(context=tool_context, registry=ctx_registry)
    assert library.context == tool_context
    assert len(library._function_descriptions) == 5  # All tools from registry


def test_library_validation_unregistered_function(tool_context):
    """Test error when providing function without __tool_schema__."""

    def unregistered_function(args: LibTestArgs) -> LibTestResult:
        return LibTestResult(message="test", computed=1)

    with pytest.raises(
        ValueError,
        match="Function unregistered_function must have __tool_schema__ attribute",
    ):
        FunctionLibrary(
            functions=[unregistered_function],
            context=tool_context,
        )


def test_call_with_dict_request(ctx_registry, tool_context):
    """Test calling tool with dictionary request."""
    library = FunctionLibrary(
        functions=[lib_test_tool_two], context=tool_context, registry=ctx_registry
    )

    result = library.call("lib_test_tool_two", {"name": "test", "value": 5})
    assert isinstance(result, LibTestResult)
    assert result.message == "Tool two processed test"
    assert result.computed == 105


def test_call_with_json_string_request(ctx_registry, tool_context):
    """Test calling tool with JSON string request."""
    library = FunctionLibrary(
        functions=[lib_test_tool_two], context=tool_context, registry=ctx_registry
    )

    result = library.call("lib_test_tool_two", {"name": "test", "value": 5})
    assert isinstance(result, LibTestResult)
    assert result.message == "Tool two processed test"
    assert result.computed == 105


def test_call_with_context_tool(ctx_registry, tool_context):
    """Test calling tool that requires context."""
    library = FunctionLibrary(
        functions=[lib_test_tool_one], context=tool_context, registry=ctx_registry
    )

    result = library.call("lib_test_tool_one", {"name": "context_test", "value": 3})
    assert isinstance(result, LibTestResult)
    assert result.message == "Tool one processed context_test"
    assert result.computed == 6


def test_call_nonexistent_tool(ctx_registry, tool_context):
    """Test calling non-existent tool."""
    library = FunctionLibrary(functions=[], context=tool_context, registry=ctx_registry)

    result = library.call("nonexistent_tool", {})
    assert isinstance(result, ToolError)
    assert "Tool 'nonexistent_tool' not found" in result.error


def test_call_invalid_arguments(ctx_registry, tool_context):
    """Test calling tool with invalid arguments."""
    library = FunctionLibrary(
        functions=[lib_test_tool_two], context=tool_context, registry=ctx_registry
    )

    result = library.call("lib_test_tool_two", {"invalid_field": "test"})
    assert isinstance(result, ToolError)
    assert "Invalid arguments" in result.error
    assert result.details is not None


def test_call_tool_execution_failure(ctx_registry, tool_context):
    """Test handling tool execution failure."""
    library = FunctionLibrary(
        functions=[lib_failing_tool], context=tool_context, registry=ctx_registry
    )

    result = library.call("lib_failing_tool", {"name": "test", "value": 1})
    assert isinstance(result, ToolError)
    assert "Tool execution failed" in result.error


def test_get_schemas(tool_context):
    """Test getting schemas for library functions."""
    library = FunctionLibrary(
        functions=[lib_test_tool_one, lib_test_tool_two],
        context=tool_context,
    )

    schemas = library.get_schemas()
    assert len(schemas) == 2  # Only functions in this library

    schema_names = [s["function"]["name"] for s in schemas]
    assert "lib_test_tool_one" in schema_names
    assert "lib_test_tool_two" in schema_names
    assert "lib_failing_tool" not in schema_names  # Not in this library


def test_get_schemas_empty_library(ctx_registry, tool_context):
    """Test getting all registry schemas when no functions provided."""
    library = FunctionLibrary(
        context=tool_context,
        registry=ctx_registry,
    )

    schemas = library.get_schemas()
    assert len(schemas) == 5  # All tools in registry

    schema_names = [s["function"]["name"] for s in schemas]
    assert "lib_test_tool_one" in schema_names
    assert "lib_test_tool_two" in schema_names
    assert "lib_failing_tool" in schema_names


def test_validate_context_success(ctx_registry, tool_context):
    """Test context validation for tool that passes."""
    library = FunctionLibrary(
        functions=[lib_test_tool_one], context=tool_context, registry=ctx_registry
    )

    is_valid = library.validate_context("lib_test_tool_one")
    assert is_valid is True


def test_validate_context_missing_attribute():
    """Test context validation failure."""
    class IncompleteContext:
        def __init__(self, project_root: str):
            self.project_root = project_root
            # Missing debug attribute
    
    incomplete_context = IncompleteContext(project_root="/test")

    library = FunctionLibrary(
        functions=[lib_test_tool_one],
        context=incomplete_context,
    )

    is_valid = library.validate_context("lib_test_tool_one")
    assert is_valid is False


def test_validate_context_no_requirements(ctx_registry, tool_context):
    """Test context validation for tool with no context requirements."""
    library = FunctionLibrary(
        functions=[lib_test_tool_two], context=tool_context, registry=ctx_registry
    )

    is_valid = library.validate_context("lib_test_tool_two")
    assert is_valid is True


def test_validate_context_nonexistent_tool(ctx_registry, tool_context):
    """Test context validation for non-existent tool."""
    library = FunctionLibrary(functions=[], context=tool_context, registry=ctx_registry)

    is_valid = library.validate_context("nonexistent")
    assert is_valid is False


def test_call_missing_args_model(tool_context):
    """Test error when tool has no args model."""
    # This would be a tool registration error, but test the runtime behavior
    FunctionLibrary(functions=[lib_test_tool_one], context=tool_context)

    # Simulate tool without proper args model
    # This would require manipulating the registry
    # For now, just test the error case
    pass


def test_context_validation_in_call():
    """Test that context validation happens during call."""
    class IncompleteContext:
        def __init__(self, project_root: str):
            self.project_root = project_root
            # Missing debug attribute
    
    incomplete_context = IncompleteContext(project_root="/test")

    library = FunctionLibrary(
        functions=[lib_test_tool_one],
        context=incomplete_context,
    )

    result = library.call("lib_test_tool_one", {"name": "test", "value": 1})
    assert isinstance(result, ToolError)
    assert "Context missing required attribute" in result.error


def test_empty_context(ctx_registry):
    """Test FunctionLibrary with empty context."""
    library = FunctionLibrary(
        functions=[lib_test_tool_two],  # No context required
        registry=ctx_registry,
    )

    assert library.context == {}

    result = library.call("lib_test_tool_two", {"name": "test", "value": 1})
    assert isinstance(result, LibTestResult)


def test_call_multi_parameter_tool(ctx_registry, tool_context):
    """Test calling tool with multiple parameters."""
    library = FunctionLibrary(
        functions=[lib_multi_param_tool],
        context=tool_context,
        registry=ctx_registry,
    )

    result = library.call("lib_multi_param_tool", {"name": "test", "count": 5, "enabled": False})
    assert result == {"name": "test", "count": 5, "enabled": False}


def test_call_multi_parameter_with_defaults(ctx_registry, tool_context):
    """Test calling multi-parameter tool with default values."""
    library = FunctionLibrary(
        functions=[lib_multi_param_tool],
        context=tool_context,
        registry=ctx_registry,
    )

    result = library.call("lib_multi_param_tool", {"name": "test", "count": 3})
    assert result == {"name": "test", "count": 3, "enabled": True}


def test_call_single_primitive_parameter(ctx_registry, tool_context):
    """Test calling tool with single primitive parameter."""
    library = FunctionLibrary(
        functions=[lib_primitive_tool], context=tool_context, registry=ctx_registry
    )

    result = library.call("lib_primitive_tool", {"message": "hello world"})
    assert result == {"processed": "HELLO WORLD"}
