"""Tests for function schema extraction."""

from typing import Any

from pydantic import BaseModel

from portkit.tidyllm.docstring import extract_function_docs
from portkit.tidyllm.schema import (
    FunctionDescription,
    generate_tool_schema,
)


class SimpleArgs(BaseModel):
    """Simple test arguments."""

    name: str
    count: int = 5
    optional_flag: bool | None = None


class ComplexArgs(BaseModel):
    """Complex test arguments."""

    items: list[str]
    metadata: dict[str, Any]
    config: dict[str, str] | None = None


def simple_function(args: SimpleArgs) -> dict:
    """A simple test function.

    Args:
        name: The name parameter
        count: Number of items to process
        optional_flag: Optional boolean flag
    """
    return {"name": args.name, "count": args.count}


def complex_function(args: ComplexArgs) -> dict:
    """A complex test function.

    Args:
        items: List of item names
        metadata: Dictionary of metadata
        config: Optional configuration
    """
    return {"items": args.items, "metadata": args.metadata}


def no_docstring_function(args: SimpleArgs) -> dict:
    return {"result": "no docs"}


async def async_function(args: SimpleArgs) -> dict:
    """An async test function."""
    return {"async": True, "name": args.name}


def multi_param_function(name: str, count: int, tags: list[str], config: dict = None) -> dict:
    """Function with multiple parameters.

    Args:
        name: The name parameter
        count: Number of items
        tags: List of tags
        config: Optional configuration dict
    """
    return {"name": name, "count": count, "tags": tags, "config": config}


def mixed_types_function(
    text: str, number: int, flag: bool, items: list[str], metadata: dict[str, Any]
) -> dict:
    """Function with mixed parameter types.

    Args:
        text: A text string
        number: An integer number
        flag: A boolean flag
        items: List of string items
        metadata: Dictionary of metadata
    """
    return {
        "text": text,
        "number": number,
        "flag": flag,
        "items": items,
        "metadata": metadata,
    }


def optional_params_function(
    required_param: str, optional_int: int = 42, optional_str: str = "default"
) -> dict:
    """Function with optional parameters.

    Args:
        required_param: This parameter is required
        optional_int: Optional integer with default
        optional_str: Optional string with default
    """
    return {
        "required": required_param,
        "opt_int": optional_int,
        "opt_str": optional_str,
    }


def single_primitive_function(message: str) -> dict:
    """Function with single primitive parameter.

    Args:
        message: The message to process
    """
    return {"processed": message}


class TestParameterDocExtraction:
    """Test parameter documentation extraction."""

    def test_extract_docs_with_docstring(self):
        """Test extracting parameter docs from function docstring."""
        docs = extract_function_docs(simple_function)["parameters"]
        assert "name" in docs
        assert "count" in docs
        assert "optional_flag" in docs
        assert docs["name"] == "The name parameter"
        assert docs["count"] == "Number of items to process"
        assert docs["optional_flag"] == "Optional boolean flag"

    def test_extract_docs_no_docstring(self):
        """Test extracting docs from function without docstring."""
        docs = extract_function_docs(no_docstring_function)["parameters"]
        assert docs == {}

    def test_extract_docs_complex_types(self):
        """Test extracting docs for complex parameter types."""
        docs = extract_function_docs(complex_function)["parameters"]
        assert "items" in docs
        assert "metadata" in docs
        assert "config" in docs


