# Fix Prompt Reading in TidyAgent Examples

## Problem Summary

The TidyAgent framework includes a `read_prompt()` function for loading external prompt files with include directive support, but the example tools are not using it properly:

### Current State

1. **Patch File Tool (`portkit/tidyagent/examples/patch_file/`)**:
   - ✅ Has a comprehensive `prompt.md` file with detailed documentation
   - ❌ Uses inline docstring in `__init__.py` instead of `@register(doc=read_prompt("prompt.md"))`
   - ❌ The external prompt.md is being ignored

2. **Calculator Tool (`portkit/tidyagent/examples/calculator/`)**:
   - ❌ No `prompt.md` file exists
   - ❌ Only has basic inline docstring
   - ❌ Not demonstrating external prompt usage

3. **Registry System (`portkit/tidyagent/registry.py`)**:
   - ✅ Supports `doc` parameter in `@register(doc=read_prompt("file.md"))`
   - ✅ `read_prompt()` function exists and supports `{{include: ./file.md}}` directives
   - ✅ Framework is ready for external prompt files

## Analysis Details

### Patch File Tool Issue
The patch file tool has excellent documentation in `prompt.md` (97 lines) covering:
- Unified diff format specification
- Parameter descriptions
- Multiple examples (simple replacement, multi-line, adding/removing lines)
- Important usage notes
- Success indicators

However, the `@register()` decorator in `__init__.py:9` doesn't use the `doc` parameter, so this rich documentation is ignored during schema generation.

### Calculator Tool Missing Feature
The calculator tool only has a basic inline docstring and no external prompt file, missing the opportunity to demonstrate both approaches.

## Proposed Solution

### 1. Fix Patch File Tool
```python
# In portkit/tidyagent/examples/patch_file/__init__.py
from portkit.tidyagent.prompt import read_prompt

@register(doc=read_prompt("prompt.md"), require_context=False)
def patch_file(args: PatchArgs) -> PatchResult | ToolError:
    # Keep minimal docstring for code readability
    """Apply unified diff patches to text content."""
    # ... rest of implementation
```

### 2. Enhance Calculator Tool
Create `portkit/tidyagent/examples/calculator/prompt.md`:
```markdown
# Calculator Tool

Perform basic mathematical calculations with two operands.

## Supported Operations
- **add**: Addition (left + right)
- **subtract**: Subtraction (left - right) 
- **multiply**: Multiplication (left * right)
- **divide**: Division (left / right)

## Parameters
- **operation**: Mathematical operation type
- **left**: First number (left operand)
- **right**: Second number (right operand)

## Examples
{{include: ./examples.md}}
```

Then update the registration:
```python
@register(doc=read_prompt("prompt.md"), require_context=False)
def calculator(args: CalculatorArgs) -> CalculatorResult | ToolError:
    """Perform basic mathematical operations."""  # Minimal inline docstring
```

### 3. Test Both Approaches
Create test cases to verify:
- Tools with inline docstrings work correctly
- Tools with `@register(doc=read_prompt())` work correctly
- Schema generation includes the external prompt content
- Include directives are processed correctly

## Benefits

1. **Consistency**: Both example tools demonstrate the external prompt approach
2. **Documentation**: Rich, maintainable documentation in separate files
3. **Flexibility**: Shows both inline and external documentation patterns
4. **Testing**: Validates the `read_prompt()` functionality is working
5. **Examples**: Provides clear patterns for users to follow

## Implementation Plan

1. Update patch file tool to use `@register(doc=read_prompt("prompt.md"))`
2. Create prompt.md for calculator tool with include directives
3. Update calculator tool registration
4. Add tests for both inline and external prompt approaches
5. Verify schema generation includes external prompt content

This fix ensures the TidyAgent framework's external prompt capabilities are properly demonstrated and tested.