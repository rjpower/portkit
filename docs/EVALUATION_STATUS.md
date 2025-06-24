# Patch Tool Evaluation Status Report

## Current Status

I've been working to create realistic evaluation tests for the patch_file tool, but I'm encountering several issues that are preventing successful execution.

## Goal

Create a comprehensive evaluation suite that:
1. Uses realistic file-based scenarios (reading C headers, making specific changes)
2. Tests the LLM's ability to use both `read_files` and `patch_file` tools together
3. Validates actual file output rather than just tool call success
4. Runs against Gemini 2.5 Flash and Pro models to measure performance

## Current Implementation

I've created:
- **evaluation_simple.py**: 5 test cases using a `test_project()` context manager
- **Context manager**: Automatically sets up temp directories with test C header files
- **Output validation**: Checks actual file contents after operations
- **Realistic scenarios**: Buffer size changes, function additions, const qualifiers, etc.

## Current Struggles

### 1. Tool Context Issues
The existing `read_files` tool expects a context with `config` attribute:
```python
# From portkit/tools/read_files.py
def read_files(args: ReadFileRequest, *, ctx: ReadFilesContext) -> ReadFileResult:
```

But the evaluation framework's LLMHelper doesn't provide this context, causing:
```
Context missing required attribute: config
```

### 2. Tool Registration Confusion
- The evaluation framework discovers tools from `portkit.tidyllm.tools`
- The existing `read_files` is in `portkit/tools/read_files.py` 
- I attempted to create a simplified version but that created conflicts

### 3. Tool Library Integration
The evaluation framework creates a `FunctionLibrary` from discovered tools, but the context passing mechanism isn't working properly for tools that need additional context parameters.

## What I Need to Fix

1. **Fix the tool context issue**: Either modify how the evaluation framework provides context to tools, or understand how the existing `read_files` tool is supposed to work within the evaluation framework

2. **Ensure proper tool registration**: Make sure both `read_files` and `patch_file` are available and working correctly in the evaluation environment

3. **Test the complete workflow**: LLM should be able to read a file, understand its contents, and then create appropriate patches

## Next Steps

I need guidance on:
1. How should tools requiring context (like `read_files`) work within the evaluation framework?
2. Should I modify the existing tools, the evaluation framework, or my test approach?
3. Is there an existing pattern for this type of multi-tool evaluation that I should follow?

## Technical Challenge

The core technical challenge is bridging the gap between tools that expect runtime context (project config, etc.) and the simplified evaluation environment that just provides an LLM with tool access.

## Files Created

- `/home/power/code/portkit/portkit/tidyllm/tools/patch_file/evaluation_simple.py` - 5 realistic evaluation tests
- `/home/power/code/portkit/docs/PATCH_EVALUATION_SPEC.md` - Formal specification document
- `/home/power/code/portkit/portkit/tidyllm/tools/simple_read_files/__init__.py` - Attempted simplified read_files (should be removed)

## Current Error

```
Context missing required attribute: config
```

This occurs when the LLM tries to call `read_files` because the tool expects a context parameter that the evaluation framework doesn't provide.