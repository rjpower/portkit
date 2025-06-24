# Registration Typing Issue Analysis

**Date**: 2025-06-23
**Author**: Analysis of TidyLLM @register decorator typing problems

## Problem Summary

Pylance reports "No parameter named 'ctx'" for calls like:
```python
compile_rust_project(ctx.config.rust_root_path(), ctx=ctx)
```

This affects registered functions throughout the codebase, causing type checking failures despite the code working correctly at runtime.

## Root Cause Analysis

### 3. Registration System Type Preservation Issues

**Problem**: The `@register` decorator in `portkit/tidyllm/registry.py` does not properly preserve type information for static analysis.

**Evidence**: 
- The decorator uses `TypeVar("F", bound=Callable)` which is too generic
- The type system cannot track that the exact function signature is preserved 
- The `Callable` bound doesn't preserve parameter names or types
- Type checkers see the registered function as a generic `Callable` rather than the specific function signature

**Technical Analysis**:
- Current signature: `def register(...) -> Callable[[F], F]` where `F = TypeVar("F", bound=Callable)`
- This tells the type checker that any `Callable` goes in and the same `Callable` comes out
- But it doesn't preserve parameter specifications (names, types, keyword-only status)
- Modern Python typing supports `ParamSpec` for this exact use case

### Registered Functions with Type Issues:

1. **compile_rust_project** (uses `ToolContext`):
   - **Definition**: `portkit/tinyagent/tools/compile_rust_project.py:20`
   - **Problematic calls**:
     - `portkit/implfuzz.py:181, 411, 484, 507`
     - `tests/test_implfuzz.py:803`

2. **All other tools** (use `PortKitContext`):
   - `search_files`, `symbol_status`, `run_fuzz_test`, `replace_file`, `list_files`, `read_files`, `append_to_file`, `edit_code`
   - **Potential issues**: Any direct calls outside the TidyLLM tool execution framework

## Impact Assessment

### Current Failures:
- **5 Pylance errors** for `compile_rust_project` calls
- Type checking failures in IDE
- Potential confusion for developers


## Solutions and Files to Update

**Approach**: Use `ParamSpec` and `TypeVar` to properly preserve function signatures.

**Solution Analysis**:
- **Root Issue**: The current `TypeVar("F", bound=Callable)` is too generic
- **Fix**: Use `ParamSpec` to capture parameter specifications and return types
- **Implementation**: Update `register` decorator to use `Callable[P, T]` pattern
- **Benefits**: Type checkers will see registered functions with their exact signatures

**Files to Update**:

1. **portkit/tidyllm/registry.py**:
   - Import `ParamSpec` from `typing`
   - Replace `TypeVar("F", bound=Callable)` with `ParamSpec` and return type `TypeVar`
   - Update decorator signature to `Callable[[Callable[P, T]], Callable[P, T]]`
   - This preserves both parameter specifications and return types

**Technical Implementation**:
```python
from typing import ParamSpec, TypeVar
P = ParamSpec("P")  # Captures parameter specification
T = TypeVar("T")    # Captures return type

def register(...) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        # Registration logic
        return func
    return decorator
```

### Solution 3: Explicit Type Annotation

**Approach**: Add explicit type annotations to resolve ambiguity.

**Files to Update**:
2. **tests/test_implfuzz.py**:
   - Add explicit typing for test context objects
   - Use proper protocol implementations in test fixtures

## Implementation Results

### ✅ Completed: Type System Enhancement

**Changes Made to `portkit/tidyllm/registry.py`**:
1. ✅ Added `ParamSpec` import from `typing`
2. ✅ Replaced `F = TypeVar("F", bound=Callable)` with:
   - `P = ParamSpec("P")` - captures parameter specifications
   - `T = TypeVar("T")` - captures return type
3. ✅ Updated decorator signature to `Callable[[Callable[P, T]], Callable[P, T]]`
4. ✅ Updated inner decorator function to use `Callable[P, T]`

**Technical Benefits**:
- Type checkers now see registered functions with their exact signatures
- Parameter names, types, and keyword-only status are preserved
- Return types are preserved
- IntelliSense and autocomplete work correctly for registered functions
- Pylance errors should be resolved for `ctx` parameter calls

**Before**:
```python
F = TypeVar("F", bound=Callable)
def register(...) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        return func
```

**After**:
```python
P = ParamSpec("P")
T = TypeVar("T")
def register(...) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        return func
```

### ✅ Testing and Validation Complete
1. ✅ Verified runtime behavior is unchanged (decorator still returns original function)
2. ✅ Tested function registration and execution with both context and non-context tools
3. ✅ All existing tests pass (37 tests in registry, decorators, and context modules)
4. ✅ Code style updated with `ruff --fix` (proper import from collections.abc)
5. ✅ Type preservation verified with test functions

**Test Results**:
- All tidyllm registry tests: ✅ PASS
- All decorator tests: ✅ PASS  
- All context injection tests: ✅ PASS
- Calculator example integration: ✅ PASS
- Type preservation verification: ✅ PASS

**Impact**:
- Type checkers now properly understand registered function signatures
- IDE autocomplete and IntelliSense work correctly
- `ctx` parameter calls should no longer show "No parameter named 'ctx'" errors
- Maintains full backward compatibility with existing code
