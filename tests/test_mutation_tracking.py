#!/usr/bin/env python3

import tempfile
from pathlib import Path

from portkit.implfuzz import BuilderContext, handler
from portkit.sourcemap import SourceMap


def test_mutation_tracking():
    """Test that mutation tracking works correctly for different tool types."""

    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust" / "src"
        rust_dir.mkdir(parents=True)

        # Create a test file
        test_file = rust_dir / "test.rs"
        test_file.write_text("// Initial content\n")

        # Create lib.rs to avoid errors
        lib_rs = rust_dir / "lib.rs"
        lib_rs.write_text("// lib file\n")

        # Setup context and handler
        ctx = BuilderContext(
            project_root=temp_path,
            source_map=SourceMap(temp_path),
        )
        handler.set_context(ctx)

        # Test 1: Read-only operations should not set has_mutations
        print("Test 1: Read operations...")
        assert not ctx.has_mutations, "Should start with no mutations"

        # Simulate read_files call
        handler.run(
            "read_files", 
            '{"paths": ["rust/src/test.rs"]}', 
            "test_call_1"
        )
        assert not ctx.has_mutations, "Read operation should not set mutations flag"

        # Simulate list_files call
        handler.run(
            "list_files", 
            '{"directory": "rust/src"}', 
            "test_call_2"
        )
        assert not ctx.has_mutations, "List operation should not set mutations flag"

        # Test 2: Mutating operations should set has_mutations
        print("Test 2: Write operations...")

        # Simulate replace_file call
        handler.run(
            "replace_file", 
            '{"path": "rust/src/test.rs", "content": "// Modified content\\n"}', 
            "test_call_3"
        )
        assert ctx.has_mutations, "Write operation should set mutations flag"

        # Test 3: Reset should clear mutations
        print("Test 3: Reset functionality...")
        ctx.reset_read_files()
        assert not ctx.has_mutations, "Reset should clear mutations flag"

        print("All mutation tracking tests passed!")


if __name__ == "__main__":
    test_mutation_tracking()
