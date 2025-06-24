# Patch File Tool Specification

## Overview

The Patch File Tool is a comprehensive reference implementation that demonstrates TidyAgent best practices. It provides precise text replacement in files using exact string matching, similar to Git patch application. This tool serves as both a practical utility and a template for creating robust, well-tested tools.

## Tool Functionality

### Core Capability
Apply precise text changes to files by replacing exact text content. The tool searches for an exact match of `old_content` in the target file and replaces it with `new_content`.

### Key Features
- **Exact string matching** - No regex or fuzzy matching to avoid unintended changes
- **Dry run support** - Preview changes without applying them
- **Comprehensive error handling** - Clear feedback for all failure cases
- **Git-style diff preview** - Visual representation of changes
- **Path validation** - Ensures files exist within project boundaries
- **Context-aware operation** - Respects project root and security constraints

## Architecture

### Directory Structure
```
examples/patch_file/
├── __init__.py              # Main tool implementation with @register decorator
├── models.py               # Pydantic models for arguments and results
├── context.py              # Protocol defining context requirements
├── lib.py                  # Core implementation functions
├── PROMPT.md               # Tool documentation for LLMs
├── prompts/
│   ├── overview.md         # High-level tool description
│   ├── parameters.md       # Parameter documentation
│   ├── examples.md         # Usage examples
│   └── safety.md          # Safety considerations and limitations
├── tests/
│   ├── test_patch.py       # Unit tests
│   ├── test_integration.py # Integration tests with FunctionLibrary
│   └── benchmark.py        # LLM benchmark test cases
└── README.md               # Development documentation
```

## Data Models

### PatchArgs (Input Model)
```python
from pydantic import BaseModel, Field, validator

class PatchArgs(BaseModel):
    """Arguments for the patch_file tool."""
    
    file_path: str = Field(
        description="Path to the file to patch, relative to project root",
        examples=["src/main.py", "config/settings.json", "docs/README.md"]
    )
    
    old_content: str = Field(
        description="Exact text to find and replace (must match exactly including whitespace)",
        examples=[
            "def hello():\n    print('world')",
            "from typing import List",
            "version = '1.0.0'"
        ]
    )
    
    new_content: str = Field(
        description="Text to replace the old content with",
        examples=[
            "def hello():\n    print('Hello, world!')",
            "from typing import List, Dict",
            "version = '1.1.0'"
        ]
    )
    
    @validator('file_path')
    def validate_file_path(cls, v):
        """Ensure file path is safe and relative."""
        if v.startswith('/') or '..' in v:
            raise ValueError("File path must be relative and within project root")
        return v
    
    @validator('old_content')
    def validate_old_content(cls, v):
        """Ensure old content is not empty."""
        if not v.strip():
            raise ValueError("Old content cannot be empty")
        return v

class PatchResult(BaseModel):
    """Result of patch operation."""
    
    success: bool = Field(description="Whether the patch was applied successfully")
    file_path: str = Field(description="The file that was patched")
    message: str = Field(description="Success or error message")
    changes_preview: str | None = Field(
        default=None,
        description="Diff preview of changes (for dry runs or successful patches)"
    )
    line_numbers: dict[str, int] | None = Field(
        default=None,
        description="Line numbers where changes were made"
    )
```

### Context Protocol
```python
from typing import Protocol
from pathlib import Path

class PatchContext(Protocol):
    """Context requirements for patch_file tool."""
    
    project_root: Path
    """Root directory of the project - all file paths are relative to this."""
    
    dry_run: bool
    """If True, show preview of changes without applying them."""
    
    max_file_size: int
    """Maximum file size in bytes that can be patched (default: 1MB)."""
    
    allowed_extensions: list[str] | None
    """Allowed file extensions. If None, all extensions are allowed."""
    
    backup_enabled: bool
    """Whether to create backup files before patching."""
```

## Core Implementation

