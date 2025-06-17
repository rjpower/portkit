#!/usr/bin/env python3

import tempfile
from pathlib import Path

from portkit.implfuzz import BuilderContext
from portkit.sourcemap import SourceMap
from portkit.tinyagent.agent import SearchRequest, SearchSpec, search_files


def test_search_files_regex():
    """Test that search_files handles regex patterns correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create test files
        test_rs = tmpdir_path / "test.rs"
        test_rs.write_text("""
pub fn ZopfliGetLengthSymbol(l: i32) -> i32 {
    42
}

pub fn ZopfliGetDistSymbol(dist: i32) -> i32 {
    24
}

pub fn SomeOtherFunction() -> i32 {
    0
}
""")

        test_c = tmpdir_path / "test.c"
        test_c.write_text("""
int ZopfliGetLengthSymbol(int l) {
    return 42;
}

int ZopfliGetDistSymbol(int dist) {
    return 24;
}

int SomeOtherFunction() {
    return 0;
}
""")

        # Create BuilderContext
        ctx = BuilderContext(
            project_root=tmpdir_path,
            source_map=SourceMap(tmpdir_path),
        )

        # Test regex OR pattern
        request = SearchRequest(searches=[
            SearchSpec(
                pattern="ZopfliGetLengthSymbol|ZopfliGetDistSymbol",
                directory=".",
                context_lines=1
            )
        ])

        result = search_files(request, ctx=ctx)

        # Should find both functions in the results
        found_text = ""
        for _, matches in result.results.items():
            for match in matches:
                found_text += match.context

        assert "ZopfliGetLengthSymbol" in found_text
        assert "ZopfliGetDistSymbol" in found_text
        assert "SomeOtherFunction" not in found_text

        # Check that matches were found in both file types
        found_files = set()
        for _, matches in result.results.items():
            for match in matches:
                found_files.add(match.path)

        assert any("test.rs" in path for path in found_files)
        assert any("test.c" in path for path in found_files)


def test_search_files_basic_pattern():
    """Test that search_files still works with basic patterns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create test file
        test_rs = tmpdir_path / "test.rs"
        test_rs.write_text("""
pub fn simple_function() -> i32 {
    42
}
""")

        # Create BuilderContext
        ctx = BuilderContext(
            project_root=tmpdir_path,
            source_map=SourceMap(tmpdir_path),
        )

        # Test simple pattern
        request = SearchRequest(searches=[
            SearchSpec(
                pattern="simple_function",
                directory=".",
                context_lines=0
            )
        ])

        result = search_files(request, ctx=ctx)

        # Should find the function
        found_text = ""
        for _, matches in result.results.items():
            for match in matches:
                found_text += match.context + " " + match.path

        assert "simple_function" in found_text
        assert "test.rs" in found_text


def test_search_files_complex_regex():
    """Test that search_files handles more complex regex patterns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create test file
        test_rs = tmpdir_path / "test.rs"
        test_rs.write_text("""
pub fn func_one() -> i32 { 1 }
pub fn func_two() -> i32 { 2 }
pub fn func_three() -> i32 { 3 }
pub fn other_function() -> i32 { 0 }
""")

        # Create BuilderContext
        ctx = BuilderContext(
            project_root=tmpdir_path,
            source_map=SourceMap(tmpdir_path),
        )

        # Test regex pattern for func_* functions
        request = SearchRequest(searches=[
            SearchSpec(
                pattern="func_(one|two|three)",
                directory=".",
                context_lines=0
            )
        ])

        result = search_files(request, ctx=ctx)

        # Should find func_one, func_two, func_three but not other_function
        found_text = ""
        for _, matches in result.results.items():
            for match in matches:
                found_text += match.context

        assert "func_one" in found_text
        assert "func_two" in found_text
        assert "func_three" in found_text
        assert "other_function" not in found_text


if __name__ == "__main__":
    test_search_files_regex()
    test_search_files_basic_pattern()
    test_search_files_complex_regex()
    print("All tests passed!")
