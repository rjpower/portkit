#!/usr/bin/env python3
"""
Tests for the implfuzz module tools and functions.

Tests the various individual tools in implfuzz.py like write_fuzz_test,
read_c_source_file, append_code, etc.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from portkit.implfuzz import (
    AppendFileRequest,
    BuilderContext,
    EditCodeRequest,
    FuzzTestError,
    ReadFileRequest,
    RunFuzzTestRequest,
    SearchRequest,
    TaskStatus,
    TaskStatusType,
    WriteFileRequest,
    append_to_file,
    compile_rust_project,
    edit_code,
    handler,
    read_file,
    run_rust_fuzz_test,
    search_files,
    write_file,
)


def test_tools_spec_generation():
    """Test that tool specs are generated correctly."""
    specs = handler.get_tools_spec()
    assert isinstance(specs, list)
    assert len(specs) > 0

    # Check structure of first spec
    spec = specs[0]
    assert "type" in spec
    assert spec["type"] == "function"
    assert "function" in spec
    assert "name" in spec["function"]
    assert "parameters" in spec["function"]


def test_read_existing_c_source_file():
    """Test reading an existing C source file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".h", delete=False) as f:
        f.write("/* Test header */\nint test_function(void);")
        temp_path = f.name

    try:
        ctx = BuilderContext(project_root=Path(temp_path).parent)

        request = ReadFileRequest(path=Path(temp_path).name)
        result = read_file(request, ctx=ctx)

        assert "/* Test header */" in result.source
        assert "int test_function(void);" in result.source
    finally:
        Path(temp_path).unlink()


def test_read_nonexistent_c_source_file():
    """Test reading a non-existent file raises appropriate error."""
    ctx = BuilderContext(project_root=Path("/tmp"))
    request = ReadFileRequest(path="nonexistent.h")

    with pytest.raises(ValueError):
        read_file(request, ctx=ctx)


def test_append_rust_code_creates_file():
    """Test that append_to_file creates file if it doesn't exist."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust"
        src_dir = rust_dir / "src"
        src_dir.mkdir(parents=True)

        # Create lib.rs
        (src_dir / "lib.rs").write_text("// lib.rs\n")

        ctx = BuilderContext(project_root=temp_path)

        # Mock the compile function to return success
        with patch("portkit.implfuzz.compile_rust_project"):

            request = AppendFileRequest(
                path="rust/src/test.rs", content="pub fn test() { unimplemented!(); }"
            )
            result = append_to_file(request, ctx=ctx)

            assert result.success is True

            # Check file was created and contains content
            test_file = src_dir / "test.rs"
            assert test_file.exists()
            assert "pub fn test()" in test_file.read_text()

            # Check lib.rs was updated
            lib_content = (src_dir / "lib.rs").read_text()
            assert "pub mod test;" in lib_content


def test_append_rust_code_appends_to_existing():
    """Test that append_to_file appends to existing file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust"
        src_dir = rust_dir / "src"
        src_dir.mkdir(parents=True)

        # Create existing files
        test_file = src_dir / "test.rs"
        test_file.write_text("existing content\n")
        (src_dir / "lib.rs").write_text("pub mod test;\n")

        ctx = BuilderContext(project_root=temp_path)

        with patch("portkit.implfuzz.compile_rust_project"):

            request = AppendFileRequest(path="rust/src/test.rs", content="new content")
            result = append_to_file(request, ctx=ctx)

            assert result.success is True

            content = test_file.read_text()
            assert "existing content" in content
            assert "new content" in content


