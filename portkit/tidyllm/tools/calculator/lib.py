"""Calculator tool with merged models for mathematical operations."""

from typing import Literal

from pydantic import BaseModel, Field


# Data Models
class CalculatorArgs(BaseModel):
    """Arguments for calculator operations."""

    operation: Literal["add", "subtract", "multiply", "divide"] = Field(
        description="Mathematical operation to perform",
        examples=["add", "subtract", "multiply", "divide"],
    )

    left: float = Field(description="Left operand (first number)", examples=[10, 5.5, -3.14])

    right: float = Field(description="Right operand (second number)", examples=[5, 2.1, 1.41])


class CalculatorResult(BaseModel):
    """Result of calculator operation."""

    result: float = Field(description="The calculated result")
    operation: str = Field(description="The operation that was performed")
    expression: str = Field(description="Human-readable expression (e.g., '10 + 5 = 15')")


# Core Implementation
def perform_calculation(args: CalculatorArgs) -> CalculatorResult:
    """Perform the requested mathematical operation.

    Args:
        args: Calculator arguments with operation and operands

    Returns:
        CalculatorResult with the computed value

    Raises:
        ValueError: For invalid operations or division by zero
    """
    left, right = args.left, args.right
    operation = args.operation

    if operation == "add":
        result = left + right
        expression = f"{left} + {right} = {result}"
    elif operation == "subtract":
        result = left - right
        expression = f"{left} - {right} = {result}"
    elif operation == "multiply":
        result = left * right
        expression = f"{left} * {right} = {result}"
    elif operation == "divide":
        if right == 0:
            raise ValueError("Cannot divide by zero")
        result = left / right
        expression = f"{left} / {right} = {result}"
    else:
        raise ValueError(f"Unknown operation: {operation}")

    return CalculatorResult(result=result, operation=operation, expression=expression)