class TestFunctionDescription:
    """Test FunctionDescription for argument parsing and validation."""

    def test_function_description_creation_single_pydantic(self):
        """Test creating FunctionDescription for single Pydantic model function."""
        func_desc = FunctionDescription(simple_function)

        assert func_desc.name == "simple_function"
        assert not func_desc.takes_ctx
        assert not func_desc.is_async
        assert func_desc.args_model is not None

    def test_function_description_creation_multi_param(self):
        """Test creating FunctionDescription for multi-parameter function."""
        func_desc = FunctionDescription(multi_param_function)

        assert func_desc.name == "multi_param_function"
        assert not func_desc.takes_ctx
        assert func_desc.args_model is not None

    def test_function_description_creation_single_primitive(self):
        """Test creating FunctionDescription for single primitive function."""
        func_desc = FunctionDescription(single_primitive_function)

        assert func_desc.name == "single_primitive_function"
        assert not func_desc.takes_ctx
        assert func_desc.args_model is not None

    def test_validate_and_parse_args_pydantic_model(self):
        """Test validation and parsing for Pydantic model function."""
        func_desc = FunctionDescription(simple_function)
        json_args = {"name": "test", "count": 10}

        result = func_desc.validate_and_parse_args(json_args)
        assert isinstance(result, dict)
        assert "args" in result
        assert result["args"].name == "test"
        assert result["args"].count == 10

    def test_validate_and_parse_args_multi_param(self):
        """Test validation and parsing for multi-parameter function."""
        func_desc = FunctionDescription(multi_param_function)
        json_args = {
            "name": "test",
            "count": 5,
            "tags": ["a", "b"],
            "config": {"key": "value"},
        }

        result = func_desc.validate_and_parse_args(json_args)
        assert isinstance(result, dict)
        assert result["name"] == "test"
        assert result["count"] == 5
        assert result["tags"] == ["a", "b"]
        assert result["config"] == {"key": "value"}

    def test_validate_and_parse_args_single_primitive(self):
        """Test validation and parsing for single primitive function."""
        func_desc = FunctionDescription(single_primitive_function)
        json_args = {"message": "hello"}

        result = func_desc.validate_and_parse_args(json_args)
        assert isinstance(result, dict)
        assert result["message"] == "hello"

    def test_call_with_json_args_pydantic_model(self):
        """Test calling function with JSON args for Pydantic model."""
        func_desc = FunctionDescription(simple_function)
        json_args = {"name": "test", "count": 10}

        result = func_desc.call_with_json_args(json_args)
        assert result["name"] == "test"
        assert result["count"] == 10

    def test_call_with_json_args_multi_param(self):
        """Test calling function with JSON args for multi-parameter function."""
        func_desc = FunctionDescription(multi_param_function)
        json_args = {"name": "test", "count": 5, "tags": ["a", "b"]}

        result = func_desc.call_with_json_args(json_args)
        assert result["name"] == "test"
        assert result["count"] == 5
        assert result["tags"] == ["a", "b"]


