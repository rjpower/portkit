#!/usr/bin/env python3

import tempfile
from pathlib import Path

import pytest

from .lib import AiderDiffPatcher, edit_code, PatchArgs
from portkit.config import ProjectConfig
from portkit.implfuzz import BuilderContext
from portkit.sourcemap import SourceMap


def create_test_context(project_root: Path) -> BuilderContext:
    """Helper function to create BuilderContext for tests."""
    config = ProjectConfig(project_name="test", library_name="test", project_root=project_root)
    return BuilderContext(
        project_root=project_root,
        config=config,
        source_map=SourceMap(project_root, config),
    )


def test_parse_single_patch():
    patch_text = """file.rs
<<<<<<< SEARCH
old content
=======
new content
>>>>>>> REPLACE"""

    patcher = AiderDiffPatcher()
    matches = patcher.parse_patches([patch_text])

    assert len(matches) == 1
    assert matches[0].file_path == "file.rs"
    assert matches[0].search_text == "old content"
    assert matches[0].replace_text == "new content"


def test_parse_multiple_patches():
    patch_text = """file1.rs
<<<<<<< SEARCH
content1
=======
replacement1
>>>>>>> REPLACE
file2.rs
<<<<<<< SEARCH
content2
=======
replacement2
>>>>>>> REPLACE"""

    patcher = AiderDiffPatcher()
    matches = patcher.parse_patches([patch_text])

    assert len(matches) == 2
    assert matches[0].file_path == "file1.rs"
    assert matches[1].file_path == "file2.rs"


def test_parse_invalid_format():
    patcher = AiderDiffPatcher()

    with pytest.raises(ValueError, match="Invalid aider diff-fenced format"):
        patcher.parse_patches(["invalid format"])


def test_normalize_whitespace():
    patcher = AiderDiffPatcher()

    text = "  line1  \n\n  line2   with   spaces  \n"
    normalized = patcher.normalize_whitespace(text)

    assert normalized == "line1\n\nline2 with spaces\n"


def test_apply_patch_success():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        test_file = temp_dir / "test.rs"
        test_file.write_text("pub fn hello() {\n    unimplemented!()\n}")

        patch_text = """test.rs
<<<<<<< SEARCH
pub fn hello() {
unimplemented!()
}
=======
pub fn hello() {
println!("Hello!");
}
>>>>>>> REPLACE"""

        patcher = AiderDiffPatcher()
        modified_files, errors = patcher.apply_patches([patch_text], temp_dir)

        assert len(modified_files) == 1
        assert modified_files[0] == test_file
        assert len(errors) == 0
        assert "println!" in test_file.read_text()


def test_apply_patch_file_not_found():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)

        patch_text = """nonexistent.rs
<<<<<<< SEARCH
content
=======
replacement
>>>>>>> REPLACE"""

        patcher = AiderDiffPatcher()
        modified_files, errors = patcher.apply_patches([patch_text], temp_dir)

        assert len(modified_files) == 0
        assert len(errors) == 1
        assert "does not exist" in errors[0]


def test_convenience_function():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        test_file = temp_dir / "test.rs"
        test_file.write_text("original content")

        patch_text = """test.rs
<<<<<<< SEARCH
original content
=======
new content
>>>>>>> REPLACE"""

        patcher = AiderDiffPatcher()
        modified_files, errors = patcher.apply_patches([patch_text], temp_dir)

        assert len(modified_files) == 1
        assert len(errors) == 0
        assert test_file.read_text() == "new content"


def test_multiline_content():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        test_file = temp_dir / "test.rs"
        test_file.write_text(
            """pub struct Test {
field1: i32,
field2: String,
}

impl Test {
pub fn new() ->  {
    unimplemented!()
}
}"""
        )

        patch_text = """test.rs
<<<<<<< SEARCH
impl Test {
pub fn new() ->  {
    unimplemented!()
}
}
=======
impl Test {
pub fn new() ->  {
    Test {
        field1: 0,
        field2: String::new(),
    }
}
}
>>>>>>> REPLACE"""

        patcher = AiderDiffPatcher()
        patcher.apply_patches([patch_text], temp_dir)
        content = test_file.read_text()

        assert "field1: 0" in content
        assert "field2: String::new()" in content
        assert "unimplemented!()" not in content


def test_empty_replace_block():
    """Test handling of empty replace blocks (removing content)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        test_file = temp_dir / "test.rs"
        test_file.write_text('fn main() {\n    println!("Hello");\n}')

        patch_text = """test.rs
<<<<<<< SEARCH
println!("Hello");
=======

