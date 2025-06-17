# Unified Fuzz Test Generation and Implementation Plan

## Current State Analysis

The current `implfuzz.py` has three separate LLM-driven steps:

1. **Stub Generation** (`generate_stub_impl`): Creates stub + FFI bindings
2. **Fuzz Test Generation** (`generate_fuzz_test`): Creates comparison fuzz tests  
3. **Full Implementation** (`generate_full_impl`): Replaces stub with working implementation

## Proposed Merge: Combine Steps 2 & 3

### Rationale

The fuzz test generation and implementation steps are tightly coupled:
- Both work toward the same goal: a working Rust implementation
- The fuzz test is the primary verification mechanism for the implementation
- Current approach creates implementation without seeing the fuzz test structure
- Merging allows the LLM to see both tasks together and optimize for the specific test

### New Workflow

1. **Stub Generation** (unchanged)
   - Creates Rust stub with `unimplemented!()`
   - Creates FFI bindings for C version
   - Ensures project compiles

2. **Unified Implementation + Fuzz Test Generation** (merged)
   - Creates fuzz test that exercises the symbol
   - Implements the Rust function to pass the fuzz test
   - Iteratively refines both until fuzz tests pass

### Implementation Changes

#### New Combined Prompt

```python
IMPLEMENT_WITH_FUZZ_PROMPT = f"""
{COMMON_PROMPT}

Your task is to create both a fuzz test and a working Rust implementation that passes it.

You will:
1. Create a comprehensive fuzz test that compares C and Rust implementations
2. Implement the Rust function to match the C behavior exactly
3. Ensure the fuzz test passes with your implementation

The fuzz test should:
- Use libfuzzer_sys to generate random inputs
- Call both C (via FFI) and Rust implementations  
- Compare outputs and assert they are identical
- Handle edge cases and provide clear assertion messages

The Rust implementation should:
- Exactly match the C implementation's behavior
- Use idiomatic Rust internally while maintaining exact behavioral compatibility
- Pass all fuzz tests that compare outputs with the C version

You may examine the C source code to understand the symbol's behavior.
When you receive compilation errors or test failures, analyze them and fix both the implementation and fuzz test accordingly.
"""
```

#### New Combined Function

```python
async def generate_impl_with_fuzz_test(
    symbol_name: str,
    symbol_kind: str, 
    c_header_path: str,
    c_source_path: str,
    rust_src_path: str,
    rust_ffi_path: str,
    rust_fuzz_path: str,
    *,
    ctx: BuilderContext,
):
    """Generate fuzz test and implementation together using LLM."""
    
    def _completion_fn(initial: bool) -> TaskStatus:
        result = TaskStatus()
        
        # Check implementation exists and is not stub
        if not is_symbol_defined(ctx.project_root, symbol_name, rust_src_path):
            result.error(f"Symbol '{symbol_name}' implementation not found or is still a stub")
            
        # Check fuzz test exists  
        if not is_fuzz_test_defined(ctx.project_root, symbol_name):
            result.error(f"Fuzz test for '{symbol_name}' not found")
            
        if result.is_done():
            compile_rust_project(ctx.project_root / "rust")
            # Run fuzz test to verify implementation
            fuzz_target = f"fuzz_{symbol_name}"
            if initial:
                run_fuzz_test(RunFuzzTestRequest(target=fuzz_target, runs=100), ctx=ctx)
            else:
                run_fuzz_test(RunFuzzTestRequest(target=fuzz_target), ctx=ctx)
                
        return result
```

#### Updated Main Pipeline

```python
async def port_symbol(symbol: Symbol, *, ctx: BuilderContext) -> None:
    """Process a single symbol with unified implementation."""
    
    # Step 1: Generate stub (unchanged)
    stub_messages = await generate_stub_impl(...)
    
    # Step 2: Generate implementation + fuzz test together
    if symbol.kind != "struct":
        impl_fuzz_messages = await generate_impl_with_fuzz_test(
            symbol.name,
            symbol.kind,
            c_header_path=str(c_header),
            c_source_path=str(c_source), 
            rust_src_path=str(rust_src_path),
            rust_ffi_path=str(rust_ffi_path),
            rust_fuzz_path=str(rust_fuzz_path),
            ctx=ctx,
        )
        write_logs(symbol.name, "impl_fuzz", impl_fuzz_messages)
```

### Benefits

1. **Tighter Integration**: LLM sees both fuzz test and implementation requirements together
2. **Fewer LLM Calls**: Reduces from 3 steps to 2 steps per symbol  
3. **Better Quality**: Implementation is designed specifically for the fuzz test structure
4. **Faster Iteration**: Can fix both test and implementation in same LLM conversation
5. **Cost Reduction**: ~33% fewer LLM interactions

### Potential Risks

1. **Increased Complexity**: Single LLM call handles more responsibility
2. **Longer Conversations**: May require more back-and-forth to get both working
3. **Debugging Difficulty**: Harder to isolate whether issue is in test or implementation

### Migration Strategy

1. Implement new combined function alongside existing functions
2. Add feature flag to choose between old 3-step and new 2-step approach
3. Test on subset of symbols to validate approach
4. Gradually migrate and remove old functions once proven

### Success Metrics

- Reduced average LLM calls per symbol
- Maintained or improved fuzz test pass rate  
- Reduced total processing time per symbol
- Lower overall API costs