class TestToolSchemaGeneration:
    """Test tool schema generation."""

    def test_generate_schema_simple_function(self):
        """Test generating schema for simple function."""
        schema = generate_tool_schema(simple_function)

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "simple_function"
        assert "A simple test function." in schema["function"]["description"]

        params = schema["function"]["parameters"]
        assert "properties" in params
        assert "name" in params["properties"]
        assert "count" in params["properties"]
        assert "optional_flag" in params["properties"]

    def test_generate_schema_complex_function(self):
        """Test generating schema for function with complex types."""
        schema = generate_tool_schema(complex_function)

        params = schema["function"]["parameters"]
        assert "items" in params["properties"]
        assert "metadata" in params["properties"]
        assert "config" in params["properties"]

        # Check array type
        assert params["properties"]["items"]["type"] == "array"
        # Check object type
        assert params["properties"]["metadata"]["type"] == "object"

    def test_generate_schema_with_doc_override(self):
        """Test generating schema with custom documentation."""
        custom_doc = "Custom documentation for this tool"
        schema = generate_tool_schema(simple_function, doc_override=custom_doc)

        assert schema["function"]["description"] == custom_doc

    def test_generate_schema_no_docstring(self):
        """Test generating schema for function without docstring."""
        schema = generate_tool_schema(no_docstring_function)

        # Should generate default description
        assert schema["function"]["name"] == "no_docstring_function"
        assert "Function no_docstring_function" in schema["function"]["description"]

    def test_generate_schema_async_function(self):
        """Test generating schema for async function."""
        schema = generate_tool_schema(async_function)

        assert schema["function"]["name"] == "async_function"
        assert schema["function"]["description"] == "An async test function."

    def test_generate_schema_parameter_descriptions(self):
        """Test that parameter descriptions are included in schema."""
        schema = generate_tool_schema(simple_function)

        params = schema["function"]["parameters"]
        name_prop = params["properties"]["name"]
        count_prop = params["properties"]["count"]

        assert name_prop["description"] == "The name parameter"
        assert count_prop["description"] == "Number of items to process"

    def test_generate_schema_optional_parameters(self):
        """Test schema generation for optional parameters."""
        schema = generate_tool_schema(simple_function)

        params = schema["function"]["parameters"]
        required = params.get("required", [])

        # name should be required, count and optional_flag should not
        assert "name" in required
        assert "count" not in required  # has default value
        assert "optional_flag" not in required  # is Optional

    def test_generate_schema_type_mapping(self):
        """Test correct JSON Schema type mapping."""
        schema = generate_tool_schema(complex_function)

        params = schema["function"]["parameters"]
        items_prop = params["properties"]["items"]
        metadata_prop = params["properties"]["metadata"]

        assert items_prop["type"] == "array"
        assert items_prop["items"]["type"] == "string"
        assert metadata_prop["type"] == "object"

    def test_generate_schema_multiple_parameters(self):
        """Test schema generation for function with multiple parameters."""
        schema = generate_tool_schema(multi_param_function)

        assert schema["function"]["name"] == "multi_param_function"
        params = schema["function"]["parameters"]

        # Check all parameters are present
        assert "name" in params["properties"]
        assert "count" in params["properties"]
        assert "tags" in params["properties"]
        assert "config" in params["properties"]

        # Check types
        assert params["properties"]["name"]["type"] == "string"
        assert params["properties"]["count"]["type"] == "integer"
        assert params["properties"]["tags"]["type"] == "array"
        assert params["properties"]["tags"]["items"]["type"] == "string"
        assert params["properties"]["config"]["type"] == "object"

        # Check required parameters
        required = params.get("required", [])
        assert "name" in required
        assert "count" in required
        assert "tags" in required
        assert "config" not in required  # Has default value

    def test_generate_schema_mixed_types(self):
        """Test schema generation for function with mixed parameter types."""
        schema = generate_tool_schema(mixed_types_function)

        params = schema["function"]["parameters"]

        # Check all basic types
        assert params["properties"]["text"]["type"] == "string"
        assert params["properties"]["number"]["type"] == "integer"
        assert params["properties"]["flag"]["type"] == "boolean"
        assert params["properties"]["items"]["type"] == "array"
        assert params["properties"]["items"]["items"]["type"] == "string"
        assert params["properties"]["metadata"]["type"] == "object"

        # All parameters should be required
        required = params.get("required", [])
        assert len(required) == 5
        assert all(param in required for param in ["text", "number", "flag", "items", "metadata"])

    def test_generate_schema_single_primitive(self):
        """Test schema generation for function with single primitive parameter."""
        schema = generate_tool_schema(single_primitive_function)

        params = schema["function"]["parameters"]

        # Should have message parameter
        assert "message" in params["properties"]
        assert params["properties"]["message"]["type"] == "string"

        # Should be required
        required = params.get("required", [])
        assert "message" in required

    def test_multi_param_parameter_descriptions(self):
        """Test that parameter descriptions work with multiple parameters."""
        schema = generate_tool_schema(multi_param_function)

        params = schema["function"]["parameters"]

        # Check descriptions from docstring
        assert params["properties"]["name"]["description"] == "The name parameter"
        assert params["properties"]["count"]["description"] == "Number of items"
        assert params["properties"]["tags"]["description"] == "List of tags"
        assert params["properties"]["config"]["description"] == "Optional configuration dict"

    def test_pydantic_model_vs_multi_param(self):
        """Test that single Pydantic model is handled differently from multiple params."""
        # Single Pydantic model function
        pydantic_schema = generate_tool_schema(simple_function)

        # Multiple parameter function
        multi_schema = generate_tool_schema(multi_param_function)

        # Both should have proper structure but different parameter handling
        assert "properties" in pydantic_schema["function"]["parameters"]
        assert "properties" in multi_schema["function"]["parameters"]

        # Pydantic model should have the model's properties
        pydantic_props = pydantic_schema["function"]["parameters"]["properties"]
        assert "name" in pydantic_props
        assert "count" in pydantic_props

        # Multi-param should have function parameters directly
        multi_props = multi_schema["function"]["parameters"]["properties"]
        assert "name" in multi_props
        assert "count" in multi_props
        assert "tags" in multi_props
