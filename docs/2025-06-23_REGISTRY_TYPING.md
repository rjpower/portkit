# Registry Typing Bug Report - 2025-06-23

## Type Errors Analysis

The codebase has type checking errors related to the `compile_rust_project` function call in `portkit/implfuzz.py:484`.

### Error 1: Argument Type Mismatch
```
ERROR Argument `Path` is not assignable to parameter with type `(ParamSpec(Unknown)) -> Unknown`
```

**Root Cause**: The function signature in `portkit/tinyagent/tools/compile_rust_project.py:20` expects a `Path` object as the first parameter, but the type checker is misinterpreting the function signature due to how the `@register` decorator affects type inference.

**Analysis**: The `@register` decorator in `portkit/tidyllm/registry.py` uses `ParamSpec` and `TypeVar` to preserve function signatures, but the type checker cannot properly infer the wrapped function's signature through the decorator chain.

### Error 2: Unexpected Keyword Argument
```
ERROR Unexpected keyword argument `ctx` in function
```

**Root Cause**: The type checker doesn't recognize that `compile_rust_project` accepts a `ctx` keyword argument, even though the actual function definition clearly shows `*, ctx: PortKitContext` as a keyword-only parameter.

**Analysis**: This is also related to the decorator's type preservation. The `@register` decorator should preserve the original function's signature including keyword-only parameters, but the type checker is losing this information.

## Technical Details

### Function Definitions
- **Actual function**: `compile_rust_project(project_dir: Path, *, ctx: PortKitContext) -> None`
- **Call site**: `compile_rust_project(ctx.config.rust_root_path(), ctx=ctx)`
- **Registry decorator**: Uses `Callable[P, T]` type preservation

### Registry Implementation
The `@register` decorator at lines 95-129 in `registry.py` uses:
- `ParamSpec("P")` and `TypeVar("T")` for type preservation
- Returns `Callable[[Callable[P, T]], Callable[P, T]]`
- Validates keyword-only `ctx` parameters at lines 117-121

## Potential Solutions

1. **Improve decorator typing**: Enhanced type hints in the `@register` decorator to better preserve function signatures
2. **Explicit type casting**: Add type annotations at call sites to help the type checker
3. **Protocol-based approach**: Use Protocol classes instead of generic callables for better type inference
4. **Overload definitions**: Provide explicit function overloads for common patterns

## Proposed Solution: Generic CallableWithSchema Protocol

The core issue is that `CallableWithSchema` is not generic and doesn't preserve the original function's parameter types. Here's a proposed fix:

```python
from typing import Any, ParamSpec, Protocol, TypeVar, cast

P = ParamSpec("P")
T = TypeVar("T")

class CallableWithSchema(Protocol[P, T]):
    """Generic callable with schema that preserves function signature."""
    
    __tool_schema__: dict
    
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T: ...

class Registry:
    def __init__(self):
        self._tools: dict[str, FunctionDescription] = OrderedDict()
    
    def get_function(self, name: str) -> CallableWithSchema[..., Any]:
        """Get the raw function by name with preserved typing."""
        func_desc = self._tools.get(name)
        if func_desc is None:
            raise KeyError(f"Tool '{name}' not found")
        return cast(CallableWithSchema[..., Any], func_desc.function)

def register(
    doc: str | None = None, name: str | None = None
) -> Callable[[Callable[P, T]], CallableWithSchema[P, T]]:
    """Register a function as a tool with preserved typing."""
    
    def decorator(func: Callable[P, T]) -> CallableWithSchema[P, T]:
        # Override function name if provided
        if name:
            func.__name__ = name

        # Validate context parameter if present
        sig = inspect.signature(func)
        if "ctx" in sig.parameters:
            ctx_param = sig.parameters["ctx"]
            if ctx_param.kind != inspect.Parameter.KEYWORD_ONLY:
                raise ValueError("ctx parameter must be keyword-only (*, ctx)")

        # Register the function - registry will generate schema automatically
        REGISTRY.register(func, doc)

        # Return the function cast as CallableWithSchema to indicate it has __tool_schema__
        return cast(CallableWithSchema[P, T], func)

    return decorator
```

### Key Changes:

1. **Generic Protocol**: `CallableWithSchema[P, T]` preserves parameter and return types
2. **ParamSpec Usage**: Proper use of `P.args` and `P.kwargs` in the protocol
3. **Type Preservation**: The decorator returns `CallableWithSchema[P, T]` indicating the function has a `__tool_schema__` attribute
4. **Better Error Handling**: Added explicit KeyError for missing tools
5. **Proper Return Type**: `register` decorator now returns `CallableWithSchema[P, T]` instead of `Callable[P, T]` to indicate the enhanced function

### Alternative: Context-Aware Protocol

For functions that commonly use `ctx`, we could also define a specialized protocol:

```python
from portkit.tinyagent.context import PortKitContext

class ContextualTool(Protocol[P, T]):
    """Protocol for tools that accept a ctx parameter."""
    
    __tool_schema__: dict
    
    def __call__(self, *args: P.args, ctx: PortKitContext, **kwargs: P.kwargs) -> T: ...
```

This would provide even better type safety for context-aware tools.

## Impact
These type errors prevent proper static analysis but don't affect runtime behavior since the actual function signatures are correct. The proposed generic protocol solution would resolve both the argument type mismatch and unexpected keyword argument errors while maintaining runtime compatibility.