def test_write_fuzz_test_creates_file_and_cargo_entry():
    """Test that fuzz test file and Cargo.toml entry are created."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust"

        # Create required directories
        fuzz_dir = rust_dir / "fuzz" / "fuzz_targets"
        fuzz_dir.mkdir(parents=True)

        # Create Cargo.toml in fuzz directory
        fuzz_cargo_toml = rust_dir / "fuzz" / "Cargo.toml"
        fuzz_cargo_toml.write_text('[package]\nname = "test"')

        ctx = BuilderContext(project_root=temp_path)

        with patch("portkit.implfuzz.compile_rust_project"):

            request = WriteFileRequest(
                path="rust/fuzz/fuzz_targets/test_target.rs",
                content="#![no_main]\nuse libfuzzer_sys::fuzz_target;\nfuzz_target!(|data: &[u8]| {});",
            )
            result = write_file(request, ctx=ctx)

            assert result.success is True

            # Check fuzz test file was created
            fuzz_file = fuzz_dir / "test_target.rs"
            assert fuzz_file.exists()
            assert "fuzz_target!" in fuzz_file.read_text()

            # Check Cargo.toml was updated
            cargo_content = fuzz_cargo_toml.read_text()
            assert 'name = "test_target"' in cargo_content
            assert 'path = "fuzz_targets/test_target.rs"' in cargo_content


def test_write_fuzz_test_skips_existing_cargo_entry():
    """Test that existing Cargo.toml entries are not duplicated."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust"
        fuzz_dir = rust_dir / "fuzz" / "fuzz_targets"
        fuzz_dir.mkdir(parents=True)

        # Create Cargo.toml with existing entry
        fuzz_cargo_toml = rust_dir / "fuzz" / "Cargo.toml"
        fuzz_cargo_toml.write_text(
            """[package]
name = "test"

[[bin]]
name = "test_target"
path = "fuzz_targets/test_target.rs"
"""
        )

        ctx = BuilderContext(project_root=temp_path)

        with patch("portkit.implfuzz.compile_rust_project"):
            request = WriteFileRequest(path="rust/fuzz/fuzz_targets/test_target.rs", content="test content")
            result = write_file(request, ctx=ctx)

        # Should return success without trying to compile
        assert result.success is True

        # Check Cargo.toml wasn't modified (no duplicate entries)
        cargo_content = fuzz_cargo_toml.read_text()
        assert cargo_content.count('name = "test_target"') == 1


@patch("portkit.implfuzz.subprocess.run")
def test_run_fuzz_test_success(mock_subprocess):
    """Test successful fuzz test run."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="")

    with tempfile.TemporaryDirectory() as temp_dir:
        ctx = BuilderContext(project_root=Path(temp_dir))

        request = RunFuzzTestRequest(target="test_target", timeout=30)
        result = run_rust_fuzz_test(request, ctx=ctx)

        assert result.success is True

        # Check subprocess was called with correct arguments
        mock_subprocess.assert_called_once()
        args = mock_subprocess.call_args[0][0]
        assert "cargo" in args
        assert "fuzz" in args
        assert "run" in args
        assert "test_target" in args
        assert "-max_total_time=30" in args


@patch("portkit.implfuzz.subprocess.run")
def test_run_fuzz_test_failure(mock_subprocess):
    """Test failed fuzz test run."""
    mock_subprocess.return_value = MagicMock(
        returncode=1, 
        stderr="Error: assertion failed: values differ\nother error"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        ctx = BuilderContext(project_root=Path(temp_dir))

        request = RunFuzzTestRequest(target="test_target")
        with pytest.raises(FuzzTestError):
            run_rust_fuzz_test(request, ctx=ctx)


@patch("portkit.implfuzz.subprocess.run")
def test_compile_rust_project_success(mock_subprocess):
    """Test successful compilation."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="")

    compile_rust_project(Path("/fake/path"))

    mock_subprocess.assert_called()


@patch("portkit.implfuzz.subprocess.run")
def test_compile_rust_project_failure(mock_subprocess):
    """Test compilation failure."""
    from portkit.implfuzz import CompileError

    mock_subprocess.return_value = MagicMock(
        returncode=1,
        stderr="error: expected `;`\nerror: cannot find function"
    )

    with pytest.raises(CompileError):
        compile_rust_project(Path("/fake/path"))


def test_tool_execution_success():
    """Test successful tool execution through handler."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".h", delete=False) as f:
        f.write("test content")
        temp_path = f.name

    try:
        ctx = BuilderContext(project_root=Path(temp_path).parent)
        handler.set_context(ctx)

        args_json = f'{{"path": "{Path(temp_path).name}"}}'
        result = handler.run("read_file", args_json, "test_id")

        assert result["role"] == "tool"
        assert result["tool_call_id"] == "test_id"
        assert "test content" in result["content"]
    finally:
        Path(temp_path).unlink()


def test_tool_execution_error():
    """Test tool execution with error."""
    ctx = BuilderContext(project_root=Path("/tmp"))
    handler.set_context(ctx)

    args_json = '{"path": "nonexistent.h"}'
    result = handler.run("read_file", args_json, "test_id")

    assert result["role"] == "tool"
    assert result["tool_call_id"] == "test_id"

    # Should contain error information
    content = json.loads(result["content"])
    assert "error" in content
    assert "type" in content


def test_unknown_tool_error():
    """Test calling unknown tool."""
    ctx = BuilderContext(project_root=Path("/tmp"))
    handler.set_context(ctx)

    result = handler.run("unknown_tool", "{}", "test_id")

    content = json.loads(result["content"])
    assert "error" in content
    assert "Unknown tool" in content["error"]


def test_context_creation():
    """Test that BuilderContext can be created with different paths."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        ctx = BuilderContext(project_root=temp_path)

        # Verify the context was created correctly
        assert ctx.project_root == temp_path


