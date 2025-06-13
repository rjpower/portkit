# Auto Fuzzing Specification

## Overview

This system implements an automated C-to-Rust porting strategy using topological ordering of code dependencies. The goal is to systematically port C code to Rust while ensuring behavioral equivalence through automated fuzz testing.

## Architecture

### Core Components

1. **C Traversal Tool** (`portkit/c_traversal.py`)
   - Uses libclang to parse C source files
   - Extracts entities: structs, typedefs, functions, enums
   - Performs dependency analysis and topological sorting
   - Handles circular dependencies with cycle detection
   - Outputs ordered list of entities for systematic porting

2. **Implementation Fuzzer** (`portkit/implfuzz.py`)
   - LLM-driven Rust code generation with fuzz testing
   - Streaming completion with tool integration
   - Automatic retry mechanism for failed implementations
   - Compilation and fuzz test validation

### Entity Dependencies

The system analyzes C code to build a dependency graph:

- **Structs**: Dependencies on field types
- **Typedefs**: Dependencies on underlying types  
- **Functions**: Dependencies on return type and parameter types
- **Enums**: Typically no dependencies

Built-in types (int, char, float, etc.) are excluded from dependency analysis.

## Porting Strategy

### Phase 1: Topological Analysis
```
1. struct   ZopfliLZ77Store      (lz77.h:44) deps: none
2. function ZopfliVerifyLenDist  (lz77.h:128) deps: none
3. function ZopfliGetDistExtraBits (symbols.h:38) deps: none
...
```

May need adjustment to make this callable from `implfuzz.py`

### Phase 2: Systematic Porting

For each entity in topological order, perform a 3-step process:

#### Step 1: Interface Porting (Stub Generation)
- Generate Rust stub implementations with correct signatures
- Create FFI bindings in `src/ffi.rs`
- Ensure compilation succeeds

**Example**: For C function:
```c
int ZopfliLengthLimitedCodeLengths(
    const size_t* frequencies, int n, int maxbits, unsigned* bitlengths);
```

Generate Rust stub:
```rust
pub fn ZopfliLengthLimitedCodeLengths(
    frequencies: &[usize],
    n: usize, 
    maxbits: i32,
    bitlengths: &mut [u32],
) -> i32 {
    unimplemented!()
}
```

#### Step 2: Fuzz Test Generation
- Generate comparative fuzz tests using template from `fuzz_targets/`
- Tests compare Rust vs C implementation outputs
- Focus on compilation success initially
- Template includes:
  - Arbitrary input generation
  - Dual execution (C and Rust)
  - Output comparison assertions

Reference `fuzz_katajainen.rs` for an example.

#### Step 3: Implementation
- Use LLM with `IMPLEMENT_PROMPT` system message
- Iterative refinement based on fuzz test failures
- Maximum 3 attempts with compilation and test feedback
- Success criteria: fuzz tests pass for specified timeout

### Special Handling

**Structs**: 
- Skip fuzz testing phase
- Ensure identical memory layout and padding
- Focus on structural compatibility

**Circular Dependencies**:
- Detected via Tarjan's algorithm for strongly connected components
- Marked entities processed after acyclic dependencies
- Smaller cycles prioritized over larger ones

## Implementation Details

### Tool Integration

The system provides LLM tools for:

- `read_source_file`: Access C source code
- `write_rust_source_file`: Write Rust implementations with validation
- `write_fuzz_test`: Create fuzz test targets
- `run_fuzz_test`: Execute and validate fuzz tests
- `append_code`: Add code with compilation checks

### Validation Pipeline

1. **Compilation Check**: All Rust code must compile
2. **Fuzz Test Execution**: Compare C and Rust outputs
3. **Timeout-based Testing**: Configurable test duration
4. **Assertion Analysis**: Parse and report test failures

### Error Handling

- Retry mechanism for compilation failures
- Structured error reporting with assertion details
- Graceful handling of unparseable C code
- Progress tracking through complex dependency chains

## Configuration

- Model: `gemini/gemini-2.5-flash-preview-05-20`
- Default fuzz timeout: 60 seconds
- Max implementation attempts: 3
- Source path: `zopfli/src`
- Rust target: `zopfli/rust`

## TODO: Remaining Implementation Items

### High Priority

1. **Main Orchestration Loop**
   - Integrate `c_traversal.py` output with `implfuzz.py`
   - Process entities in topological order

### Medium Priority

4. **Enhanced Fuzz Test Templates**
   - Create specialized templates per entity type
   - Better input generation strategies
   - Improved assertion patterns

5. **Struct Handling**
   - Memory layout verification
   - Padding compatibility checks
   - Nested struct dependency resolution

6. **Error Recovery**
   - Better failure analysis and retry strategies
   - Partial success handling
   - Dependency skip mechanisms

### Low Priority

7. **Performance Optimization**
   - Parallel processing of independent entities
   - Caching of compilation results
   - Incremental progress tracking

8. **Documentation Generation**
   - Auto-generate porting reports
   - Dependency visualization
   - Progress dashboards

9. **Advanced Features**
   - Custom type mapping configuration
   - Selective entity filtering
   - Integration with existing test suites