### Main Tool Function
```python
from portkit.tidyagent import register, read_prompt, ToolError
from .models import PatchArgs, PatchResult
from .context import PatchContext
from .lib import (
    find_exact_match, 
    create_patch_preview, 
    validate_file_access,
    create_backup
)

@register(doc=read_prompt("./PROMPT.md"))
def patch_file(args: PatchArgs, *, ctx: PatchContext) -> PatchResult | ToolError:
    """Apply a text patch to a file.
    
    This tool provides precise text replacement in files using exact string matching.
    It's designed for surgical edits to code, configuration files, and documentation.
    
    Args:
        file_path: Path to file relative to project root
        old_content: Exact text to find and replace
        new_content: Replacement text
        
    Returns:
        PatchResult with success status and details, or ToolError on failure
    """
    try:
        # Resolve and validate file path
        file_path = ctx.project_root / args.file_path
        
        # Security and validation checks
        validation_error = validate_file_access(file_path, ctx)
        if validation_error:
            return ToolError(error=validation_error)
        
        # Read current content
        try:
            content = file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            return ToolError(
                error=f"File {args.file_path} is not a text file (binary content detected)"
            )
        except Exception as e:
            return ToolError(error=f"Failed to read file: {str(e)}")
        
        # Check file size limit
        if len(content) > ctx.max_file_size:
            return ToolError(
                error=f"File too large: {len(content)} bytes (max: {ctx.max_file_size})"
            )
        
        # Find exact match
        match_result = find_exact_match(content, args.old_content)
        if not match_result.found:
            return ToolError(
                error="Exact match not found",
                details={
                    "searched_for": args.old_content[:200] + "..." if len(args.old_content) > 200 else args.old_content,
                    "suggestions": match_result.suggestions,
                    "file_preview": content[:300] + "..." if len(content) > 300 else content
                }
            )
        
        # Create patched content
        patched_content = (
            content[:match_result.start_index] + 
            args.new_content + 
            content[match_result.end_index:]
        )
        
        # Generate diff preview
        diff_preview = create_patch_preview(content, patched_content, args.file_path)
        
        # Calculate line numbers
        lines_before = content[:match_result.start_index].count('\n')
        lines_after = patched_content[:match_result.start_index + len(args.new_content)].count('\n')
        
        line_numbers = {
            "start_line": lines_before + 1,
            "end_line": lines_after + 1,
            "lines_changed": lines_after - lines_before + 1
        }
        
        # Handle dry run
        if ctx.dry_run:
            return PatchResult(
                success=True,
                file_path=args.file_path,
                message=f"Dry run - would apply patch to {args.file_path}",
                changes_preview=diff_preview,
                line_numbers=line_numbers
            )
        
        # Create backup if enabled
        if ctx.backup_enabled:
            backup_path = create_backup(file_path)
        
        # Apply patch
        try:
            file_path.write_text(patched_content, encoding='utf-8')
            
            success_message = f"Successfully patched {args.file_path}"
            if ctx.backup_enabled:
                success_message += f" (backup created: {backup_path.name})"
            
            return PatchResult(
                success=True,
                file_path=args.file_path,
                message=success_message,
                changes_preview=diff_preview,
                line_numbers=line_numbers
            )
            
        except Exception as e:
            return ToolError(error=f"Failed to write patched file: {str(e)}")
            
    except Exception as e:
        return ToolError(
            error=f"Unexpected error in patch_file: {str(e)}",
            details={"args": args.model_dump()}
        )
```

### Supporting Functions (lib.py)
```python
import difflib
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

@dataclass
class MatchResult:
    """Result of searching for exact match in content."""
    found: bool
    start_index: int = -1
    end_index: int = -1
    suggestions: list[str] = None
    
    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []

def find_exact_match(content: str, search: str) -> MatchResult:
    """Find exact match of search string in content.
    
    Args:
        content: File content to search in
        search: Text to search for
        
    Returns:
        MatchResult with match details and suggestions if not found
    """
    index = content.find(search)
    
    if index != -1:
        return MatchResult(
            found=True,
            start_index=index,
            end_index=index + len(search)
        )
    
    # Generate helpful suggestions for partial matches
    suggestions = []
    
    # Look for similar lines
    search_lines = search.split('\n')
    content_lines = content.split('\n')
    
    for i, content_line in enumerate(content_lines):
        for search_line in search_lines:
            if search_line.strip() in content_line.strip():
                suggestions.append(f"Line {i+1}: {content_line.strip()}")
                break
    
    # Limit suggestions to most relevant
    suggestions = suggestions[:5]
    
    return MatchResult(
        found=False,
        suggestions=suggestions
    )

def create_patch_preview(original: str, patched: str, file_path: str) -> str:
    """Create a unified diff preview of the changes.
    
    Args:
        original: Original file content
        patched: Patched file content  
        file_path: File path for diff headers
        
    Returns:
        Unified diff string
    """
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        patched.splitlines(keepends=True),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=3  # 3 lines of context
    )
    return ''.join(diff)

def validate_file_access(file_path: Path, ctx: PatchContext) -> Optional[str]:
    """Validate that file can be safely accessed and modified.
    
    Args:
        file_path: Absolute path to file
        ctx: Patch context with constraints
        
    Returns:
        Error message if validation fails, None if valid
    """
    # Check if file exists
    if not file_path.exists():
        return f"File not found: {file_path.relative_to(ctx.project_root)}"
    
    # Check if it's actually a file
    if not file_path.is_file():
        return f"Path is not a file: {file_path.relative_to(ctx.project_root)}"
    
    # Check file extension if restricted
    if ctx.allowed_extensions:
        if file_path.suffix not in ctx.allowed_extensions:
            return f"File extension {file_path.suffix} not allowed. Allowed: {ctx.allowed_extensions}"
    
    # Check if file is readable
    if not os.access(file_path, os.R_OK):
        return f"File is not readable: {file_path.relative_to(ctx.project_root)}"
    
    # Check if file is writable
    if not os.access(file_path, os.W_OK):
        return f"File is not writable: {file_path.relative_to(ctx.project_root)}"
    
    return None

def create_backup(file_path: Path) -> Path:
    """Create a backup of the file before patching.
    
    Args:
        file_path: Path to file to backup
        
    Returns:
        Path to created backup file
    """
    import datetime
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = file_path.with_suffix(f"{file_path.suffix}.bak.{timestamp}")
    
    backup_path.write_text(file_path.read_text())
    return backup_path
```

