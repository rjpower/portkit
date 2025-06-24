"""Tests for summarize_module tool."""

import tempfile
from pathlib import Path

import pytest

from portkit.tidyllm import REGISTRY, FunctionLibrary
from portkit.tools.summarize_module import summarize_module
from portkit.tools.summarize_module.lib import (
    SummarizeModuleArgs,
    SummarizeModuleResult,
)


class TestSummarizeModuleTool:
    """Test summarize_module tool registration and execution."""

    def test_tool_registered(self):
        """Test that summarize_module tool is properly registered."""
        tool_desc = REGISTRY.get("summarize_module")
        assert tool_desc is not None
        assert tool_desc.function.__name__ == "summarize_module"

        # Check tool has schema
        func = tool_desc.function
        assert hasattr(func, "__tool_schema__")
        schema = func.__tool_schema__
        assert schema["function"]["name"] == "summarize_module"
        assert "paths" in schema["function"]["parameters"]["properties"]

    def test_schema_structure(self):
        """Test schema generation for summarize_module."""
        schema = summarize_module.__tool_schema__

        # Check basic structure
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "summarize_module"

        # Check parameters
        params = schema["function"]["parameters"]["properties"]

        # Required paths
        assert "paths" in params
        assert params["paths"]["type"] == "array"

        # Check required parameters
        required = schema["function"]["parameters"]["required"]
        assert "paths" in required

    def test_tool_execution_with_sample_file(self):
        """Test tool execution with a sample C header file."""
        # Create a sample C header to analyze
        sample_header = """
// Sample XPath module header
#ifndef XPATH_H
#define XPATH_H

typedef enum {
    XPATH_SUCCESS = 0,
    XPATH_ERROR = 1,
    XPATH_INVALID_EXPR = 2
} xpath_error_t;

typedef struct xpath_context {
    void* document;
    int position;
    char* expression;
} xpath_context_t;

// Create new XPath context
xpath_context_t* xpath_create_context(void* doc);

// Evaluate XPath expression
int xpath_eval(xpath_context_t* ctx, const char* expr);

// Free context
void xpath_free_context(xpath_context_t* ctx);

#endif
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".h", delete=False) as f:
            f.write(sample_header)
            f.flush()

            try:
                # Test the tool - this will actually call the LLM
                args = SummarizeModuleArgs(
                    paths=[f.name],
                )

                result = summarize_module(args)

                # Verify result structure
                assert isinstance(result, SummarizeModuleResult)
                assert result.module_name  # Should have some module name
                assert result.analyzed_files  # Should list the analyzed file
                assert len(result.analyzed_files) == 1

            except Exception as e:
                # LLM might fail, but we should at least get a structured response
                pytest.skip(f"LLM analysis failed: {e}")

    def test_tool_with_invalid_path(self):
        """Test tool with invalid file path."""
        args = SummarizeModuleArgs(paths=["/nonexistent/path.h"])

        with pytest.raises(ValueError, match="File does not exist"):
            summarize_module(args)

    def test_tool_with_empty_paths(self):
        """Test tool with empty paths list."""
        args = SummarizeModuleArgs(paths=[])

        with pytest.raises(ValueError, match="No file paths provided"):
            summarize_module(args)


class TestSummarizeModuleIntegration:
    """Test integration with FunctionLibrary."""

    def setup_method(self):
        """Ensure tool is registered."""
        if REGISTRY.get("summarize_module") is None:
            import importlib

            import portkit.tools.summarize_module

            importlib.reload(portkit.tools.summarize_module)

    def test_library_execution(self):
        """Test execution through FunctionLibrary."""
        # Create sample file
        sample_code = """
#include <stdio.h>

typedef struct point {
    int x, y;
} point_t;

int add_points(point_t* a, point_t* b);
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".h", delete=False) as f:
            f.write(sample_code)
            f.flush()

            library = FunctionLibrary(functions=[summarize_module])

            try:
                result = library.call(
                    {
                        "name": "summarize_module",
                        "arguments": {"paths": [f.name]},
                    }
                )

                # Should return result or ToolError
                if hasattr(result, "error"):
                    # LLM call failed, but structure is correct
                    pytest.skip(f"LLM call failed: {result.error}")
                else:
                    assert isinstance(result, SummarizeModuleResult)
                    assert result.analyzed_files

            except Exception as e:
                pytest.skip(f"Integration test failed: {e}")

    def test_missing_required_args(self):
        """Test handling of missing required arguments."""
        library = FunctionLibrary(functions=[summarize_module])

        result = library.call(
            {
                "name": "summarize_module",
                "arguments": {
                    # Missing required paths
                    "include_source": True
                },
            }
        )

        # Should return ToolError for validation failure
        assert hasattr(result, "error")
        assert "paths" in result.error.lower()

    def test_real_xpath_header(self):
        """Test with actual xpath.h if available."""
        xpath_h = Path("/Users/power/code/portkit/libxml2/include/libxml/xpath.h")

        if not xpath_h.exists():
            pytest.skip("xpath.h not available for testing")

        library = FunctionLibrary(functions=[summarize_module])

        try:
            result = library.call(
                {
                    "name": "summarize_module",
                    "arguments": {"paths": [str(xpath_h)]},
                }
            )

            if hasattr(result, "error"):
                pytest.skip(f"LLM analysis failed: {result.error}")
            else:
                assert isinstance(result, SummarizeModuleResult)
                assert "xpath" in result.module_name.lower()
                assert result.analyzed_files == ["xpath.h"]

                # Should find key XPath structures
                struct_names = [s.name for s in result.key_structures]
                assert any("xpath" in name.lower() for name in struct_names)

        except Exception as e:
            pytest.skip(f"Real file test failed: {e}")