>>>>>>> REPLACE"""

        patcher = AiderDiffPatcher()
        patcher.apply_patches([patch_text], temp_dir)
        content = test_file.read_text()

        assert "println!" not in content


def test_empty_blocks_edge_cases():
    """Test edge cases with empty blocks."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        test_file = temp_dir / "test.rs"

        # Test replacing entire file content with empty
        test_file.write_text("some content")
        patch_text = """test.rs
<<<<<<< SEARCH
some content
=======

>>>>>>> REPLACE"""

        patcher = AiderDiffPatcher()
        patcher.apply_patches([patch_text], temp_dir)
        content = test_file.read_text()

        assert content == ""

        # Test adding content to empty file
        test_file.write_text("")
        patch_text = """test.rs
<<<<<<< SEARCH

=======
new content
>>>>>>> REPLACE"""

        patcher.apply_patches([patch_text], temp_dir)
        content = test_file.read_text()

        assert content == "new content"


def test_normalize_whitespace_empty_string():
    """Test normalize_whitespace with empty strings."""
    patcher = AiderDiffPatcher()

    # Test empty string
    result = patcher.normalize_whitespace("")
    assert result == ""

    # Test string with only whitespace
    result = patcher.normalize_whitespace("   \n  \n   ")
    assert result == "\n\n"


# edit_code integration tests
def test_edit_code_success():
    """Test successful edit_code execution with patch."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust"
        src_dir = rust_dir / "src"
        src_dir.mkdir(parents=True)

        # Create initial Rust file
        test_file = src_dir / "test.rs"
        test_file.write_text("pub fn test() { unimplemented!(); }\n")

        ctx = create_test_context(temp_path)

        # Working patch format
        patch_content = """rust/src/test.rs
<<<<<<< SEARCH
pub fn test() { unimplemented!(); }
=======
pub fn test() { println!("Hello"); }
>>>>>>> REPLACE"""

        request = PatchArgs(patches=[patch_content])
        result = edit_code(request, ctx=ctx)

        assert result.success is True

        # Verify the file was actually patched
        updated_content = test_file.read_text()
        assert "println!" in updated_content
        assert "unimplemented!" not in updated_content


def test_edit_code_patch_failure():
    """Test edit_code handling patch application failure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust"
        src_dir = rust_dir / "src"
        src_dir.mkdir(parents=True)

        test_file = src_dir / "test.rs"
        test_file.write_text("pub fn test() { unimplemented!(); }")

        ctx = create_test_context(temp_path)

        # Create a malformed patch that will fail
        patch_content = """rust/src/test.rs
<<<<<<< SEARCH
this line does not exist in the file
=======
pub fn test() { println!("Hello"); }
>>>>>>> REPLACE"""

        request = PatchArgs(patches=[patch_content])
        result = edit_code(request, ctx=ctx)

        assert result.success is False
        assert len(result.messages) > 0


def test_edit_code_nonexistent_file():
    """Test edit_code with non-existent file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        ctx = create_test_context(Path(temp_dir))

        patch_content = """rust/src/nonexistent.rs
<<<<<<< SEARCH
old line
=======
new line
>>>>>>> REPLACE"""

        request = PatchArgs(patches=[patch_content])
        result = edit_code(request, ctx=ctx)

        assert result.success is False
        assert len(result.messages) > 0


def test_edit_code_invalid_path():
    """Test edit_code with invalid file path (not in rust directory)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create file outside rust directory
        test_file = temp_path / "test.rs"
        test_file.write_text("test content")

        ctx = create_test_context(temp_path)

        patch_content = """test.rs
<<<<<<< SEARCH
test content
=======
new content
>>>>>>> REPLACE"""

        request = PatchArgs(patches=[patch_content])
        result = edit_code(request, ctx=ctx)

        assert result.success is False
        assert len(result.messages) > 0


def test_edit_code_fuzz_directory():
    """Test edit_code works with files in rust/fuzz directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rust_dir = temp_path / "rust"
        fuzz_dir = rust_dir / "fuzz" / "fuzz_targets"
        fuzz_dir.mkdir(parents=True)

        test_file = fuzz_dir / "test_fuzz.rs"
        test_file.write_text("#![no_main]\nuse libfuzzer_sys::fuzz_target;\n")

        ctx = create_test_context(temp_path)

        patch_content = """rust/fuzz/fuzz_targets/test_fuzz.rs
<<<<<<< SEARCH
#![no_main]
use libfuzzer_sys::fuzz_target;
=======
#![no_main]
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {});
>>>>>>> REPLACE"""

        request = PatchArgs(patches=[patch_content])
        result = edit_code(request, ctx=ctx)

        assert result.success is True

        # Verify the file was actually patched
        updated_content = test_file.read_text()
        assert "fuzz_target!" in updated_content
