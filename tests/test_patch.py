#!/usr/bin/env python3

import tempfile
from pathlib import Path

import pytest

from portkit.tinyagent.patch import DiffFencedPatcher, apply_diff_fenced_patch


class TestDiffFencedPatcher:
    def test_parse_single_patch(self):
        patch_text = """file.rs
<<<<<<< SEARCH
old content
=======
new content
>>>>>>> REPLACE"""

        patcher = DiffFencedPatcher()
        matches = patcher.parse_patch(patch_text)

        assert len(matches) == 1
        assert matches[0].file_path == "file.rs"
        assert matches[0].search_text == "old content"
        assert matches[0].replace_text == "new content"

    def test_parse_multiple_patches(self):
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

        patcher = DiffFencedPatcher()
        matches = patcher.parse_patch(patch_text)

        assert len(matches) == 2
        assert matches[0].file_path == "file1.rs"
        assert matches[1].file_path == "file2.rs"

    def test_parse_invalid_format(self):
        patcher = DiffFencedPatcher()

        with pytest.raises(ValueError, match="Invalid diff-fenced format"):
            patcher.parse_patch("invalid format")

    def test_normalize_whitespace(self):
        patcher = DiffFencedPatcher()

        text = "  line1  \n\n  line2   with   spaces  \n"
        normalized = patcher.normalize_whitespace(text)

        assert normalized == "line1\n\nline2 with spaces\n"

    def test_exact_match_replacement(self):
        patcher = DiffFencedPatcher()
        content = "Hello world\nThis is a test"

        result = patcher.find_and_replace(content, "Hello world", "Goodbye world")
        assert result == "Goodbye world\nThis is a test"

    def test_whitespace_flexible_replacement(self):
        patcher = DiffFencedPatcher()
        content = "pub fn test() {\n    unimplemented!()\n}"
        search = "pub fn test() {\nunimplemented!()\n}"
        replace = "pub fn test() {\n    println!(\"Hello\");\n}"

        result = patcher.find_and_replace(content, search, replace)
        assert "println!" in result

    def test_search_not_found(self):
        patcher = DiffFencedPatcher()
        content = "Hello world"

        with pytest.raises(ValueError, match="Search text not found"):
            patcher.find_and_replace(content, "nonexistent", "replacement")

    def test_apply_patch_success(self):
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

            patcher = DiffFencedPatcher()
            modified_files = patcher.apply_patch(patch_text, temp_dir)

            assert len(modified_files) == 1
            assert modified_files[0] == test_file
            assert "println!" in test_file.read_text()

    def test_apply_patch_file_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)

            patch_text = """nonexistent.rs
<<<<<<< SEARCH
content
=======
replacement
>>>>>>> REPLACE"""

            patcher = DiffFencedPatcher()
            with pytest.raises(ValueError, match="does not exist"):
                patcher.apply_patch(patch_text, temp_dir)

    def test_convenience_function(self):
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

            modified_files = apply_diff_fenced_patch(patch_text, temp_dir)

            assert len(modified_files) == 1
            assert test_file.read_text() == "new content"

    def test_multiline_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            test_file = temp_dir / "test.rs"
            test_file.write_text("""pub struct Test {
    field1: i32,
    field2: String,
}

impl Test {
    pub fn new() -> Self {
        unimplemented!()
    }
}""")

            patch_text = """test.rs
<<<<<<< SEARCH
impl Test {
    pub fn new() -> Self {
        unimplemented!()
    }
}
=======
impl Test {
    pub fn new() -> Self {
        Test {
            field1: 0,
            field2: String::new(),
        }
    }
}
>>>>>>> REPLACE"""

            apply_diff_fenced_patch(patch_text, temp_dir)
            content = test_file.read_text()

            assert "field1: 0" in content
            assert "field2: String::new()" in content
            assert "unimplemented!()" not in content

    def test_empty_replace_block(self):
        """Test handling of empty replace blocks (removing content)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            test_file = temp_dir / "test.rs"
            test_file.write_text("fn main() {\n    println!(\"Hello\");\n}")

            patch_text = """test.rs
<<<<<<< SEARCH
    println!("Hello");
=======

>>>>>>> REPLACE"""

            patcher = DiffFencedPatcher()
            patcher.apply_patch(patch_text, temp_dir)
            content = test_file.read_text()

            assert "println!" not in content

    def test_empty_blocks_edge_cases(self):
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

            patcher = DiffFencedPatcher()
            patcher.apply_patch(patch_text, temp_dir)
            content = test_file.read_text()

            assert content == ""

            # Test adding content to empty file
            test_file.write_text("")
            patch_text = """test.rs
<<<<<<< SEARCH

