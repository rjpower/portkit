# TinyAgent to TidyLLM Migration Plan

## Overview

This document outlines the plan to migrate TinyAgent from its custom tool management and LLM handling to use TidyLLM's comprehensive framework. The migration will preserve TinyAgent's specialized porting workflow while leveraging TidyLLM's superior architecture for tool management, testing, and LLM abstraction.

## Current State Analysis

### TinyAgent Architecture (Before Migration)
```
tinyagent/
├── agent.py           # LLM interaction, streaming, retry logic
├── registry.py        # Simple tool registration
├── tools/            # Domain-specific porting tools
│   ├── read_files.py      # Multi-file reading
│   ├── search_files.py    # Pattern search
│   ├── patch/            # Diff-based code editing
│   ├── replace_file.py    # Complete file replacement
│   ├── run_fuzz_test.py   # Cargo fuzz execution
│   └── symbol_status.py   # Implementation tracking
└── __init__.py       # Simple API exposure
```

**Key Capabilities:**
- ✅ Streaming LLM interactions with interrupts
- ✅ Retry logic with task completion detection  
- ✅ Specialized C-to-Rust porting tools
- ✅ Direct LiteLLM integration
- ❌ Limited testing framework
- ❌ Basic tool registration
- ❌ Minimal error handling

### TidyLLM Framework (Target)
```
tidyllm/
├── registry.py       # Advanced tool registration with FunctionDescriptions
├── library.py        # Tool execution with context management
├── llm.py           # LLM client abstraction (OpenAI, LiteLLM, Mock)
├── schema.py        # Automatic Pydantic schema generation
├── benchmark.py     # LLM performance testing framework
├── models.py        # Standardized error handling
└── examples/        # Calculator and Patch File examples
```

**Key Advantages:**
- ✅ Comprehensive testing (163 tests passing)
- ✅ Multiple function signature patterns
- ✅ Protocol-based context injection
- ✅ Automatic schema generation
- ✅ Benchmark framework for LLM validation
- ✅ Clean separation of concerns
- ❌ No retry/completion logic
- ❌ No interrupt handling
- ❌ No domain-specific tools

## Migration Strategy

### Phase 1: Foundation Extension
**Goal**: Extend TidyLLM with TinyAgent's core capabilities

#### 1.1 Add Retry and Completion Logic to TidyLLM
```python
# tidyllm/agent.py (new file)
from dataclasses import dataclass
from typing import Protocol

@dataclass
class TaskStatus:
    """Task completion status with diagnostics"""
    complete: bool
    errors: list[str]
    diagnostics: list[str]
    retry_suggested: bool

class CompletionChecker(Protocol):
    """Protocol for task completion detection"""
    def is_complete(self, response: LLMResponse) -> TaskStatus: ...

class LLMAgent:
    """Enhanced LLM agent with retry logic"""
    
    async def call_with_retry(
        self,
        messages: list[dict],
        completion_checker: CompletionChecker,
        max_retries: int = 3,
        interrupt_handler: InterruptHandler = None
    ) -> TaskStatus:
        """Call LLM with retry logic until task completion"""
        # Implementation with streaming, interrupts, and task detection
```

#### 1.2 Add Interrupt Handling Support
```python
# tidyllm/interrupts.py (new file)
class InterruptHandler:
    """Handle interrupts during streaming operations"""
    
    def check_interrupt(self) -> bool: ...
    def handle_interrupt(self, partial_response: str) -> str: ...
```

#### 1.3 Extend Context System for PortKit
```python
# tinyagent/context.py (updated)
from typing import Protocol
from pathlib import Path
from portkit.sourcemap import SourceMap

class PortKitContext(Protocol):
    """PortKit-specific context requirements"""
    project_root: Path
    source_map: SourceMap
    running_cost: float
    files_read: set[str]
    max_cost: float
```

### Phase 2: Tool Migration
**Goal**: Port TinyAgent's specialized tools to TidyLLM's registration system

#### 2.1 Update Tool Structure
```python
# tinyagent/tools/read_files.py (updated)
from portkit.tidyllm import register, read_prompt, module_dir
from .models import ReadFilesArgs, ReadFilesResult
from .context import PortKitContext

@register(doc=read_prompt(module_dir(__file__) / "read_files.md"))
def read_files(args: ReadFilesArgs, *, ctx: PortKitContext) -> ReadFilesResult:
    """Read multiple files with cost tracking"""
    # Enhanced implementation with tidyllm patterns
```

#### 2.2 Migrate All Existing Tools

Migrate all of the existing tools to the new pattern. Small tools can be a single file with a @register macro, more complex tools  should use the directory approach.

Write a benchmark to the patch tool with appropriate test cases.

-  `read_files` 
-  `search_files`
-  `patch` 
-  `replace_file` 
-  `run_fuzz_test`
-  `symbol_status` 
-  `append_to_file`
-  `list_files`  

#### 2.3 Add External Documentation
```markdown
# tinyagent/tools/read_files.md
# Read Files Tool

{{include: ../common/file_operations.md}}

## Usage
Read multiple source files for analysis during C-to-Rust porting.

## Parameters
- `file_paths`: List of files to read (relative to project root)
- `max_lines_per_file`: Limit output size (default: 1000)

{{include: ../examples/read_files_examples.md}}
```

