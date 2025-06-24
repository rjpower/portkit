# Benchmark Framework Specification

## Overview

The TidyAgent Benchmark Framework provides a simple, pytest-like system for testing tool effectiveness with LLM models. Tests are written as regular Python functions with decorators, and the framework handles LLM invocation, tool execution, and result validation.

## Core Concepts

### Simple Test Functions
Tests are written as standard Python functions using pytest-like decorators:

```python
@benchmark_test("gpt-4", "claude-3-sonnet")
def test_patch_file_basic(llm, tools, mock_context):
    """Test basic patch file functionality."""
    # Setup
    original_content = "def hello():\n    print('world')"
    
    # Invoke LLM to call patch_file
    result = llm.ask(
        "Change 'world' to 'hello world' in the function",
        tools=tools,
        context={"file_content": original_content}
    )
    
    # Validate the LLM called the right tool with right args
    assert result.tool_called == "patch_file"
    assert "world" in result.tool_args["old_content"]
    assert "hello world" in result.tool_args["new_content"]
    
    # Validate the tool result
    assert result.tool_result["success"] is True
    assert "hello world" in result.final_content

@benchmark_test("gpt-4")  
def test_patch_file_error_handling(llm, tools, mock_context):
    """Test patch file error handling for missing content."""
    original_content = "def hello():\n    print('world')"
    
    result = llm.ask(
        "Change 'universe' to 'cosmos' in the function",  # 'universe' doesn't exist
        tools=tools,
        context={"file_content": original_content}
    )
    
    # Should still call patch_file but with error result
    assert result.tool_called == "patch_file"
    assert result.tool_result.get("success") is False
    assert "not found" in result.tool_result.get("error", "").lower()
```

## Framework Components

### 1. Test Decorators

```python
from typing import Callable
import functools

def benchmark_test(*models: str, timeout: int = 30, tags: list[str] = None):
    """Mark a function as a benchmark test for specified LLM models.
    
    Args:
        *models: LLM model names to test against
        timeout: Maximum test execution time in seconds
        tags: Optional tags for test categorization
    """
    def decorator(func: Callable):
        func._is_benchmark_test = True
        func._test_models = list(models)
        func._test_timeout = timeout
        func._test_tags = tags or []
        return func
    return decorator

def skip_if_no_api_key(provider: str):
    """Skip test if API key for provider is not available."""
    def decorator(func: Callable):
        func._skip_condition = f"no_{provider}_api_key"
        return func
    return decorator
```

### 2. LLM Test Helper

```python
import json
from dataclasses import dataclass
from typing import Any

@dataclass
class TestResult:
    """Result of a single LLM tool calling test."""
    success: bool
    tool_called: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: Any = None
    error_message: str | None = None
    response_time_ms: int = 0
    
    # For tools that modify content
    final_content: str | None = None

class LLMTestHelper:
    """Helper for invoking LLMs in tests with consistent interface."""
    
    def __init__(self, model: str, function_library, llm_client):
        self.model = model
        self.function_library = function_library
        self.llm_client = llm_client
    
    def ask(
        self, 
        prompt: str, 
        tools: list[dict], 
        context: dict[str, Any] = None
    ) -> TestResult:
        """Ask LLM to perform a task using available tools.
        
        Args:
            prompt: User prompt describing the task
            tools: Available tool schemas
            context: Test context (e.g., file contents, mock data)
            
        Returns:
            TestResult with tool call and execution details
        """
        import time
        
        start_time = time.time()
        
        try:
            # Get LLM response
            response = self.llm_client.completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant with access to tools."},
                    {"role": "user", "content": prompt}
                ],
                tools=tools
            )
            
            response_time = int((time.time() - start_time) * 1000)
            
            # Check if tool was called
            tool_calls = response.choices[0].message.tool_calls
            if not tool_calls:
                return TestResult(
                    success=False,
                    error_message="No tool was called",
                    response_time_ms=response_time
                )
            
            # Execute the tool call
            tool_call = tool_calls[0]
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            
            # Execute tool with test context
            if context:
                # Merge test context with function library context
                test_library = self._create_test_library(context)
                tool_result = test_library.call({
                    "name": tool_name,
                    "arguments": tool_args
                })
            else:
                tool_result = self.function_library.call({
                    "name": tool_name,
                    "arguments": tool_args
                })
            
            # Extract final content for content-modifying tools
            final_content = None
            if context and "file_content" in context:
                # For patch-like tools, simulate the content change
                final_content = self._simulate_content_change(
                    context["file_content"], tool_args, tool_result
                )
            
            return TestResult(
                success=True,
                tool_called=tool_name,
                tool_args=tool_args,
                tool_result=tool_result,
                response_time_ms=response_time,
                final_content=final_content
            )
            
        except Exception as e:
            return TestResult(
                success=False,
                error_message=str(e),
                response_time_ms=int((time.time() - start_time) * 1000)
            )
    
    def _create_test_library(self, context: dict[str, Any]):
        """Create a test-specific function library with mocked context."""
        from portkit.tidyagent import FunctionLibrary
        
        # Create mock context that includes test data
        mock_context = {
            **self.function_library.context,
            **context
        }
        
        return FunctionLibrary(
            functions=self.function_library._tools.values(),
            context=mock_context,
            registry=self.function_library.registry
        )
    
    def _simulate_content_change(self, original_content: str, tool_args: dict, tool_result: Any) -> str:
        """Simulate content changes for testing patch-like tools."""
        if tool_result.get("success") and "old_content" in tool_args and "new_content" in tool_args:
            return original_content.replace(tool_args["old_content"], tool_args["new_content"])
        return original_content
```

