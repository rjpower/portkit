"""Tests for tool registry system."""

import pytest
from pydantic import BaseModel

from portkit.tidyllm.registry import REGISTRY, Registry


class RegistryTestArgs(BaseModel):
    """Test arguments model."""

    message: str
    count: int = 1


class RegistryTestResult(BaseModel):
    """Test result model."""

    output: str
    processed_count: int


def registry_test_function(args: RegistryTestArgs) -> RegistryTestResult:
    """A test function for registry."""
    return RegistryTestResult(output=f"Processed: {args.message}", processed_count=args.count)


def another_registry_test_function(args: RegistryTestArgs) -> dict:
    """Another test function."""
    return {"message": args.message, "count": args.count}


class TestRegistry:
    """Test Registry class."""

    def setup_method(self):
        """Set up test registry."""
        self.registry = Registry()

    def test_registry_initialization(self):
        """Test registry initializes empty."""
        assert len(self.registry._tools) == 0
        assert self.registry.list_tools() == []

    def test_register_function(self):
        """Test registering a function."""
        self.registry.register(registry_test_function)

        assert "registry_test_function" in self.registry._tools
        assert self.registry.get("registry_test_function") is not None

    def test_register_duplicate_function(self):
        """Test that registering duplicate function name is silently ignored."""
        self.registry.register(registry_test_function)
        assert len(self.registry.list_tools()) == 1

        # Registering again should be silently ignored
        self.registry.register(registry_test_function)
        assert len(self.registry.list_tools()) == 1

    def test_register_with_context_type(self):
        """Test registering function - context type is auto-inferred from signature."""

        # Note: registry_test_function doesn't actually have a context parameter
        # so this test is testing a function that doesn't need context
        self.registry.register(registry_test_function)

        func_desc = self.registry.get("registry_test_function")
        assert func_desc is not None
        # Since registry_test_function doesn't have a ctx parameter, context_type should be None
        assert func_desc.context_type is None

    def test_get_existing_tool(self):
        """Test getting an existing tool."""
        self.registry.register(registry_test_function)

        func_desc = self.registry.get("registry_test_function")
        assert func_desc is not None
        assert func_desc.function is registry_test_function

        # Test get_function method
        tool_func = self.registry.get_function("registry_test_function")
        assert tool_func is registry_test_function

    def test_get_nonexistent_tool(self):
        """Test getting a non-existent tool."""
        func_desc = self.registry.get("nonexistent")
        assert func_desc is None

    def test_list_tools(self):
        """Test listing all registered tools."""
        self.registry.register(registry_test_function)
        self.registry.register(another_registry_test_function)

        tools = self.registry.list_tools()
        assert len(tools) == 2
        assert "registry_test_function" in tools
        assert "another_registry_test_function" in tools

    def test_get_schemas(self):
        """Test getting all tool schemas."""
        self.registry.register(registry_test_function)
        self.registry.register(another_registry_test_function)

        schemas = self.registry.get_schemas()
        assert len(schemas) == 2

        # Check that schemas are properly generated
        schema_names = [s["function"]["name"] for s in schemas]
        assert "registry_test_function" in schema_names
        assert "another_registry_test_function" in schema_names

    def test_registry_independence(self):
        """Test that separate registry instances are independent."""
        other_registry = Registry()
        
        self.registry.register(registry_test_function)
        assert len(self.registry.list_tools()) == 1
        assert len(other_registry.list_tools()) == 0
        
        other_registry.register(another_registry_test_function)
        assert len(self.registry.list_tools()) == 1
        assert len(other_registry.list_tools()) == 1

    def test_function_metadata_attached(self):
        """Test that metadata is attached to registered functions."""
        self.registry.register(registry_test_function)

        # Check function metadata
        assert hasattr(registry_test_function, "__tool_schema__")
        assert (
            registry_test_function.__tool_schema__["function"]["name"] == "registry_test_function"
        )
        # Context type should be None for functions without context requirements
        func_desc = self.registry.get("registry_test_function")
        assert func_desc
        assert func_desc.context_type is None

        # Check FunctionDescription has schema
        func_desc = self.registry.get("registry_test_function")
        assert func_desc
        assert func_desc.schema is not None
        assert func_desc.schema["function"]["name"] == "registry_test_function"


class TestGlobalRegistry:
    """Test global REGISTRY instance."""

    def setup_method(self):
        """Save global registry state before each test."""
        self._saved_tools = REGISTRY._tools.copy()

    def teardown_method(self):
        """Restore global registry state after each test."""
        REGISTRY._tools = self._saved_tools

    def test_global_registry_exists(self):
        """Test that global REGISTRY exists."""
        assert REGISTRY is not None
        assert isinstance(REGISTRY, Registry)

    def test_global_registry_register(self):
        """Test registering with global registry."""
        REGISTRY.register(registry_test_function)

        assert "registry_test_function" in REGISTRY.list_tools()

    def test_global_registry_isolation(self):
        """Test that tests don't interfere with each other."""
        # This test should start with the saved registry state
        initial_count = len(self._saved_tools)
        assert len(REGISTRY.list_tools()) == initial_count

        REGISTRY.register(registry_test_function)

        assert len(REGISTRY.list_tools()) == initial_count + 1
