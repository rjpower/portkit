# TidyLLM - Clean LLM Tool Framework

TidyLLM is a comprehensive framework for building type-safe, self-documenting tools for Large Language Models. It provides automatic schema generation, validation, CLI creation, and comprehensive testing capabilities.

## Overview

TidyLLM eliminates the boilerplate and complexity of building LLM tools by providing:

- **Automatic Schema Generation**: Convert Python functions to OpenAI-compatible tool schemas
- **Type-Safe Validation**: Pydantic-based argument validation with rich error messages  
- **Context Injection**: Protocol-based dependency injection for shared resources
- **CLI Generation**: Automatic command-line interfaces for testing and integration
- **Comprehensive Testing**: Built-in benchmark framework for LLM tool validation
- **Documentation Integration**: Automatic docstring parsing and schema enhancement

## Quick Start

### 1. Define a Tool

```python
from pydantic import BaseModel
from portkit.tidyllm import register, ToolError

class CalculatorArgs(BaseModel):
    """Arguments for calculator operations."""
    expression: str
    precision: int = 2

@register()
def calculator(args: CalculatorArgs) -> dict:
    """
    Evaluate mathematical expressions safely.
    
    Args:
        expression: Mathematical expression to evaluate (e.g., "2 + 3 * 4")
        precision: Number of decimal places for results
        
    Returns:
        Dictionary with 'result' and 'expression' keys
    """
    try:
        result = eval(args.expression)  # Note: Use ast.literal_eval in production
        return {
            "result": round(result, args.precision),
            "expression": args.expression
        }
    except Exception as e:
        return ToolError(error=f"Invalid expression: {str(e)}")
```

### 2. Create a Function Library

```python
from portkit.tidyllm import FunctionLibrary

# Create library with registered tools
library = FunctionLibrary(
    functions=[calculator],  # Legacy approach - looks up from registry
    context={}  # Shared context for tools
)

# Or use the optimized approach with pre-created descriptions
from portkit.tidyllm.registry import REGISTRY
func_descriptions = [REGISTRY.get("calculator")]
library = FunctionLibrary(
    function_descriptions=func_descriptions,  # Direct FunctionDescription objects
    context={}
)

# Get OpenAI-compatible schemas
schemas = library.get_schemas()
```

### 3. Execute Tool Calls

```python
# Execute a tool call
result = library.call({
    "name": "calculator",
    "arguments": {
        "expression": "2 + 3 * 4",
        "precision": 2
    }
})

print(result)  # {'result': 14.0, 'expression': '2 + 3 * 4'}
```

### 4. Use with LLMs

```python
import litellm

# Use with LiteLLM (or any OpenAI-compatible client)
response = litellm.completion(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "Calculate 15 * 7 + 3"}
    ],
    tools=library.get_schemas(),
    tool_choice="auto"
)

# Handle tool calls
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        result = library.call({
            "name": tool_call.function.name,
            "arguments": json.loads(tool_call.function.arguments)
        })
        print(f"Tool result: {result}")
```

## Architecture

### Core Components

#### 1. **Models** (`models.py`)
- `ToolError`: Standardized error responses with optional details
- `ToolResult`: Union type for success/error results

#### 2. **Registry** (`registry.py`)
- Global tool registration system storing `FunctionDescription` objects
- One-time schema generation at registration for optimal performance
- Automatic context requirement inference from function signatures
- Duplicate prevention and validation

#### 3. **Schema Generation** (`schema.py`)
- `FunctionDescription`: Core wrapper for function validation/execution
- Automatic Pydantic model creation from function signatures
- OpenAI-compatible JSON schema generation
- Support for multiple function signature patterns

#### 4. **Function Library** (`library.py`)
- Runtime tool execution with shared context and optimized function lookups
- Support for both legacy function lists and new `FunctionDescription` objects
- Internal function dictionary for faster execution without registry lookups
- Protocol-based context validation
- Comprehensive error handling
- JSON request processing