### Phase 3: Architecture Integration
**Goal**: Integrate enhanced TidyLLM with PortKit's workflow

#### 3.1 Update Agent Integration
```python
# tinyagent/agent.py (simplified)
from portkit.tidyllm import FunctionLibrary, LLMHelper
from .context import PortKitContext
from .completion import SymbolPortingChecker
from .tools import get_portkit_tools

class PortKitAgent:
    """PortKit-specific agent using TidyLLM foundation"""
    
    def __init__(self, context: PortKitContext):
        self.library = FunctionLibrary(
            function_descriptions=get_portkit_tools(),
            context=context.__dict__
        )
        self.llm = LLMHelper(
            model="claude-3-sonnet",
            function_library=self.library
        )
        self.completion_checker = SymbolPortingChecker(context)
    
    async def port_symbol(self, symbol_name: str) -> TaskStatus:
        """Port a C symbol to Rust using TidyLLM infrastructure"""
        messages = self._generate_porting_prompt(symbol_name)
        return await self.call_with_retry(
            messages=messages,
            completion_checker=self.completion_checker,
            max_retries=3
        )
```

#### 3.2 Preserve Existing Workflow
```python
# portkit/implfuzz.py (minimal changes)
from portkit.tinyagent import PortKitAgent

def process_symbol(symbol: str, context: PortKitContext) -> bool:
    """Process symbol using enhanced TidyLLM-based agent"""
    agent = PortKitAgent(context)
    
    try:
        status = await agent.port_symbol(symbol)
        return status.complete
    except KeyboardInterrupt:
        # Interrupt handling preserved
        return False
```

### Phase 4: Testing and Validation
**Goal**: Leverage TidyLLM's testing framework for better validation

#### 4.1 Add Benchmark Tests
```python
# tinyagent/tests/benchmarks/read_files_bench.py
from portkit.tidyllm.benchmark import benchmark_test

@benchmark_test()
def test_read_files_basic(context):
    """Test LLM can read files correctly"""
    response = context.llm.ask("Read the main.c file")
    context.assert_tool_called(response, "read_files")
    context.assert_success(response)
    context.assert_result_contains(response, "#include")
```

#### 4.2 Add Integration Tests
```python
# tinyagent/tests/test_symbol_porting.py
def test_complete_symbol_porting():
    """Test end-to-end symbol porting workflow"""
    # Integration test with real SourceMap and project
```

### Phase 5: Documentation and Migration
**Goal**: Complete the migration with updated documentation

#### 5.1 Update TinyAgent README
- Document new TidyLLM-based architecture
- Update tool usage examples
- Add benchmark testing guide
- Migration guide for custom tools

#### 5.2 Cleanup Legacy Code
- Remove old `registry.py` 
- Remove direct LiteLLM dependencies
- Update imports across codebase
- Remove duplicate tool management code

## Implementation Timeline

### Week 1: Foundation (Phase 1)
- [ ] Add retry logic to TidyLLM
- [ ] Add interrupt handling support
- [ ] Extend context system for PortKit
- [ ] Basic integration tests

### Week 2: Tool Migration (Phase 2)
- [ ] Port all existing tools to TidyLLM patterns
- [ ] Add external documentation files  
- [ ] Update tool tests with TidyLLM framework
- [ ] Validate tool functionality

### Week 3: Integration (Phase 3)
- [ ] Update PortKitAgent to use TidyLLM
- [ ] Preserve existing workflow compatibility
- [ ] End-to-end integration testing
- [ ] Performance validation

### Week 4: Testing & Documentation (Phases 4-5)
- [ ] Add comprehensive benchmark tests
- [ ] Update all documentation
- [ ] Code cleanup and optimization
- [ ] Final validation and deployment

## Expected Benefits

### 1. **Improved Architecture**
- ✅ Clean separation of concerns
- ✅ Better error handling and validation
- ✅ Type-safe tool definitions
- ✅ Comprehensive testing framework

### 2. **Enhanced Capabilities**
- ✅ Multiple function signature patterns
- ✅ Protocol-based context injection
- ✅ Automatic schema generation
- ✅ Benchmark testing for LLM validation

### 3. **Better Maintainability**
- ✅ 163 tests providing comprehensive coverage
- ✅ External documentation with include directives
- ✅ Modular design for easy extension
- ✅ Clean tool registration patterns

### 4. **Preserved Functionality**
- ✅ All existing tools and workflows
- ✅ Streaming and interrupt handling
- ✅ Task completion detection
- ✅ Cost tracking and monitoring

## Risk Mitigation

### 1. **Backward Compatibility**
- Maintain existing API surface where possible
- Gradual migration with side-by-side testing
- Rollback plan if integration issues arise

### 2. **Performance**
- Benchmark current performance before migration
- Monitor streaming latency and tool execution speed
- Optimize hot paths if needed

### 3. **Testing**
- Comprehensive test suite before and after migration
- A/B testing with real porting workflows
- User acceptance testing with sample projects

## Success Metrics

- [ ] All existing TinyAgent tests pass with new architecture
- [ ] Tool execution performance within 10% of current
- [ ] Streaming latency unchanged
- [ ] 95%+ test coverage maintained
- [ ] Documentation completeness verified
- [ ] Integration with PortKit workflow seamless

This migration will result in a more robust, testable, and maintainable system while preserving all of TinyAgent's specialized capabilities for C-to-Rust porting.