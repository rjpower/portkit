"""Tests for calculator tool."""

import pytest

from portkit.tidyllm import REGISTRY, ToolError
from portkit.tidyllm.tools.calculator import calculator
from portkit.tidyllm.tools.calculator.lib import (
    CalculatorArgs,
    CalculatorResult,
    perform_calculation,
)


class TestCalculatorLib:
    """Test core calculator functionality."""

    def test_addition(self):
        """Test addition operation."""
        args = CalculatorArgs(operation="add", left=10, right=5)
        result = perform_calculation(args)

        assert isinstance(result, CalculatorResult)
        assert result.result == 15
        assert result.operation == "add"
        assert result.expression == "10.0 + 5.0 = 15.0"

    def test_subtraction(self):
        """Test subtraction operation."""
        args = CalculatorArgs(operation="subtract", left=10, right=3)
        result = perform_calculation(args)

        assert result.result == 7
        assert result.operation == "subtract"
        assert "10.0 - 3.0 = 7.0" in result.expression

    def test_multiplication(self):
        """Test multiplication operation."""
        args = CalculatorArgs(operation="multiply", left=4, right=6)
        result = perform_calculation(args)

        assert result.result == 24
        assert result.operation == "multiply"

    def test_division(self):
        """Test division operation."""
        args = CalculatorArgs(operation="divide", left=15, right=3)
        result = perform_calculation(args)

        assert result.result == 5
        assert result.operation == "divide"

    def test_division_by_zero(self):
        """Test division by zero error."""
        args = CalculatorArgs(operation="divide", left=10, right=0)

        with pytest.raises(ValueError, match="Cannot divide by zero"):
            perform_calculation(args)

    def test_float_operations(self):
        """Test operations with floating point numbers."""
        args = CalculatorArgs(operation="add", left=3.14, right=2.86)
        result = perform_calculation(args)

        assert abs(result.result - 6.0) < 0.0001  # Float precision

    def test_negative_numbers(self):
        """Test operations with negative numbers."""
        args = CalculatorArgs(operation="multiply", left=-5, right=3)
        result = perform_calculation(args)

        assert result.result == -15


class TestCalculatorTool:
    """Test calculator tool registration and execution."""

    def setup_method(self):
        """Ensure calculator is registered."""
        # If calculator isn't already registered, register it
        if REGISTRY.get("calculator") is None:
            # Import will cause the @register decorator to execute
            import importlib

            import portkit.tidyllm.tools.calculator

            importlib.reload(portkit.tidyllm.tools.calculator)

    def test_tool_registered(self):
        """Test that calculator tool is properly registered."""
        tool_desc = REGISTRY.get("calculator")
        assert tool_desc is not None
        assert tool_desc.function.__name__ == "calculator"

        # Check tool has schema attached
        calculator_func = tool_desc.function
        assert hasattr(calculator_func, "__tool_schema__")
        schema = calculator_func.__tool_schema__
        assert schema["function"]["name"] == "calculator"
        assert "operation" in schema["function"]["parameters"]["properties"]
        assert "left" in schema["function"]["parameters"]["properties"]
        assert "right" in schema["function"]["parameters"]["properties"]

    def test_tool_execution_success(self):
        """Test successful tool execution."""
        args = CalculatorArgs(operation="add", left=8, right=7)
        result = calculator(args)

        assert isinstance(result, CalculatorResult)
        assert result.result == 15
        assert result.operation == "add"

    def test_tool_execution_error(self):
        """Test tool execution with error."""
        args = CalculatorArgs(operation="divide", left=10, right=0)

        with pytest.raises(ValueError, match="Cannot divide by zero"):
            calculator(args)

    def test_schema_generation(self):
        """Test that schema is generated correctly."""
        schema = calculator.__tool_schema__

        # Check basic structure
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "calculator"

        # Check parameters
        params = schema["function"]["parameters"]["properties"]

        # Check operation parameter
        assert "operation" in params
        operation_param = params["operation"]
        assert "enum" in operation_param  # Should have limited values
        assert set(operation_param["enum"]) == {"add", "subtract", "multiply", "divide"}

        # Check number parameters
        assert "left" in params
        assert "right" in params
        assert params["left"]["type"] == "number"
        assert params["right"]["type"] == "number"

        # Check required parameters
        required = schema["function"]["parameters"]["required"]
        assert "operation" in required
        assert "left" in required
        assert "right" in required

    def test_context_not_required(self):
        """Test that calculator doesn't require context."""
        # Calculator should not require context
        func_desc = REGISTRY.get("calculator")
        assert func_desc is not None
        assert func_desc.context_type is None


class TestCalculatorIntegration:
    """Test calculator integration with FunctionLibrary."""

    def setup_method(self):
        """Ensure calculator is registered."""
        # If calculator isn't already registered, register it
        if REGISTRY.get("calculator") is None:
            # Import will cause the @register decorator to execute
            import importlib

            import portkit.tidyllm.tools.calculator

            importlib.reload(portkit.tidyllm.tools.calculator)

    def test_library_execution(self):
        """Test calculator execution through FunctionLibrary."""
        from portkit.tidyllm import FunctionLibrary

        # Create library without context since calculator doesn't need it
        library = FunctionLibrary(functions=[calculator])

        # Execute through library
        result = library.call(
            {
                "name": "calculator",
                "arguments": {"operation": "multiply", "left": 6, "right": 7},
            }
        )

        assert isinstance(result, CalculatorResult)
        assert result.result == 42
        assert result.operation == "multiply"

    def test_library_error_handling(self):
        """Test error handling through FunctionLibrary."""
        from portkit.tidyllm import FunctionLibrary

        library = FunctionLibrary(functions=[calculator])

        result = library.call(
            {
                "name": "calculator",
                "arguments": {"operation": "divide", "left": 5, "right": 0},
            }
        )

        assert isinstance(result, ToolError)
        assert "divide by zero" in result.error.lower()

    def test_invalid_arguments(self):
        """Test handling of invalid arguments."""
        from portkit.tidyllm import FunctionLibrary

        library = FunctionLibrary(functions=[calculator])

        # Missing required argument
        result = library.call(
            {
                "name": "calculator",
                "arguments": {
                    "operation": "add",
                    "left": 5,
                    # Missing 'right'
                },
            }
        )

        # Should return ToolError due to validation failure
        assert isinstance(result, ToolError)