#### 5. **Documentation System** (`docstring.py`, `prompt.py`)
- Griffe-based docstring parsing for enhanced schemas
- Support for `{{include: ./file.md}}` directives
- Automatic parameter documentation extraction

#### 6. **CLI Generation** (`cli.py`)
- Automatic Click-based CLI creation
- Support for individual arguments and JSON input
- Mock context injection for testing

#### 7. **Benchmark Framework** (`benchmark.py`)
- `@benchmark_test` decorator for LLM performance testing
- Automatic test discovery and execution
- Success rate tracking and statistics

#### 8. **LLM Integration** (`llm.py`)
- Multiple client support (LiteLLM, Mock)
- Streaming response handling
- High-level helper functions for tool usage

## Function Signature Patterns

TidyLLM supports three distinct function signature patterns:

### 1. Single Pydantic Model Pattern
```python
@register()
def my_tool(args: MyArgs, *, ctx: Context) -> Result:
    """Tool with single Pydantic model for arguments."""
    pass
```

### 2. Multiple Parameters Pattern
```python
@register()
def my_tool(name: str, count: int, enabled: bool = True, *, ctx: Context) -> Result:
    """Tool with multiple primitive or complex parameters."""
    pass
```

### 3. Single Primitive Parameter Pattern
```python
@register()
def my_tool(message: str, *, ctx: Context) -> Result:
    """Tool with single primitive parameter."""
    pass
```

## Context System

TidyLLM uses Protocol-based context injection for dependency management:

### Defining Context Requirements
```python
from typing import Protocol
from pathlib import Path

class FileContext(Protocol):
    """Context requirements for file operations."""
    project_root: Path
    max_file_size: int
    dry_run: bool
```

### Using Context in Tools
```python
@register()
def read_file(path: str, *, ctx: FileContext) -> dict:
    """Read a file with context validation."""
    full_path = ctx.project_root / path
    
    if ctx.dry_run:
        return {"status": "dry_run", "path": str(full_path)}
    
    if full_path.stat().st_size > ctx.max_file_size:
        return ToolError(error="File too large")
    
    return {"content": full_path.read_text(), "path": str(full_path)}
```

### Providing Context
```python
context = {
    "project_root": Path("/my/project"),
    "max_file_size": 1000000,
    "dry_run": False
}

library = FunctionLibrary(
    functions=[read_file],
    context=context
)
```

## Testing Framework

### Unit Tests
```python
def test_calculator_basic():
    """Test basic calculator functionality."""
    args = CalculatorArgs(expression="2 + 3", precision=2)
    result = calculator(args)
    assert result["result"] == 5.0
```

### Benchmark Tests
```python
from portkit.tidyllm.benchmark import benchmark_test

@benchmark_test()
def test_calculator_addition(context):
    """Test LLM can use calculator for addition."""
    response = context.llm.ask("What is 15 + 27?")
    
    # Validate tool was called correctly
    context.assert_tool_called(response, "calculator")
    context.assert_success(response)
    
    # Validate result contains expected value
    context.assert_result_contains(response, "42")
```

### Running Benchmarks
```python
from portkit.tidyllm.benchmark import run_benchmarks
from portkit.tidyllm import FunctionLibrary

# Create function library
library = FunctionLibrary(functions=[calculator])

# Run benchmarks with real LLM
results = run_benchmarks(
    function_library=library,
    model="gpt-4",
    test_modules=[calculator_benchmarks]
)

# Check results
passed = sum(1 for r in results if r.success)
print(f"Passed: {passed}/{len(results)} tests")
```

### Command Line Usage
```bash
# Run benchmarks from command line
python -m portkit.tidyllm.benchmark --model gpt-4 calculator_bench.py

# Run with different models
python -m portkit.tidyllm.benchmark --model claude-3-sonnet calculator_bench.py
```

## CLI Generation

TidyLLM automatically generates CLI interfaces for registered tools:

```bash
# Individual arguments
python -m examples.calculator --expression "2 + 3 * 4" --precision 2

# JSON input
python -m examples.calculator --json '{"expression": "2 + 3 * 4", "precision": 2}'

# Output (always JSON)
{"result": 14.0, "expression": "2 + 3 * 4"}
```