## Documentation (PROMPT.md)

### Main Prompt File
```markdown
# Patch File Tool

{{include: ./prompts/overview.md}}

## Parameters

{{include: ./prompts/parameters.md}}

## Examples

{{include: ./prompts/examples.md}}

## Safety and Limitations

{{include: ./prompts/safety.md}}
```

### prompts/overview.md
```markdown
Apply precise changes to files by replacing exact text content.

This tool searches for an exact match of `old_content` in the file and replaces it with `new_content`. The match must be exact, including whitespace and newlines.

**Key Features:**
- Exact string matching prevents unintended changes
- Git-style diff preview shows exactly what will change
- Dry run mode allows safe preview of changes
- Comprehensive error messages help diagnose issues
- Backup creation for safety

**Best Use Cases:**
- Fixing specific bugs in code
- Updating configuration values
- Modifying import statements
- Changing function signatures
- Updating documentation
```

### prompts/parameters.md
```markdown
- **file_path** (str): Path to the file to patch, relative to project root
  - Must be a relative path (no leading `/` or `..`)
  - Examples: `src/main.py`, `config/settings.json`, `docs/README.md`

- **old_content** (str): Exact text to find and replace
  - Must match exactly including all whitespace, newlines, and formatting
  - Cannot be empty or only whitespace
  - Examples: `def hello():`, `from typing import List`, `version = "1.0.0"`

- **new_content** (str): Text to replace the old content with
  - Can be empty string to delete content
  - Should maintain proper indentation and formatting
  - Examples: `def hello(name):`, `from typing import List, Dict`, `version = "1.1.0"`
```

### prompts/examples.md
```markdown
## Example: Fix import statement

```json
{
  "name": "patch_file",
  "arguments": {
    "file_path": "src/main.py",
    "old_content": "from typing import List",
    "new_content": "from typing import List, Dict"
  }
}
```

## Example: Update function implementation

```json
{
  "name": "patch_file", 
  "arguments": {
    "file_path": "src/utils.py",
    "old_content": "def process(data):\n    return data",
    "new_content": "def process(data):\n    # Process the data\n    return data.strip().lower()"
  }
}
```

## Example: Fix bug in condition

```json
{
  "name": "patch_file",
  "arguments": {
    "file_path": "src/validator.py", 
    "old_content": "if user.age > 18:",
    "new_content": "if user.age >= 18:"
  }
}
```

## Example: Update configuration value

```json
{
  "name": "patch_file",
  "arguments": {
    "file_path": "config/settings.json",
    "old_content": "\"debug\": false",
    "new_content": "\"debug\": true"
  }
}
```
```

### prompts/safety.md
```markdown
## Safety Considerations

**Exact Matching Required:**
- The `old_content` must match exactly what's in the file
- Include all whitespace, newlines, and formatting 
- Use consistent indentation (tabs vs spaces)

**File Path Security:**
- All paths are relative to the project root
- Cannot access files outside the project directory
- File must exist and be readable/writable

**Content Validation:**
- Files must be text files (UTF-8 encoding)
- Binary files will be rejected
- File size limits apply for performance

**Error Recovery:**
- Tool provides helpful suggestions when exact match fails
- Backup files created before changes (if enabled)
- Dry run mode allows safe preview of changes

**Best Practices:**
- Always test with dry run first for complex changes
- Copy the exact text from the file to ensure matching
- Consider breaking large changes into smaller patches
- Review the diff preview before confirming changes
```

