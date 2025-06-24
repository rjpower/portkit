"""Tests for tool execution with various argument types."""

from typing import Any

from pydantic import BaseModel

from portkit.tidyllm.library import FunctionLibrary
from portkit.tidyllm.models import ToolError
from portkit.tidyllm.registry import Registry


class SimpleArgs(BaseModel):
    """Simple arguments."""

    name: str
    count: int = 1


class ComplexArgs(BaseModel):
    """Complex arguments with various types."""

    strings: list[str]
    mapping: dict[str, Any]
    optional_int: int | None = None
    flag: bool = False


class NestedArgs(BaseModel):
    """Nested model arguments."""

    class Config(BaseModel):
        timeout: int
        retries: int = 3

    name: str
    config: Config
    tags: list[str] = []


class UnionArgs(BaseModel):
    """Arguments with Union types."""

    value: str | int | float
    optional_data: dict[str, str] | None = None


class SimpleResult(BaseModel):
    """Simple result."""

    processed: str
    count: int


def simple_tool(args: SimpleArgs) -> SimpleResult:
    """Simple tool for testing."""
    return SimpleResult(processed=f"Processed {args.name}", count=args.count * 2)


def complex_tool(args: ComplexArgs) -> dict:
    """Tool with complex argument types."""
    return {
        "strings_count": len(args.strings),
        "mapping_keys": list(args.mapping.keys()),
        "optional_int": args.optional_int,
        "flag": args.flag,
    }


def nested_tool(args: NestedArgs) -> dict:
    """Tool with nested model arguments."""
    return {
        "name": args.name,
        "timeout": args.config.timeout,
        "retries": args.config.retries,
        "tags": args.tags,
    }


def union_tool(args: UnionArgs) -> dict:
    """Tool with union type arguments."""
    return {
        "value": args.value,
        "value_type": type(args.value).__name__,
        "has_optional_data": args.optional_data is not None,
    }


def error_tool(args: SimpleArgs) -> SimpleResult:
    """Tool that raises an error."""
    if args.name == "error":
        raise ValueError("Intentional error for testing")
    return SimpleResult(processed=args.name, count=args.count)


def validation_tool(args: SimpleArgs) -> SimpleResult:
    """Tool that validates arguments strictly."""
    if not args.name:
        raise ValueError("Name cannot be empty")
    if args.count < 0:
        raise ValueError("Count must be non-negative")

    return SimpleResult(processed=args.name, count=args.count)


