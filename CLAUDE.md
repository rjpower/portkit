# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development Commands
- `uv run python -m portkit.implfuzz` - Main entry point for porting C libraries to Rust
- `uv run python -m portkit.implfuzz --editor litellm` - Use LiteLLM models (default)
- `uv run python -m portkit.implfuzz --editor claude` - Use Claude Code directly
- `uv run python -m portkit.implfuzz --editor codex` - Use OpenAI Codex

### Testing
- `uv run pytest` - Run the test suite
- `uv run pytest tests/test_implfuzz.py` - Run specific test file
- `uv run ruff check` - Run linter
- `uv run ruff format` - Format code

### Python Operations
- Use `uv run` for all Python operations (not direct python/pip commands)
- `uv sync` - Install/update dependencies

## Architecture

PortKit is an AI-powered C-to-Rust porting toolkit with a multi-agent architecture:

### Core Components
- **`portkit/implfuzz.py`** - Main orchestration engine and CLI entry point
- **`portkit/sourcemap.py`** - C code analysis using Tree-sitter, symbol extraction and dependency graph
- **`portkit/checkpoint.py`** - Project state management and recovery from compilation failures
- **`portkit/tinyagent/agent.py`** - Built-in LLM agent with tool-calling capabilities for porting tasks
- **`portkit/claude.py`** - Claude Code integration module
- **`portkit/codex.py`** - OpenAI Codex integration module

### AI Model Integration
- **Multi-model support**: Claude, OpenAI Codex, or any LiteLLM-compatible model
- **Unified prompting system**: `portkit/prompts/unified_implementation.md` contains the main porting instructions
- **Tool-calling agents**: The tinyagent system provides structured tools for file operations, compilation, and testing

### Project Workflow
1. **Analysis**: Parse C source using Tree-sitter to extract symbols (functions, structs, enums)
2. **Topological ordering**: Process symbols in dependency order to avoid circular references
3. **AI-powered porting**: Generate FFI bindings, Rust implementations, and fuzz tests
4. **Validation**: Compile and run differential fuzz tests between C and Rust implementations
5. **Checkpointing**: Save/restore state on failures for iterative development

### Expected Project Structure
Projects should follow this structure:
```
project/
  src/           # C source code
  rust/          # Rust project root
    src/         # Rust implementations  
    fuzz/        # Differential fuzz tests
      fuzz_targets/  # Individual fuzz test files
```

### Symbol Processing
- Extracts functions, structs, enums, typedefs, constants from C code
- Creates dependency graphs to determine porting order
- Generates corresponding Rust FFI bindings, implementations, and fuzz tests
- Uses differential testing to validate behavioral equivalence

## Development Principles
- Use `uv run` for all Python operations
- Keep code flat, don't swallow exceptions, let exceptions flow
- No hacks or backwards compatibility concerns  
- Direct, efficient error handling without try/except logging patterns