### 3. Test Discovery and Runner

```python
import inspect
import importlib
from pathlib import Path
from typing import Generator

class BenchmarkRunner:
    """Discovers and runs benchmark tests."""
    
    def __init__(self, function_library, llm_client=None):
        self.function_library = function_library
        self.llm_client = llm_client or self._create_default_client()
        self.results = {}
    
    def discover_tests(self, test_dir: Path) -> Generator[tuple[str, Callable], None, None]:
        """Discover all benchmark test functions in directory."""
        for test_file in test_dir.glob("test_*.py"):
            module_name = test_file.stem
            spec = importlib.util.spec_from_file_location(module_name, test_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            for name, obj in inspect.getmembers(module):
                if (inspect.isfunction(obj) and 
                    hasattr(obj, '_is_benchmark_test') and 
                    name.startswith('test_')):
                    yield f"{module_name}::{name}", obj
    
    def run_test(self, test_name: str, test_func: Callable, models: list[str] = None) -> dict:
        """Run a single test function against specified models."""
        test_models = models or test_func._test_models
        test_results = {}
        
        for model in test_models:
            print(f"Running {test_name} with {model}...")
            
            # Create LLM helper for this model
            llm_helper = LLMTestHelper(model, self.function_library, self.llm_client)
            
            # Get tool schemas
            tools = self.function_library.get_schemas()
            
            # Create mock context fixture
            mock_context = self._create_mock_context()
            
            try:
                # Run the test function
                test_func(llm_helper, tools, mock_context)
                test_results[model] = {"success": True, "error": None}
                
            except AssertionError as e:
                test_results[model] = {"success": False, "error": f"Assertion failed: {str(e)}"}
                
            except Exception as e:
                test_results[model] = {"success": False, "error": f"Test error: {str(e)}"}
        
        return test_results
    
    def run_all_tests(self, test_dir: Path, models: list[str] = None) -> dict:
        """Run all discovered tests and return aggregated results."""
        all_results = {}
        
        for test_name, test_func in self.discover_tests(test_dir):
            all_results[test_name] = self.run_test(test_name, test_func, models)
        
        return all_results
    
    def _create_default_client(self):
        """Create default LiteLLM client."""
        try:
            from .clients import LiteLLMClient
            return LiteLLMClient()
        except ImportError:
            # Return mock client if LiteLLM not available
            from .clients import MockLLMClient
            return MockLLMClient({})
    
    def _create_mock_context(self) -> dict:
        """Create mock context for tests."""
        return {
            "project_root": Path("/tmp/test"),
            "dry_run": False,
            "max_file_size": 1_000_000
        }
```

### 4. Simple Client Interface