=======
new content
>>>>>>> REPLACE"""

            patcher.apply_patch(patch_text, temp_dir)
            content = test_file.read_text()

            assert content == "new content"

    def test_real_patch_file(self):
        """Test applying the actual test.patch file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            # Create the directory structure and files
            rust_dir = temp_dir / "rust"
            src_dir = rust_dir / "src"
            fuzz_dir = rust_dir / "fuzz" / "fuzz_targets"
            src_dir.mkdir(parents=True)
            fuzz_dir.mkdir(parents=True)
            
            # Create deflate.rs with the original content
            deflate_file = src_dir / "deflate.rs"
            deflate_file.write_text("""fn some_function() {
    debug_assert!(expected_data_size == 0 || testlength == expected_data_size);
}""")
            
            # Create fuzz file with original content
            fuzz_file = fuzz_dir / "fuzz_AddLZ77Data.rs"
            fuzz_file.write_text("""#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    litlens: Vec<u16>,
    dists: Vec<u16>,
    expected_data_size: usize,
    ll_symbols: Vec<c_uint>,
    // other fields...
}

fn fuzz_target(input: FuzzInput) {
    let mut input = input;
    let size = input.litlens.len();
    
    if size == 0 || input.dists.len() != size {
        return;
    }
    let mut litlens = input.litlens;
    let mut dists = input.dists;
    input.ll_symbols.resize(ZOPFLI_NUM_LL, 0);
    
    input.ll_lengths.resize(ZOPFLI_NUM_LL, 0);
    input.d_symbols.resize(ZOPFLI_NUM_D, 0);
    input.d_lengths.resize(ZOPFLI_NUM_D, 0);

    for i in 0..size {
        if dists[i] == 0 {
            let litlen = litlens[i] as usize;
            if litlen >= 256 {
                return;
            }
            // Ensure length is > 0 so assert(ll_lengths[litlen] > 0) doesn't fire
            if input.ll_lengths[litlen] == 0 {
                input.ll_lengths[litlen] = 1;
            }
        } else {
            let litlen = litlens[i] as i32;
            if !(3..=288).contains(&litlen) {
                return;
            }
            let dist = dists[i] as i32;
            if !(1..=32768).contains(&dist) {
                return;
            }

            let lls = unsafe { ffi::ZopfliGetLengthSymbol(litlen) as usize };
            let ds = unsafe { ffi::ZopfliGetDistSymbol(dist) as usize };
            if lls >= ZOPFLI_NUM_LL || ds >= ZOPFLI_NUM_D {
                return;
            }
            // Ensure lengths are > 0 so asserts don't fire
            if input.ll_lengths[lls] == 0 {
                input.ll_lengths[lls] = 1;
            }
            if input.d_lengths[ds] == 0 {
                input.d_lengths[ds] = 1;
            }
        }
    }
    
    unsafe {
        zopfli::deflate::AddLZ77Data(
            &lz77,
            0,
            size,
            input.expected_data_size,
            input.ll_symbols.as_ptr(),
            // other params...
        );
    }
}""")
            
            # Read the actual patch file
            patch_file = Path("/Users/power/code/portkit/tests/test.patch")
            patch_content = patch_file.read_text()
            
            # Apply the patch
            modified_files = apply_diff_fenced_patch(patch_content, temp_dir)
            
            # Verify changes were applied
            assert len(modified_files) == 2
            
            # Check deflate.rs changes
            deflate_content = deflate_file.read_text()
            assert "assert!(expected_data_size == 0 || testlength == expected_data_size);" in deflate_content
            assert "debug_assert!" not in deflate_content
            
            # Check fuzz file changes
            fuzz_content = fuzz_file.read_text()
            assert "expected_data_size: usize," not in fuzz_content
            assert "expected_data_size," in fuzz_content  # local variable usage
            assert "expected_data_size += 1;" in fuzz_content
            assert "expected_data_size += litlen as usize;" in fuzz_content

    def test_normalize_whitespace_empty_string(self):
        """Test normalize_whitespace with empty strings."""
        patcher = DiffFencedPatcher()

        # Test empty string
        result = patcher.normalize_whitespace("")
        assert result == ""

        # Test string with only whitespace
        result = patcher.normalize_whitespace("   \n  \n   ")
        assert result == "\n\n"

    def test_find_replace_empty_search_direct(self):
        """Test find_and_replace with empty search text directly."""
        patcher = DiffFencedPatcher()

        # Empty search on empty content should work
        result = patcher.find_and_replace("", "", "replacement")
        assert result == "replacement"

        # Empty search on file with contents is an error
        with pytest.raises(ValueError, match="Empty search text"):
            patcher.find_and_replace("line1\n\nline2", "", "replacement")