class TestToolExecution:
    """Test tool execution with various argument patterns."""

    def setup_method(self):
        """Set up test registry and tools."""
        self.registry = Registry()

        # Register all test tools
        tools_and_schemas = [
            simple_tool,
            complex_tool,
            nested_tool,
            union_tool,
            error_tool,
            validation_tool,
        ]

        for tool in tools_and_schemas:
            self.registry.register(tool)

        self.library = FunctionLibrary(registry=self.registry)

    def test_simple_arguments(self):
        """Test execution with simple argument types."""
        request = {"name": "simple_tool", "arguments": {"name": "test", "count": 5}}

        result = self.library.call(request)
        assert isinstance(result, SimpleResult)
        assert result.processed == "Processed test"
        assert result.count == 10

    def test_simple_arguments_with_defaults(self):
        """Test execution using default argument values."""
        request = {
            "name": "simple_tool",
            "arguments": {"name": "default_test"},
            # count not provided, should use default
        }

        result = self.library.call(request)
        assert isinstance(result, SimpleResult)
        assert result.processed == "Processed default_test"
        assert result.count == 2  # default 1 * 2

    def test_complex_arguments(self):
        """Test execution with complex argument types."""
        request = {
            "name": "complex_tool",
            "arguments": {
                "strings": ["apple", "banana", "cherry"],
                "mapping": {"key1": "value1", "key2": 42, "key3": [1, 2, 3]},
                "optional_int": 100,
                "flag": True,
            },
        }

        result = self.library.call(request)
        assert result["strings_count"] == 3
        assert set(result["mapping_keys"]) == {"key1", "key2", "key3"}
        assert result["optional_int"] == 100
        assert result["flag"] is True

    def test_complex_arguments_partial(self):
        """Test complex arguments with only required fields."""
        request = {
            "name": "complex_tool",
            "arguments": {
                "strings": ["single"],
                "mapping": {"only": "one"},
                # optional_int and flag use defaults
            },
        }

        result = self.library.call(request)
        assert result["strings_count"] == 1
        assert result["mapping_keys"] == ["only"]
        assert result["optional_int"] is None
        assert result["flag"] is False

    def test_nested_model_arguments(self):
        """Test execution with nested Pydantic models."""
        request = {
            "name": "nested_tool",
            "arguments": {
                "name": "nested_test",
                "config": {"timeout": 30, "retries": 5},
                "tags": ["tag1", "tag2"],
            },
        }

        result = self.library.call(request)
        assert result["name"] == "nested_test"
        assert result["timeout"] == 30
        assert result["retries"] == 5
        assert result["tags"] == ["tag1", "tag2"]

    def test_nested_model_with_defaults(self):
        """Test nested model with default values."""
        request = {
            "name": "nested_tool",
            "arguments": {
                "name": "default_nested",
                "config": {
                    "timeout": 15
                    # retries uses default
                },
                # tags uses default
            },
        }

        result = self.library.call(request)
        assert result["name"] == "default_nested"
        assert result["timeout"] == 15
        assert result["retries"] == 3  # default value
        assert result["tags"] == []  # default value

    def test_union_type_arguments_string(self):
        """Test union type arguments with string value."""
        request = {
            "name": "union_tool",
            "arguments": {"value": "string_value", "optional_data": {"key": "value"}},
        }

        result = self.library.call(request)
        assert result["value"] == "string_value"
        assert result["value_type"] == "str"
        assert result["has_optional_data"] is True

    def test_union_type_arguments_int(self):
        """Test union type arguments with integer value."""
        request = {"name": "union_tool", "arguments": {"value": 42}}

        result = self.library.call(request)
        assert result["value"] == 42
        assert result["value_type"] == "int"
        assert result["has_optional_data"] is False

    def test_union_type_arguments_float(self):
        """Test union type arguments with float value."""
        request = {"name": "union_tool", "arguments": {"value": 3.14}}

        result = self.library.call(request)
        assert result["value"] == 3.14
        assert result["value_type"] == "float"
        assert result["has_optional_data"] is False

    def test_tool_execution_error(self):
        """Test handling of tool execution errors."""
        request = {"name": "error_tool", "arguments": {"name": "error", "count": 1}}

        result = self.library.call(request)
        assert isinstance(result, ToolError)
        assert "Tool execution failed" in result.error
        assert "Intentional error" in result.error

    def test_tool_validation_error(self):
        """Test tool that performs its own validation."""
        request = {"name": "validation_tool", "arguments": {"name": "", "count": -1}}

        result = self.library.call(request)
        assert isinstance(result, ToolError)
        assert "Tool execution failed" in result.error
        # Should contain the validation error message
        assert (
            "Name cannot be empty" in result.error or "Count must be non-negative" in result.error
        )

    def test_argument_validation_error(self):
        """Test Pydantic argument validation errors."""
        request = {
            "name": "simple_tool",
            "arguments": {"name": "test", "count": "not_a_number"},  # Invalid type
        }

        result = self.library.call(request)
        assert isinstance(result, ToolError)
        assert "Invalid arguments" in result.error
        assert result.details is not None

    def test_missing_required_arguments(self):
        """Test error when required arguments are missing."""
        request = {
            "name": "simple_tool",
            "arguments": {
                # Missing required 'name' field
                "count": 5
            },
        }

        result = self.library.call(request)
        assert isinstance(result, ToolError)
        assert "Invalid arguments" in result.error

    def test_extra_arguments_ignored(self):
        """Test that extra arguments are handled gracefully."""
        request = {
            "name": "simple_tool",
            "arguments": {
                "name": "test",
                "count": 3,
                "extra_field": "ignored",  # Should be ignored
            },
        }

        result = self.library.call(request)
        # Should succeed despite extra field
        assert isinstance(result, SimpleResult)
        assert result.processed == "Processed test"

    def test_empty_arguments(self):
        """Test tool call with empty arguments."""
        request = {"name": "simple_tool", "arguments": {}}

        result = self.library.call(request)
        assert isinstance(result, ToolError)
        assert "Invalid arguments" in result.error
        # Should fail due to missing required 'name'

    def test_null_arguments(self):
        """Test tool call with null argument values."""
        request = {
            "name": "complex_tool",
            "arguments": {
                "strings": ["test"],
                "mapping": {"key": None},  # Null value in dict
                "optional_int": None,  # Explicitly null optional field
                "flag": False,
            },
        }

        result = self.library.call(request)
        # Should handle null values appropriately
        assert result["optional_int"] is None

    def test_deeply_nested_arguments(self):
        """Test with deeply nested argument structures."""
        request = {
            "name": "complex_tool",
            "arguments": {
                "strings": ["nested", "test"],
                "mapping": {
                    "level1": {"level2": {"level3": "deep_value"}},
                    "array": [{"item": 1}, {"item": 2}],
                },
                "flag": True,
            },
        }

        result = self.library.call(request)
        assert result["strings_count"] == 2
        assert "level1" in result["mapping_keys"]
        assert "array" in result["mapping_keys"]

    def test_large_argument_values(self):
        """Test with large argument values."""
        large_list = [f"item_{i}" for i in range(1000)]
        large_dict = {f"key_{i}": f"value_{i}" for i in range(100)}

        request = {
            "name": "complex_tool",
            "arguments": {"strings": large_list, "mapping": large_dict, "flag": True},
        }

        result = self.library.call(request)
        assert result["strings_count"] == 1000
        assert len(result["mapping_keys"]) == 100

    def test_unicode_arguments(self):
        """Test with Unicode and special characters."""
        request = {
            "name": "simple_tool",
            "arguments": {"name": "测试 🚀 émojis ànd spéciål chars", "count": 1},
        }

        result = self.library.call(request)
        assert isinstance(result, SimpleResult)
        assert "测试 🚀 émojis ànd spéciål chars" in result.processed