```python
from abc import ABC, abstractmethod

class LLMClient(ABC):
    @abstractmethod
    def completion(self, model: str, messages: list[dict], tools: list[dict], **kwargs) -> dict:
        pass

class LiteLLMClient(LLMClient):
    def completion(self, model: str, messages: list[dict], tools: list[dict], **kwargs) -> dict:
        import litellm
        return litellm.completion(model=model, messages=messages, tools=tools, **kwargs)

class MockLLMClient(LLMClient):
    def __init__(self, mock_responses: dict[str, dict]):
        self.mock_responses = mock_responses
    
    def completion(self, model: str, messages: list[dict], tools: list[dict], **kwargs) -> dict:
        # Return pre-configured response or default tool call
        prompt = messages[-1]["content"]
        return self.mock_responses.get(prompt, {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": "patch_file",
                            "arguments": '{"file_path": "test.py", "old_content": "world", "new_content": "hello world"}'
                        }
                    }]
                }
            }]
        })
```

## Usage Examples

### Writing Test Files

Create `tests/test_patch_file_benchmark.py`:

```python
from portkit.tidyagent.benchmark import benchmark_test

@benchmark_test("gpt-4", "claude-3-sonnet")
def test_simple_replacement(llm, tools, mock_context):
    """Test simple string replacement."""
    original = "def greet():\n    return 'Hello'"
    
    result = llm.ask(
        "Change 'Hello' to 'Hi' in the greet function",
        tools=tools,
        context={"file_content": original}
    )
    
    assert result.tool_called == "patch_file"
    assert "Hello" in result.tool_args["old_content"] 
    assert "Hi" in result.tool_args["new_content"]
    assert result.tool_result["success"] is True

@benchmark_test("gpt-4", tags=["error_handling"])
def test_missing_content(llm, tools, mock_context):
    """Test error when content not found."""
    original = "print('hello')"
    
    result = llm.ask(
        "Change 'goodbye' to 'farewell'",  # 'goodbye' doesn't exist
        tools=tools,
        context={"file_content": original}
    )
    
    assert result.tool_called == "patch_file"
    assert result.tool_result.get("success") is False
    assert "not found" in result.tool_result.get("error", "").lower()

@benchmark_test("gpt-3.5-turbo", timeout=60)
def test_complex_multiline(llm, tools, mock_context):
    """Test complex multi-line function modification."""
    original = """def calculate(a, b):
    return a + b"""
    
    result = llm.ask(
        "Add error handling to check if inputs are numbers",
        tools=tools,
        context={"file_content": original}
    )
    
    assert result.tool_called == "patch_file"
    assert result.tool_result["success"] is True
    # Verify error handling was added
    assert "isinstance" in result.final_content or "type" in result.final_content
```

### Running Benchmarks

```python
from pathlib import Path
from portkit.tidyagent.benchmark import BenchmarkRunner
from portkit.tidyagent import FunctionLibrary
from examples.patch_file import patch_file

# Setup
function_library = FunctionLibrary(
    functions=[patch_file],
    context={"project_root": Path("/tmp"), "dry_run": False}
)

# Run benchmarks
runner = BenchmarkRunner(function_library)
results = runner.run_all_tests(
    test_dir=Path("tests"),
    models=["gpt-4", "claude-3-sonnet"]
)

# Print results
for test_name, model_results in results.items():
    print(f"\n{test_name}:")
    for model, result in model_results.items():
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        print(f"  {model}: {status}")
        if not result["success"]:
            print(f"    Error: {result['error']}")
```

## File Structure

```
portkit/tidyagent/
├── benchmark.py              # Main benchmark framework
├── benchmark/
│   ├── __init__.py
│   ├── decorators.py         # @benchmark_test decorator
│   ├── runner.py             # BenchmarkRunner 
│   ├── helpers.py            # LLMTestHelper
│   └── clients.py            # LLM client implementations
├── tests/
│   └── test_benchmark.py     # Framework self-tests
└── examples/
    └── patch_file/
        └── tests/
            └── test_patch_file_benchmark.py  # Example benchmark tests
```

This simpler approach focuses on ease of use and follows familiar pytest patterns while still providing comprehensive LLM tool testing capabilities.