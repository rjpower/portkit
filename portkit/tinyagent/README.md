# TinyAgent

TinyAgent is PortKit's specialized agent system for C-to-Rust porting, now built on the TidyLLM framework. It provides domain-specific tools and workflows while leveraging TidyLLM's robust architecture for tool management, validation, and testing.

## Architecture

TinyAgent has been migrated to use TidyLLM as its foundation:

- **PortKitAgent**: Main agent class using TidyLLM's FunctionLibrary
- **PortKitContext**: Protocol defining context requirements for porting tools  
- **Domain-specific tools**: Specialized for C-to-Rust porting workflows
- **Backward compatibility**: Existing workflow preserved through adapter layer

## Tools

All tools have been migrated to TidyLLM patterns with comprehensive validation:

- `read_files` - Read multiple source files for analysis
- `search_files` - Pattern search across source code
- `edit_code` - Apply diff-fenced patches to files  
- `replace_file` - Write complete file content
- `run_fuzz_test` - Execute cargo fuzz tests
- `symbol_status` - Lookup symbol implementation status
- `append_to_file` - Append content to existing files
- `list_files` - List files by extension patterns

Each tool provides:
- Type-safe Pydantic models for arguments and results
- Automatic OpenAI-compatible schema generation
- CLI generation for testing and debugging
- Protocol-based context injection
- Comprehensive error handling

## Usage

```python
from portkit.tinyagent.portkit_agent import PortKitAgent
from portkit.tinyagent.context import PortKitContext

# Create agent with PortKit context
agent = PortKitAgent(context)

# Get OpenAI-compatible tool schemas
schemas = agent.get_schemas()

# Execute tool calls
result = agent.call_tool({
    "name": "read_files",
    "arguments": {"paths": ["src/main.c"]}
})
```

## Benefits of TidyLLM Migration

- **Improved Architecture**: Clean separation of concerns, better error handling
- **Type Safety**: Comprehensive Pydantic validation with rich error messages
- **Testing Framework**: Built-in support for unit and benchmark tests
- **Documentation**: External prompt files with include directive support
- **Maintainability**: 163 tests ensuring reliability across the stack
- **Extensibility**: Easy to add new tools following established patterns

## Testing

```bash
# Run TinyAgent tests
uv run pytest portkit/tinyagent/tests/ -v

# Test individual tools via CLI
uv run python portkit/tinyagent/tools/read_files.py --help
uv run python portkit/tinyagent/tools/read_files.py --json '{"paths": ["src/main.c"]}'
```