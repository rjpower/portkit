#!/usr/bin/env python3
"""Test FastAPI adapter for TidyLLM tools."""

import pytest
from pydantic import BaseModel

from portkit.tidyllm import FunctionLibrary, register

# Skip all tests if FastAPI is not available
fastapi = pytest.importorskip("fastapi")
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from portkit.tidyllm.adapters.fastapi_adapter import create_fastapi_app


class CalculatorArgs(BaseModel):
    """Arguments for calculator tool."""

    operation: str
    left: float
    right: float


@register()
def fastapi_calculator(args: CalculatorArgs) -> dict:
    """Perform basic mathematical operations."""
    if args.operation == "add":
        result = args.left + args.right
    elif args.operation == "subtract":
        result = args.left - args.right
    elif args.operation == "multiply":
        result = args.left * args.right
    elif args.operation == "divide":
        if args.right == 0:
            raise ValueError("Division by zero")
        result = args.left / args.right
    else:
        raise ValueError(f"Unknown operation: {args.operation}")

    return {
        "result": result,
        "expression": f"{args.left} {args.operation} {args.right} = {result}",
    }


@pytest.fixture
def library():
    """Create a FunctionLibrary with test tools."""
    return FunctionLibrary(functions=[fastapi_calculator])


@pytest.fixture
def app(library):
    """Create a FastAPI app with test tools."""
    return create_fastapi_app(library)


@pytest.fixture
def client(app):
    """Create a test client for the FastAPI app."""
    return TestClient(app)


def test_fastapi_app_creation(library):
    """Test that FastAPI app can be created with registered tools."""
    app = create_fastapi_app(library, title="Test API")

    # Verify app was created
    assert app is not None
    assert app.title == "Test API"


def test_fastapi_tool_endpoints(client):
    """Test that tool endpoints are created and work correctly."""
    # Test root endpoint
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert "fastapi_calculator" in data["tools"]

    # Test health endpoint
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["available_tools"] == 1


def test_tool_execution_success(client):
    """Test successful tool execution via FastAPI."""
    # Test calculator tool
    response = client.post(
        "/tools/fastapi_calculator", json={"operation": "add", "left": 10, "right": 5}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["result"] == 15
    assert "expression" in data


def test_tool_execution_error(client):
    """Test tool execution with validation error."""
    # Test calculator tool with division by zero
    response = client.post(
        "/tools/fastapi_calculator",
        json={"operation": "divide", "left": 10, "right": 0},
    )

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "error" in data["detail"]


def test_tool_execution_invalid_args(client):
    """Test tool execution with invalid arguments."""
    # Test calculator tool with missing arguments
    response = client.post(
        "/tools/fastapi_calculator",
        json={
            "operation": "add",
            "left": 10,
            # Missing 'right' argument
        },
    )

    assert response.status_code == 422  # FastAPI validation error


def test_openapi_schema_generation(client):
    """Test that OpenAPI schema is generated correctly."""
    # Get OpenAPI schema
    response = client.get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    assert "paths" in schema
    assert "/tools/fastapi_calculator" in schema["paths"]
    assert "post" in schema["paths"]["/tools/fastapi_calculator"]

    # Check that the tool endpoint has proper schema
    calculator_schema = schema["paths"]["/tools/fastapi_calculator"]["post"]
    assert "requestBody" in calculator_schema
    assert "content" in calculator_schema["requestBody"]