def test_task_status_success():
    """Test TaskStatus in success case."""
    status = TaskStatus()
    assert status.is_done()
    assert status.status == TaskStatusType.DONE
    assert len(status.errors) == 0
    assert "successfully" in status.get_feedback()


def test_task_status_with_errors():
    """Test TaskStatus with error reporting."""
    status = TaskStatus()
    status.error("First error message")
    status.error("Second error message")

    assert not status.is_done()
    assert status.status == TaskStatusType.INCOMPLETE
    assert len(status.errors) == 2
    assert "First error message" in status.errors
    assert "Second error message" in status.errors

    feedback = status.get_feedback()
    assert "not yet complete" in feedback
    assert "First error message" in feedback
    assert "Second error message" in feedback


@patch("portkit.implfuzz.subprocess.run")
def test_search_files_success(mock_subprocess):
    """Test successful search_files execution."""
    mock_subprocess.return_value = MagicMock(
        returncode=0,
        stdout="src/file1.c:10:int main() {\nsrc/file2.h:15:extern int func();"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        src_dir = temp_path / "src"
        src_dir.mkdir()
        
        ctx = BuilderContext(project_root=temp_path)

        request = SearchRequest(pattern="int", directory="src", context_lines=2)
        result = search_files(request, ctx=ctx)

        assert "src/file1.c:10:int main()" in result.match_output
        assert "src/file2.h:15:extern int func()" in result.match_output

        # Check subprocess was called with correct arguments
        mock_subprocess.assert_called_once()
        args = mock_subprocess.call_args[0][0]
        assert "grep" in args
        assert "-rn" in args
        assert "-C2" in args
        assert "--include=*.c" in args
        assert "--include=*.h" in args
        assert "--include=*.rs" in args
        assert "int" in args


def test_search_files_nonexistent_directory():
    """Test search_files with non-existent directory."""
    ctx = BuilderContext(project_root=Path("/tmp"))

    request = SearchRequest(pattern="test", directory="nonexistent")

    with pytest.raises(ValueError, match="Directory nonexistent does not exist"):
        search_files(request, ctx=ctx)


@patch("portkit.implfuzz.compile_rust_project")
def test_edit_code_success(mock_compile):
    """Test successful edit_code execution with unified diff patch."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust"
        src_dir = rust_dir / "src"
        src_dir.mkdir(parents=True)

        # Create initial Rust file
        test_file = src_dir / "test.rs"
        test_file.write_text("pub fn test() { unimplemented!(); }\n")

        ctx = BuilderContext(project_root=temp_path)

        # Working patch format
        patch_content = """--- test.rs.orig
+++ test.rs
@@ -1 +1 @@
-pub fn test() { unimplemented!(); }
+pub fn test() { println!(\"Hello\"); }"""

        request = EditCodeRequest(path="rust/src/test.rs", patch=patch_content)
        result = edit_code(request, ctx=ctx)

        assert result.success is True
        
        # Verify the file was actually patched
        updated_content = test_file.read_text()
        assert "println!" in updated_content
        assert "unimplemented!" not in updated_content


@patch("portkit.implfuzz.subprocess.run")
def test_edit_code_patch_failure(mock_subprocess):
    """Test edit_code handling patch application failure."""
    # Mock failed patch application for all strip levels and git apply
    mock_subprocess.return_value = MagicMock(
        returncode=1, stderr="patch: malformed patch at line 10"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust"
        src_dir = rust_dir / "src"
        src_dir.mkdir(parents=True)

        test_file = src_dir / "test.rs"
        test_file.write_text("pub fn test() { unimplemented!(); }")

        ctx = BuilderContext(project_root=temp_path)

        patch_content = """--- a/rust/src/test.rs
+++ b/rust/src/test.rs
@@ -1,1 +1,1 @@
-pub fn test() { unimplemented!(); }
+pub fn test() { println!("Hello"); }"""

        request = EditCodeRequest(path="rust/src/test.rs", patch=patch_content)

        with pytest.raises(ValueError, match="All patch application strategies failed"):
            edit_code(request, ctx=ctx)


def test_edit_code_nonexistent_file():
    """Test edit_code with non-existent file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        ctx = BuilderContext(project_root=Path(temp_dir))

        patch_content = """--- a/nonexistent.rs
+++ b/nonexistent.rs
@@ -1,1 +1,1 @@
-old line
+new line"""

        request = EditCodeRequest(path="nonexistent.rs", patch=patch_content)

        with pytest.raises(ValueError, match="File nonexistent.rs does not exist"):
            edit_code(request, ctx=ctx)


def test_edit_code_invalid_path():
    """Test edit_code with invalid file path (not in rust directory)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create file outside rust directory
        test_file = temp_path / "test.rs"
        test_file.write_text("test content")

        ctx = BuilderContext(project_root=temp_path)

        patch_content = """--- a/test.rs
+++ b/test.rs
@@ -1,1 +1,1 @@
-test content
+new content"""

        request = EditCodeRequest(path="test.rs", patch=patch_content)

        with pytest.raises(
            ValueError, match="must be in the rust/src or rust/fuzz directory"
        ):
            edit_code(request, ctx=ctx)


@patch("portkit.implfuzz.subprocess.run")
def test_edit_code_multiple_strip_levels(mock_subprocess):
    """Test edit_code trying multiple strip levels before succeeding."""
    # Mock failed patch at strip level 0 and 1, success at strip level 2
    mock_subprocess.side_effect = [
        MagicMock(returncode=1, stderr="patch failed"),  # dry-run p0
        MagicMock(returncode=1, stderr="patch failed"),  # dry-run p1
        MagicMock(returncode=0, stderr=""),  # dry-run p2 (success)
        MagicMock(returncode=0, stderr=""),  # actual patch p2
        MagicMock(returncode=0, stderr=""),  # cargo clean (rust dir)
        MagicMock(returncode=0, stderr=""),  # cargo clean (fuzz dir)
        MagicMock(returncode=0, stderr=""),  # cargo fuzz build
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust"
        src_dir = rust_dir / "src"
        fuzz_dir = rust_dir / "fuzz"
        src_dir.mkdir(parents=True)
        fuzz_dir.mkdir(parents=True)

        test_file = src_dir / "test.rs"
        test_file.write_text("pub fn test() { unimplemented!(); }")

        ctx = BuilderContext(project_root=temp_path)

        patch_content = """--- a/rust/src/test.rs
+++ b/rust/src/test.rs
@@ -1,1 +1,1 @@
-pub fn test() { unimplemented!(); }
+pub fn test() { println!("Hello"); }"""

        request = EditCodeRequest(path="rust/src/test.rs", patch=patch_content)
        result = edit_code(request, ctx=ctx)

        assert result.success is True
        
        # Verify we tried multiple strip levels
        patch_calls = [call for call in mock_subprocess.call_args_list if "patch" in str(call)]
        assert len(patch_calls) >= 4  # 3 dry-runs + 1 actual patch


@patch("portkit.implfuzz.subprocess.run")
def test_edit_code_git_apply_fallback(mock_subprocess):
    """Test edit_code falling back to git apply when patch fails."""
    # Mock patch failure but git apply success
    mock_subprocess.side_effect = [
        MagicMock(returncode=1, stderr="patch failed"),  # patch p0
        MagicMock(returncode=1, stderr="patch failed"),  # patch p1
        MagicMock(returncode=1, stderr="patch failed"),  # patch p2
        MagicMock(returncode=0, stderr=""),  # git apply (success)
        MagicMock(returncode=0, stderr=""),  # cargo clean (rust dir)
        MagicMock(returncode=0, stderr=""),  # cargo clean (fuzz dir)
        MagicMock(returncode=0, stderr=""),  # cargo fuzz build
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust"
        src_dir = rust_dir / "src"
        fuzz_dir = rust_dir / "fuzz"
        src_dir.mkdir(parents=True)
        fuzz_dir.mkdir(parents=True)

        test_file = src_dir / "test.rs"
        test_file.write_text("pub fn test() { unimplemented!(); }")

        ctx = BuilderContext(project_root=temp_path)

        patch_content = """--- a/rust/src/test.rs
+++ b/rust/src/test.rs
@@ -1,1 +1,1 @@
-pub fn test() { unimplemented!(); }
+pub fn test() { println!("Hello"); }"""

        request = EditCodeRequest(path="rust/src/test.rs", patch=patch_content)
        result = edit_code(request, ctx=ctx)

        assert result.success is True
        
        # Verify git apply was called
        git_calls = [call for call in mock_subprocess.call_args_list if "git" in str(call)]
        assert len(git_calls) == 1
        git_args = git_calls[0][0][0]
        assert "git" in git_args
        assert "apply" in git_args
        assert "--ignore-whitespace" in git_args
        assert "--3way" in git_args


@patch("portkit.implfuzz.compile_rust_project")
def test_edit_code_fuzz_directory(mock_compile):
    """Test edit_code works with files in rust/fuzz directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust"
        fuzz_dir = rust_dir / "fuzz" / "fuzz_targets"
        fuzz_dir.mkdir(parents=True)

        test_file = fuzz_dir / "test_fuzz.rs"
        test_file.write_text("#![no_main]\nuse libfuzzer_sys::fuzz_target;\n")

        ctx = BuilderContext(project_root=temp_path)

        patch_content = """--- test_fuzz.rs.orig
+++ test_fuzz.rs
@@ -1,2 +1,3 @@
 #![no_main]
 use libfuzzer_sys::fuzz_target;
+fuzz_target!(|data: &[u8]| {});"""

        request = EditCodeRequest(path="rust/fuzz/fuzz_targets/test_fuzz.rs", patch=patch_content)
        result = edit_code(request, ctx=ctx)

        assert result.success is True
        
        # Verify the file was actually patched
        updated_content = test_file.read_text()
        assert "fuzz_target!" in updated_content


@patch("portkit.implfuzz.compile_rust_project")
def test_edit_code_cleanup_temp_file(mock_compile):
    """Test edit_code cleans up temporary patch file even on failure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust"
        src_dir = rust_dir / "src"
        src_dir.mkdir(parents=True)

        test_file = src_dir / "test.rs"
        test_file.write_text("pub fn test() { unimplemented!(); }")

        ctx = BuilderContext(project_root=temp_path)

        # Use a malformed patch that will fail
        patch_content = """this is not a valid patch format"""

        request = EditCodeRequest(path="rust/src/test.rs", patch=patch_content)

        with pytest.raises(ValueError):
            edit_code(request, ctx=ctx)

        # Test passes if no exception is raised during cleanup


@patch("portkit.implfuzz.subprocess.run")
def test_edit_code_compilation_failure_after_patch(mock_subprocess):
    """Test edit_code when patch succeeds but compilation fails."""
    mock_subprocess.side_effect = [
        MagicMock(returncode=0, stderr=""),  # patch dry-run (success)
        MagicMock(returncode=0, stderr=""),  # actual patch (success)
        MagicMock(returncode=0, stderr=""),  # cargo clean (rust dir)
        MagicMock(returncode=0, stderr=""),  # cargo clean (fuzz dir)
        MagicMock(returncode=1, stderr="error: expected `;`"),  # cargo fuzz build (fail)
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust"
        src_dir = rust_dir / "src"
        fuzz_dir = rust_dir / "fuzz"
        src_dir.mkdir(parents=True)
        fuzz_dir.mkdir(parents=True)

        test_file = src_dir / "test.rs"
        test_file.write_text("pub fn test() { unimplemented!(); }")

        ctx = BuilderContext(project_root=temp_path)

        patch_content = """--- a/rust/src/test.rs
+++ b/rust/src/test.rs
@@ -1,1 +1,1 @@
-pub fn test() { unimplemented!(); }
+pub fn test() { invalid rust syntax }"""

        request = EditCodeRequest(path="rust/src/test.rs", patch=patch_content)

        # Should raise CompileError from compile_rust_project
        from portkit.implfuzz import CompileError
        with pytest.raises(CompileError):
            edit_code(request, ctx=ctx)


if __name__ == "__main__":
    pytest.main([__file__])
