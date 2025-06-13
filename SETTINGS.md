# Implfuzz Settings Configuration

## Overview

The `implfuzz.py` module uses a configurable settings system to allow testing with different source and project directories. This enables isolation during testing and flexibility for different project structures.

## Settings Structure

```python
class ProjectSettings(BaseModel):
    c_source_path: Path      # Path to C source files
    rust_project_path: Path  # Path to Rust project root
```

## Default Configuration

```python
SETTINGS = ProjectSettings(
    c_source_path=Path(__file__).parent.parent / "zopfli/src/zopfli",
    rust_project_path=Path(__file__).parent.parent / "zopfli/rust",
)
```

## Overriding Settings for Testing

To use different paths (e.g., for testing), override the `SETTINGS` object:

### Method 1: Direct Override
```python
from portkit.implfuzz import SETTINGS
from pathlib import Path

# Override paths
SETTINGS.c_source_path = Path("/path/to/test/c/source")
SETTINGS.rust_project_path = Path("/path/to/test/rust/project")
```

### Method 2: Monkey Patching (Recommended for Tests)
```python
from unittest.mock import patch
from pathlib import Path
import portkit.implfuzz

with patch.object(portkit.implfuzz, 'SETTINGS') as mock_settings:
    mock_settings.c_source_path = Path("/temp/c/source")
    mock_settings.rust_project_path = Path("/temp/rust/project")
    # Run test code here
```

### Method 3: Environment-based Configuration (Future)
Could be extended to support environment variables:
```python
SETTINGS = ProjectSettings(
    c_source_path=Path(os.getenv("IMPLFUZZ_C_SOURCE", default_c_path)),
    rust_project_path=Path(os.getenv("IMPLFUZZ_RUST_PROJECT", default_rust_path)),
)
```

## Tools Affected by Settings

All registered tools use `SETTINGS` for path resolution:

- `read_c_source_file`: Uses `SETTINGS.c_source_path`
- `read_rust_source_file`: Uses `SETTINGS.rust_project_path`  
- `append_rust_code`: Uses `SETTINGS.rust_project_path`
- `write_rust_source_file`: Uses `SETTINGS.rust_project_path`
- `write_rust_fuzz_test`: Uses `SETTINGS.rust_project_path`
- `run_rust_fuzz_test`: Uses `SETTINGS.rust_project_path`

## Implementation Functions

The high-level pipeline functions also use `SETTINGS`:

- `generate_stub_impl`: References `SETTINGS.rust_project_path`
- `generate_fuzz_test`: References `SETTINGS.rust_project_path`
- `generate_full_impl`: References `SETTINGS.rust_project_path`
- `run_traversal_pipeline`: Uses `SETTINGS.c_source_path`

## Testing Strategy

The configurable settings enable:

1. **Isolation**: Each test can use temporary directories
2. **Safety**: No modification of actual project files during testing
3. **Flexibility**: Easy to test different project structures
4. **Reproducibility**: Consistent test environments

## Example Test Setup

```python
import tempfile
from pathlib import Path
from unittest.mock import patch
import portkit.implfuzz

def test_with_temp_dirs():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        c_source = temp_path / "c_source"
        rust_project = temp_path / "rust_project"
        
        # Create directory structure
        c_source.mkdir()
        (rust_project / "src").mkdir(parents=True)
        
        # Mock settings
        with patch.object(portkit.implfuzz, 'SETTINGS') as mock_settings:
            mock_settings.c_source_path = c_source
            mock_settings.rust_project_path = rust_project
            
            # Run test code that uses the tools
            # All file operations will use temporary directories
```

This approach ensures tests are isolated, safe, and maintainable while keeping the production code simple and configurable.