## Examples

The framework includes two comprehensive example tools with both unit tests and LLM benchmark tests:

### Calculator Tool (`examples/calculator/`)
- Mathematical operation validation (add, subtract, multiply, divide) 
- Error handling for division by zero and invalid operations
- 5 benchmark tests covering various scenarios
- External prompt documentation with comprehensive examples
- CLI integration

### Patch File Tool (`examples/patch_file/`)
- Unified diff parsing and application
- File and inline text modes  
- Rich statistics and validation
- 14 comprehensive benchmark tests
- External prompt documentation with detailed format specifications

## Advanced Features

### Prompt Management
```python
from portkit.tidyllm.prompt import read_prompt, module_dir

@register(doc=read_prompt(module_dir(__file__) / "prompt.md"))
def my_tool(args: MyArgs) -> Result:
    """Tool with external documentation."""
    pass
```

With `prompt.md`:
```markdown
# My Tool

{{include: ./shared/common_instructions.md}}

## Parameters
- `param1`: Description of parameter 1
- `param2`: Description of parameter 2

{{include: ./examples/usage_examples.md}}
```

The `module_dir(__file__)` helper provides clean module-relative paths, and `{{include: ./file.md}}` directives allow modular documentation composition.

### Error Handling
```python
@register()
def risky_operation(data: str) -> dict:
    """Operation that might fail."""
    # Tools should raise exceptions directly
    # FunctionLibrary.call() will wrap them in ToolError automatically
    if not data:
        raise ValueError("Data cannot be empty")
    
    result = process_data(data)  # May raise ProcessingError
    return {"success": True, "result": result}
```

The framework automatically catches exceptions and wraps them in `ToolError` responses, simplifying error handling in tool functions.

### LLM Integration Helpers
```python
from portkit.tidyllm.llm import LLMHelper

helper = LLMHelper(client=litellm, tools=library.get_schemas())

# Ask LLM to use tools
response = helper.ask("Calculate the area of a circle with radius 5")

# Validate and execute tool calls
if helper.has_tool_calls():
    for call in helper.get_tool_calls():
        result = library.call(call)
        helper.add_tool_result(call, result)
    
    # Get final response
    final_response = helper.continue_conversation()
```

## Current Implementation Status

### ✅ Fully Implemented
- Core models and error handling
- Function registry with automatic schema generation
- Schema generation for all function patterns
- Function library with context injection
- CLI generation with multiple input modes
- Comprehensive testing infrastructure
- Documentation integration with Griffe
- LLM integration helpers
- Benchmark framework with assertion helpers
- Two complete example tools with extensive tests

### 🔧 Recent Improvements
- **Optimized Architecture**: Registry now stores `FunctionDescription` objects for efficient schema reuse
- **Simplified Registration**: Auto-inference of context requirements, removed `require_context` parameter
- **Performance Boost**: Eliminated redundant `FunctionDescription` creation during function calls
- **Faster Lookups**: `FunctionLibrary` maintains internal function dictionary for optimal execution
- **External Prompt Support**: Tools can now load documentation from external `prompt.md` files with include directives
- **Simplified Benchmark Framework**: Removed unnecessary complexity, direct `list[BenchmarkResult]` returns
- **Model Flexibility**: Benchmark framework supports any LLM model without defaults
- **Improved Error Handling**: Tools raise exceptions directly, framework handles `ToolError` wrapping
- **Enhanced Documentation**: `module_dir()` helper for clean module-relative paths
- **163 tests passing** with excellent coverage

### 📊 Test Coverage  
- **Core Models**: 8 tests
- **Registry**: 11 tests  
- **Schema Generation**: 13 tests
- **Function Library**: 18 tests
- **CLI Generation**: 15 tests
- **Context System**: 12 tests
- **Integration**: 8 tests
- **Benchmark Framework**: 16 tests
- **Prompt Management**: 8 tests
- **Example Tools**: 30+ tests
- **Total**: 163 tests passing

