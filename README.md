# PortKit

An AI-powered toolkit for porting C libraries to Rust with automated testing and validation.

## Overview

PortKit is designed to systematically port C codebases to Rust by:
- Analyzing C source code and extracting symbols (functions, structs, enums, etc.)
- Generating FFI bindings, Rust implementations, and fuzz tests
- Using AI models (Claude, Codex, or LiteLLM) to perform the actual porting
- Validating ports through compilation and differential fuzzing

The main entry point is `portkit/implfuzz.py`, which orchestrates the entire porting pipeline.

## Features

- **Automated Symbol Analysis**: Parses C source code using Tree-sitter to extract functions, structs, and dependencies
- **Topological Ordering**: Processes symbols in dependency order to avoid circular references
- **Multi-Model Support**: Works with Claude, OpenAI Codex, or any LiteLLM-compatible model
- **Differential Testing**: Generates fuzz tests that compare C and Rust implementations
- **Checkpointing**: Saves/restores project state on compilation failures
- **Interactive Workflow**: Handles interrupts gracefully and provides progress tracking

## Installation

```bash
uv sync
```

## Usage

The primary command is:

```bash
uv run python -m portkit.implfuzz [--editor MODEL_TYPE]
```

Where `MODEL_TYPE` can be:
- `litellm` (default) - Uses LiteLLM for model access
- `claude` - Uses Claude Code directly
- `codex` - Uses OpenAI Codex

## Project Structure

- `portkit/implfuzz.py` - Main entry point and orchestration logic
- `portkit/sourcemap.py` - C code analysis and symbol extraction
- `portkit/checkpoint.py` - Project state management
- `portkit/claude.py` - Claude Code integration
- `portkit/codex.py` - OpenAI Codex integration
- `portkit/interrupt.py` - Interrupt handling
- `portkit/tinyagent/` - Built-in agent for simple porting tasks
- `portkit/prompts/` - AI model prompts and instructions

## How It Works

1. **Analysis Phase**: Parses C source files to extract symbols and their dependencies
2. **Planning Phase**: Creates a topological ordering of symbols to process
3. **Porting Phase**: For each symbol:
   - Generates a comprehensive prompt with C source code and context
   - Calls the AI model to generate FFI bindings, Rust implementation, and fuzz tests
   - Validates the implementation through compilation and testing
   - Creates checkpoints to recover from failures
4. **Validation Phase**: Runs differential fuzz tests to ensure behavioral equivalence