## Testing Strategy

### Unit Tests (test_patch.py)
```python
import pytest
from pathlib import Path
from patch_file import patch_file
from patch_file.models import PatchArgs, PatchResult
from portkit.tidyagent import ToolError

class MockContext:
    def __init__(self, tmpdir, dry_run=False):
        self.project_root = Path(tmpdir)
        self.dry_run = dry_run
        self.max_file_size = 1_000_000
        self.allowed_extensions = None
        self.backup_enabled = True

def test_patch_file_success(tmp_path):
    """Test successful patch application."""
    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello():\n    print('world')")
    
    # Create context
    ctx = MockContext(tmp_path)
    
    # Create patch args
    args = PatchArgs(
        file_path="test.py",
        old_content="print('world')",
        new_content="print('hello world')"
    )
    
    # Apply patch
    result = patch_file(args, ctx=ctx)
    
    assert isinstance(result, PatchResult)
    assert result.success
    assert test_file.read_text() == "def hello():\n    print('hello world')"
    assert "Successfully patched" in result.message

def test_patch_file_not_found(tmp_path):
    """Test error when file doesn't exist."""
    ctx = MockContext(tmp_path)
    args = PatchArgs(
        file_path="missing.py",
        old_content="foo",
        new_content="bar"
    )
    
    result = patch_file(args, ctx=ctx)
    
    assert isinstance(result, ToolError)
    assert "not found" in result.error

def test_patch_file_no_match(tmp_path):
    """Test error when old_content doesn't match."""
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello():\n    print('world')")
    
    ctx = MockContext(tmp_path)
    args = PatchArgs(
        file_path="test.py",
        old_content="print('universe')",  # Doesn't exist
        new_content="print('hello')"
    )
    
    result = patch_file(args, ctx=ctx)
    
    assert isinstance(result, ToolError)
    assert "not found" in result.error
    assert "suggestions" in result.details

def test_dry_run(tmp_path):
    """Test dry run functionality."""
    test_file = tmp_path / "test.py"
    original_content = "def hello():\n    print('world')"
    test_file.write_text(original_content)
    
    ctx = MockContext(tmp_path, dry_run=True)
    args = PatchArgs(
        file_path="test.py",
        old_content="print('world')",
        new_content="print('hello world')"
    )
    
    result = patch_file(args, ctx=ctx)
    
    assert isinstance(result, PatchResult)
    assert result.success
    assert "Dry run" in result.message
    assert result.changes_preview is not None
    # Original file unchanged
    assert test_file.read_text() == original_content

def test_backup_creation(tmp_path):
    """Test backup file creation."""
    test_file = tmp_path / "test.py"
    test_file.write_text("original content")
    
    ctx = MockContext(tmp_path)
    ctx.backup_enabled = True
    
    args = PatchArgs(
        file_path="test.py",
        old_content="original",
        new_content="modified"
    )
    
    result = patch_file(args, ctx=ctx)
    
    assert isinstance(result, PatchResult)
    assert result.success
    assert "backup created" in result.message
    
    # Check backup exists
    backup_files = list(tmp_path.glob("test.py.bak.*"))
    assert len(backup_files) == 1
    assert backup_files[0].read_text() == "original content"

def test_file_size_limit(tmp_path):
    """Test file size limit enforcement."""
    test_file = tmp_path / "large.txt"
    test_file.write_text("x" * 1000)  # 1000 bytes
    
    ctx = MockContext(tmp_path)
    ctx.max_file_size = 500  # Smaller limit
    
    args = PatchArgs(
        file_path="large.txt",
        old_content="x",
        new_content="y"
    )
    
    result = patch_file(args, ctx=ctx)
    
    assert isinstance(result, ToolError)
    assert "too large" in result.error

def test_extension_restriction(tmp_path):
    """Test file extension restrictions."""
    test_file = tmp_path / "script.sh"
    test_file.write_text("echo hello")
    
    ctx = MockContext(tmp_path)
    ctx.allowed_extensions = [".py", ".txt"]  # .sh not allowed
    
    args = PatchArgs(
        file_path="script.sh",
        old_content="hello",
        new_content="world"
    )
    
    result = patch_file(args, ctx=ctx)
    
    assert isinstance(result, ToolError)
    assert "not allowed" in result.error
```