## Code Quality Analysis

### Strengths
1. **Clean Architecture**: Well-separated concerns with minimal coupling
2. **Type Safety**: Extensive use of Pydantic, Protocols, and type hints
3. **Comprehensive Testing**: Excellent test coverage across all components
4. **Flexible Design**: Supports multiple function patterns and use cases
5. **Documentation Integration**: Automatic schema enhancement from docstrings
6. **Error Handling**: Robust, standardized error responses throughout
7. **Modern Python**: Proper use of advanced typing features and best practices

### Areas for Improvement
1. **Prompt Optimizer**: Advanced prompt optimization features not yet implemented
2. **Async Support**: Could benefit from async tool execution capabilities
3. **Performance**: Some areas could be optimized for high-throughput scenarios
4. **Plugin System**: Could add dynamic tool discovery and loading
5. **Security**: Could add input sanitization and rate limiting features

### Potential Enhancements
1. **Tool Composition**: Chaining multiple tools together
2. **Observability**: OpenTelemetry integration for monitoring
3. **Caching**: Result caching for expensive operations
4. **Streaming**: Support for streaming tool responses
5. **Versioning**: Tool version management and compatibility

## Dependencies

### Required
- `pydantic`: Data validation and JSON schema generation
- `click`: CLI generation framework
- `griffe`: Advanced docstring parsing

### Optional
- `litellm`: Multi-provider LLM client (for LLM integration)
- `pytest`: Testing framework (for development)

## Installation

```bash
# Install portkit with tidyagent
pip install portkit

# Or for development
git clone https://github.com/your-org/portkit
cd portkit
uv sync
```

## Usage with Different LLM Providers

### OpenAI
```python
import openai
from portkit.tidyllm import FunctionLibrary

client = openai.OpenAI()
library = FunctionLibrary(functions=[calculator])

response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Calculate 2^10"}],
    tools=library.get_schemas()
)
```

### Anthropic Claude
```python
import anthropic
from portkit.tidyllm import FunctionLibrary

client = anthropic.Anthropic()
library = FunctionLibrary(functions=[calculator])

# Convert schemas to Claude format
claude_tools = [
    {
        "name": schema["function"]["name"],
        "description": schema["function"]["description"],
        "input_schema": schema["function"]["parameters"]
    }
    for schema in library.get_schemas()
]

response = client.messages.create(
    model="claude-3-sonnet-20240229",
    messages=[{"role": "user", "content": "Calculate 2^10"}],
    tools=claude_tools
)
```

### LiteLLM (Universal)
```python
import litellm
from portkit.tidyllm import FunctionLibrary

library = FunctionLibrary(functions=[calculator])

# Works with any provider
response = litellm.completion(
    model="gpt-4",  # or "claude-3-sonnet", "gemini-pro", etc.
    messages=[{"role": "user", "content": "Calculate 2^10"}],
    tools=library.get_schemas()
)
```

## Contributing

The TidyLLM framework is part of the PortKit project. Contributions are welcome!

### Development Setup
```bash
git clone https://github.com/your-org/portkit
cd portkit
uv sync
uv run pytest portkit/tidyagent/tests/
```

### Running Tests
```bash
# Run all tests
uv run pytest portkit/tidyllm/

# Run specific test categories
uv run pytest portkit/tidyllm/tests/test_models.py
uv run pytest portkit/tidyllm/tests/test_benchmark.py

# Run example tool unit tests
uv run pytest portkit/tidyllm/examples/calculator/test.py
uv run pytest portkit/tidyllm/examples/patch_file/test.py

# Run live benchmarks (requires LLM API access)
python -m portkit.tidyllm.benchmark --model gpt-4 portkit/tidyllm/examples/benchmarks/calculator_bench.py
```

TidyLLM provides a solid foundation for building robust, type-safe LLM tools with minimal boilerplate and comprehensive testing capabilities. The clean architecture makes it easy to extend and customize for specific use cases.