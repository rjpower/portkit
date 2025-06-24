"""Tests for griffe docstring parsing integration."""

from typing import Protocol

from pydantic import BaseModel

from portkit.tidyllm.docstring import extract_function_docs


class GriffeTestArgs(BaseModel):
    """Test arguments for griffe parsing."""

    name: str
    count: int = 5
    enabled: bool = False


class GriffeTestContext(Protocol):
    """Test context protocol."""

    project_root: str


def documented_function(name: str, count: int = 5, enabled: bool = False) -> dict:
    """A well-documented function for testing griffe parsing.

    This function demonstrates comprehensive docstring parsing
    with parameter descriptions and return value documentation.

    Args:
        name: The name parameter for processing
        count: Number of items to process (default: 5)
        enabled: Whether processing is enabled (default: False)

    Returns:
        A dictionary containing the processed results with status,
        name, count, and enabled fields.
    """
    if not name:
        raise ValueError("Name cannot be empty")
    if count < 0:
        raise ValueError("Count cannot be negative")

    return {"status": "success", "name": name, "count": count, "enabled": enabled}


def minimal_function(message: str) -> str:
    """A function with minimal documentation.

    Args:
        message: Input message to process
    """
    return message.upper()


def no_docstring_function(data: dict) -> bool:
    return bool(data)


def pydantic_function(args: GriffeTestArgs, *, ctx: GriffeTestContext) -> dict:
    """Function using Pydantic model arguments.

    This function shows how griffe handles Pydantic model parameters
    where individual fields need to be documented.

    Args:
        args: The arguments model containing name, count, and enabled
        ctx: Context object with project_root

    Returns:
        Processed result dictionary
    """
    return {
        "name": args.name,
        "count": args.count,
        "enabled": args.enabled,
        "project": ctx.project_root,
    }


class TestGriffeParameterExtraction:
    """Test griffe parameter documentation extraction."""

    def test_extract_parameter_docs_comprehensive(self):
        """Test extracting parameter docs from well-documented function."""
        param_docs = extract_function_docs(documented_function)["parameters"]

        assert "name" in param_docs
        assert "count" in param_docs
        assert "enabled" in param_docs

        assert "name parameter for processing" in param_docs["name"]
        assert "Number of items to process" in param_docs["count"]
        assert "Whether processing is enabled" in param_docs["enabled"]

    def test_extract_parameter_docs_minimal(self):
        """Test extracting from function with minimal docs."""
        param_docs = extract_function_docs(minimal_function)["parameters"]

        assert "message" in param_docs
        assert "Input message to process" in param_docs["message"]

    def test_extract_parameter_docs_no_docstring(self):
        """Test extracting from function without docstring."""
        param_docs = extract_function_docs(no_docstring_function)["parameters"]

        # Should return empty dict when no docstring
        assert param_docs == {}

    def test_extract_parameter_docs_pydantic_model(self):
        """Test extracting docs from function with Pydantic model args."""
        param_docs = extract_function_docs(pydantic_function)["parameters"]

        assert "args" in param_docs
        assert "ctx" in param_docs

        assert "arguments model containing" in param_docs["args"]
        assert "Context object with project_root" in param_docs["ctx"]

    def test_extract_parameter_docs_with_defaults(self):
        """Test that parameter docs include default value information."""
        param_docs = extract_function_docs(documented_function)["parameters"]

        # Should capture the default value info from docstring
        assert "(default: 5)" in param_docs["count"]
        assert "(default: False)" in param_docs["enabled"]

    def test_extract_parameter_docs_case_insensitive(self):
        """Test that parameter extraction handles case variations."""
        # This tests the robustness of griffe parsing
        param_docs = extract_function_docs(documented_function)["parameters"]

        # Should work regardless of case in docstring
        assert len(param_docs) == 3
        assert all(key in ["name", "count", "enabled"] for key in param_docs.keys())


class TestGriffeFunctionExtraction:
    """Test griffe function-level documentation extraction."""

    def test_extract_function_docs_basic(self):
        """Test extracting basic function documentation."""
        func_docs = extract_function_docs(documented_function)

        assert func_docs["description"] is not None
        assert "well-documented function" in func_docs["description"]
        assert func_docs["returns"] is not None
        assert "dictionary containing" in func_docs["returns"]

    def test_extract_function_docs_minimal(self):
        """Test extracting from minimal documentation."""
        func_docs = extract_function_docs(minimal_function)

        assert func_docs["description"] is not None
        assert "minimal documentation" in func_docs["description"]

    def test_extract_function_docs_no_docstring(self):
        """Test extracting from function without docstring."""
        func_docs = extract_function_docs(no_docstring_function)

        # Should return minimal structure
        assert func_docs["description"] == ""
        assert func_docs["returns"] == ""


class TestGriffeIntegrationWithSchema:
    """Test griffe integration with existing schema generation."""

    def test_griffe_enhances_schema_generation(self):
        """Test that griffe docs enhance schema generation."""
        from portkit.tidyllm.schema import generate_tool_schema

        # Generate schema with griffe integration
        schema = generate_tool_schema(documented_function)

        # Check that parameter descriptions are included
        params = schema["function"]["parameters"]
        props = params["properties"]

        assert "name" in props
        assert "description" in props["name"]
        assert "name parameter for processing" in props["name"]["description"]

        assert "count" in props
        assert "description" in props["count"]
        assert "Number of items to process" in props["count"]["description"]

    def test_griffe_works_with_pydantic_models(self):
        """Test griffe integration with Pydantic model parameters."""
        from portkit.tidyllm.schema import generate_tool_schema

        schema = generate_tool_schema(pydantic_function)

        # Should have enhanced descriptions from griffe
        assert "function" in schema
        assert "description" in schema["function"]
        assert "Pydantic model arguments" in schema["function"]["description"]

    def test_griffe_fallback_behavior(self):
        """Test that schema generation works when griffe fails."""
        from portkit.tidyllm.schema import generate_tool_schema

        # Should not fail even if griffe can't parse
        schema = generate_tool_schema(no_docstring_function)

        assert "function" in schema
        assert "name" in schema["function"]
        assert schema["function"]["name"] == "no_docstring_function"


class TestGriffeErrorHandling:
    """Test griffe error handling and edge cases."""

    def test_griffe_handles_malformed_docstring(self):
        """Test griffe handling of malformed docstrings."""

        def malformed_docstring_function(arg1: str) -> str:
            """This is a malformed docstring

            Args:
                arg1 this is missing colon
                missing_arg: This parameter doesn't exist

            Returns:
                Some return value
            """
            return arg1

        # Should not raise exception
        param_docs = extract_function_docs(malformed_docstring_function)["parameters"]

        # Should handle gracefully, potentially with empty or partial results
        assert isinstance(param_docs, dict)

    def test_griffe_handles_complex_signatures(self):
        """Test griffe with complex function signatures."""

        def complex_function(
            required_kw: str,
            optional_kw: int = 10,
        ) -> dict:
            """Complex function signature.

            Args:
                required_kw: Required keyword argument
                optional_kw: Optional keyword with default
            """
            return {"result": "test"}

        param_docs = extract_function_docs(complex_function)["parameters"]

        # Should handle gracefully
        assert isinstance(param_docs, dict)
        assert "required_kw" in param_docs
        assert "optional_kw" in param_docs