### Benchmark Tests (benchmark.py)
```python
"""Benchmark tests for patch_file tool with LLMs."""

from portkit.tidyagent.benchmark import TestCase

PATCH_FILE_BENCHMARK = [
    TestCase(
        id="simple_string_replacement",
        description="Simple string replacement in Python file",
        prompt="Change the greeting from 'Hello' to 'Hi' in greet.py",
        expected_tool="patch_file",
        expected_args={
            "file_path": "greet.py",
            "old_content": "return 'Hello, world!'",
            "new_content": "return 'Hi, world!'"
        },
        setup_files={
            "greet.py": "def greet():\n    return 'Hello, world!'"
        },
        validate_result=lambda r: r.get("success") is True,
        tags=["basic", "string_replacement"]
    ),
    
    TestCase(
        id="multiline_function_update",
        description="Update multi-line function with error handling",
        prompt="Add error handling to the divide function in math.py - check for division by zero",
        expected_tool="patch_file",
        expected_args={
            "file_path": "math.py",
            "old_content": "def divide(a, b):\n    return a / b",
            "new_content": "def divide(a, b):\n    if b == 0:\n        raise ValueError('Cannot divide by zero')\n    return a / b"
        },
        setup_files={
            "math.py": "def divide(a, b):\n    return a / b"
        },
        validate_result=lambda r: r.get("success") is True,
        tags=["multiline", "error_handling"],
        difficulty="medium"
    ),
    
    TestCase(
        id="import_statement_modification",
        description="Add Dict to typing imports",
        prompt="Add Dict to the typing imports in types.py",
        expected_tool="patch_file", 
        expected_args={
            "file_path": "types.py",
            "old_content": "from typing import List, Optional",
            "new_content": "from typing import List, Optional, Dict"
        },
        setup_files={
            "types.py": "from typing import List, Optional\n\nMyList = List[str]"
        },
        validate_result=lambda r: r.get("success") is True,
        tags=["imports", "typing"],
        difficulty="easy"
    ),
    
    TestCase(
        id="exact_match_failure",
        description="Handle case where exact match is not found",
        prompt="Change 'print(hello)' to 'print(world)' in broken.py",
        expected_tool="patch_file",
        expected_args={
            "file_path": "broken.py", 
            "old_content": "print(hello)",
            "new_content": "print(world)"
        },
        setup_files={
            "broken.py": "print('hello')"  # Note: quotes don't match
        },
        validate_result=lambda r: "error" in str(r).lower(),
        tags=["error_handling", "edge_cases"],
        difficulty="hard"
    ),
    
    TestCase(
        id="configuration_value_update",
        description="Update JSON configuration value",
        prompt="Enable debug mode in the config.json file",
        expected_tool="patch_file",
        expected_args={
            "file_path": "config.json",
            "old_content": '"debug": false',
            "new_content": '"debug": true'
        },
        setup_files={
            "config.json": '{\n  "app_name": "test",\n  "debug": false,\n  "port": 8080\n}'
        },
        validate_result=lambda r: r.get("success") is True,
        tags=["configuration", "json"],
        difficulty="easy"
    )
]
```

## CLI Integration

The tool automatically gets CLI generation through TidyAgent:

```bash
# Test the tool via CLI
python -m examples.patch_file --file-path src/main.py \
    --old-content "print('hello')" \
    --new-content "print('world')"

# Or with JSON input
python -m examples.patch_file --json '{
    "file_path": "src/main.py",
    "old_content": "print(\"hello\")", 
    "new_content": "print(\"world\")"
}'

# Dry run via environment or context
DRY_RUN=true python -m examples.patch_file --file-path test.py \
    --old-content "old" --new-content "new"
```

## Integration Examples

### With FunctionLibrary
```python
from portkit.tidyagent import FunctionLibrary
from examples.patch_file import patch_file

# Create library with context
library = FunctionLibrary(
    functions=[patch_file],
    context={
        "project_root": Path("/workspace"),
        "dry_run": False,
        "max_file_size": 1_000_000,
        "allowed_extensions": [".py", ".js", ".md"],
        "backup_enabled": True
    }
)

# Use with LLM
result = library.call({
    "name": "patch_file",
    "arguments": {
        "file_path": "src/main.py",
        "old_content": "def old_function():",
        "new_content": "def new_function():"
    }
})
```

This patch file tool provides a complete reference implementation showcasing TidyAgent best practices while serving as a practical utility for precise file modifications.