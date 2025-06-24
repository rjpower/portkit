# PortKit

A comprehensive AI-powered toolkit featuring:
1. **C-to-Rust Porting**: Automated porting of C libraries to Rust with testing and validation
2. **TidyLLM**: Clean tool management system for LLM applications with auto-discovery and adapters

## Overview

### C-to-Rust Porting
PortKit systematically ports C codebases to Rust by:
- Analyzing C source code and extracting symbols (functions, structs, enums, etc.)
- Generating FFI bindings, Rust implementations, and fuzz tests
- Using AI models (Claude, Codex, or LiteLLM) to perform the actual porting
- Validating ports through compilation and differential fuzzing

### TidyLLM Tool System
A clean, registry-based tool management system for LLM applications:
- **Decorator-based registration**: Simple `@register` decorator for tool functions
- **Auto-discovery**: Automatically discover tools in directories or packages
- **CLI generation**: Generate Click CLIs from registered functions
- **FastAPI adapter**: Expose tools via REST API endpoints
- **Type safety**: Full Pydantic validation and OpenAI-compatible schemas

## Features

### C-to-Rust Porting Features
- **Automated Symbol Analysis**: Parses C source code using Tree-sitter to extract functions, structs, and dependencies
- **Topological Ordering**: Processes symbols in dependency order to avoid circular references
- **Multi-Model Support**: Works with Claude, OpenAI Codex, or any LiteLLM-compatible model
- **Differential Testing**: Generates fuzz tests that compare C and Rust implementations
- **Checkpointing**: Saves/restores project state on compilation failures
- **Interactive Workflow**: Handles interrupts gracefully and provides progress tracking

### TidyLLM Features
- **Registry System**: Central registry for all tool functions with deduplication
- **Auto-Discovery**: Discover tools in directories with configurable patterns and exclusions
- **OpenAI Compatibility**: Generate OpenAI-compatible tool schemas automatically
- **CLI Generation**: Create Click CLIs from function signatures with proper argument handling
- **FastAPI Integration**: REST API endpoints for tool execution and schema retrieval
- **Context Injection**: Pass context objects to tools for stateful operations
- **Error Handling**: Structured error responses with detailed information

## Installation

```bash
uv sync
```

## Usage

### C-to-Rust Porting

The primary command for porting C code to Rust:

```bash
uv run python -m portkit.implfuzz [--editor MODEL_TYPE]
```

Where `MODEL_TYPE` can be:
- `litellm` (default) - Uses LiteLLM for model access
- `claude` - Uses Claude Code directly
- `codex` - Uses OpenAI Codex

### TidyLLM Tool System

#### Basic Tool Registration

```python
from portkit.tidyllm import register

@register
def hello_world(name: str) -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"
```

#### Auto-Discovery

```python
from pathlib import Path
from portkit.tidyllm import discover_tools_in_directory

# Discover all tools in a directory
tools = discover_tools_in_directory(
    Path("my_tools"),
    exclude_patterns=["test_*", "__pycache__"]
)
```

#### CLI Generation

```python
from portkit.tidyllm import cli_main

# Generate CLI from registered tools
if __name__ == "__main__":
    cli_main()
```

#### FastAPI Integration

```python
from portkit.tidyllm.adapters import create_fastapi_app
from portkit.tidyllm import FunctionLibrary

# Create library with context
library = FunctionLibrary(context={"project_root": Path("/tmp")})

# Create FastAPI app
app = create_fastapi_app(library)

# Run with: uvicorn module:app --reload
```

## Project Structure

### C-to-Rust Porting Components
- `portkit/implfuzz.py` - Main entry point and orchestration logic
- `portkit/sourcemap.py` - C code analysis and symbol extraction
- `portkit/checkpoint.py` - Project state management
- `portkit/claude.py` - Claude Code integration
- `portkit/codex.py` - OpenAI Codex integration
- `portkit/interrupt.py` - Interrupt handling
- `portkit/prompts/` - AI model prompts and instructions

### TidyLLM Components
- `portkit/tidyllm/registry.py` - Central tool registry
- `portkit/tidyllm/library.py` - Function execution library with context injection
- `portkit/tidyllm/cli.py` - CLI generation from registered functions
- `portkit/tidyllm/discover.py` - Auto-discovery system for tools
- `portkit/tidyllm/schema.py` - OpenAI-compatible schema generation
- `portkit/tidyllm/models.py` - Pydantic models for tool responses
- `portkit/tidyllm/adapters/` - Framework adapters (FastAPI, etc.)

### TinyAgent System
- `portkit/tinyagent/portkit_agent.py` - Agent with PortKit-specific tools
- `portkit/tinyagent/tools/` - Reusable tools for file operations, compilation, etc.

## How It Works

### C-to-Rust Porting Workflow

1. **Analysis Phase**: Parses C source files to extract symbols and their dependencies
2. **Planning Phase**: Creates a topological ordering of symbols to process
3. **Porting Phase**: For each symbol:
   - Generates a comprehensive prompt with C source code and context
   - Calls the AI model to generate FFI bindings, Rust implementation, and fuzz tests
   - Validates the implementation through compilation and testing
   - Creates checkpoints to recover from failures
4. **Validation Phase**: Runs differential fuzz tests to ensure behavioral equivalence

### TidyLLM Tool Registration Flow

1. **Registration**: Functions decorated with `@register` are added to the global registry
2. **Schema Generation**: Pydantic schemas are automatically generated from function signatures
3. **Discovery**: Auto-discovery can import modules to trigger registration
4. **Execution**: Tools are called through the FunctionLibrary with context injection
5. **Integration**: CLI and API endpoints are generated from the registry
