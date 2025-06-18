#!/usr/bin/env python3
"""
Tests for the search_files functionality in implfuzz module.
"""

import tempfile
from pathlib import Path

import pytest

from portkit.config import ProjectConfig
from portkit.implfuzz import (
    BuilderContext,
)
from portkit.sourcemap import SourceMap
from portkit.tinyagent.agent import SearchRequest, SearchSpec, search_files


def create_test_context(project_root: Path) -> BuilderContext:
    """Helper function to create BuilderContext for tests."""
    config = ProjectConfig(project_name="test", library_name="test")
    return BuilderContext(
        project_root=project_root,
        config=config,
        source_map=SourceMap(project_root, config),
    )


def test_search_files_success():
    """Test successful search_files execution."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        src_dir = temp_path / "src"
        src_dir.mkdir()

        # Create test files with content to search
        test_c_file = src_dir / "test.c"
        test_c_file.write_text("int main() {\n    return 0;\n}")

        test_h_file = src_dir / "test.h"
        test_h_file.write_text(
            "extern int func();\nstruct TestStruct {\n    int value;\n};"
        )

        ctx = create_test_context(temp_path)

        # Test single search
        request = SearchRequest(
            searches=[SearchSpec(pattern="int", directory="src", context_lines=1)]
        )
        result = search_files(request, ctx=ctx)

        # Should find matches in both files
        assert isinstance(result.results, dict)
        assert len(result.results) > 0

        # Check that we found matches
        found_paths = set()
        for _, matches in result.results.items():
            for match in matches:
                found_paths.add(match.path)
                assert hasattr(match, "line")
                assert hasattr(match, "context")
                assert isinstance(match.line, int)
                assert "int" in match.context

        # Should find matches in both test files
        assert "src/test.c" in found_paths
        assert "src/test.h" in found_paths


def test_search_files_multiple_searches():
    """Test search_files with multiple search patterns."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        src_dir = temp_path / "src"
        src_dir.mkdir()

        # Create test files with different content
        test_c_file = src_dir / "test.c"
        test_c_file.write_text('int main() {\n    printf("Hello");\n    return 0;\n}')

        test_h_file = src_dir / "test.h"
        test_h_file.write_text(
            "struct TestStruct {\n    float value;\n    char* name;\n};"
        )

        ctx = create_test_context(temp_path)

        # Test multiple searches with different patterns
        request = SearchRequest(
            searches=[
                SearchSpec(pattern="int", directory="src", context_lines=1),
                SearchSpec(pattern="struct", directory="src", context_lines=0),
                SearchSpec(pattern="char\\*", directory="src", context_lines=2),
            ]
        )
        result = search_files(request, ctx=ctx)

        # Should find matches for all patterns
        assert isinstance(result.results, dict)
        assert len(result.results) >= 3  # At least one match for each pattern

        # Check that we found the expected content in matches
        all_contexts = []
        for _, matches in result.results.items():
            for match in matches:
                all_contexts.append(match.context)

        combined_context = " ".join(all_contexts)
        assert (
            "int" in combined_context
            or "struct" in combined_context
            or "char*" in combined_context
        )


def test_search_files_context_lines():
    """Test search_files with different context line settings."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        src_dir = temp_path / "src"
        src_dir.mkdir()

        # Create a file with multiple lines
        test_file = src_dir / "test.c"
        test_file.write_text(
            "// Header comment\n"
            "// Another comment\n"
            "int main() {\n"
            '    printf("Hello");\n'
            "    return 0;\n"
            "}\n"
            "// End comment"
        )

        ctx = create_test_context(temp_path)

        # Test with 0 context lines
        request = SearchRequest(
            searches=[SearchSpec(pattern="main", directory="src", context_lines=0)]
        )
        result = search_files(request, ctx=ctx)

        # Should find the match with minimal context
        assert len(result.results) > 0
        found_match = False
        for _, matches in result.results.items():
            for match in matches:
                if "main" in match.context:
                    found_match = True
                    # With 0 context lines, should only contain the matching line
                    assert match.context.count("\n") <= 1
        assert found_match

        # Test with more context lines
        request = SearchRequest(
            searches=[SearchSpec(pattern="main", directory="src", context_lines=2)]
        )
        result = search_files(request, ctx=ctx)

        # Should find the match with more context
        assert len(result.results) > 0
        found_match = False
        for _, matches in result.results.items():
            for match in matches:
                if "main" in match.context:
                    found_match = True
                    # Should include surrounding lines
                    assert (
                        "comment" in match.context.lower() or "printf" in match.context
                    )
        assert found_match


def test_search_files_regex_patterns():
    """Test search_files with regex patterns."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        src_dir = temp_path / "src"
        src_dir.mkdir()

        # Create test file with various patterns
        test_file = src_dir / "test.c"
        test_file.write_text(
            "void func1() {}\n"
            "int func2(int x) { return x; }\n"
            "float func3(float y) { return y * 2; }\n"
            'char* getString() { return "hello"; }\n'
        )

        ctx = create_test_context(temp_path)

        # Test regex pattern matching function definitions
        request = SearchRequest(
            searches=[SearchSpec(pattern=r"func\d+", directory="src", context_lines=0)]
        )
        result = search_files(request, ctx=ctx)

        # Should find multiple function matches
        assert len(result.results) > 0
        func_matches = 0
        for _, matches in result.results.items():
            for match in matches:
                if "func" in match.context:
                    func_matches += 1
        assert func_matches >= 3  # Should find func1, func2, func3


def test_search_files_no_matches():
    """Test search_files when no matches are found."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        src_dir = temp_path / "src"
        src_dir.mkdir()

        # Create test file without the search pattern
        test_file = src_dir / "test.c"
        test_file.write_text("int main() {\n    return 0;\n}")

        ctx = create_test_context(temp_path)

        # Search for pattern that doesn't exist
        request = SearchRequest(
            searches=[
                SearchSpec(
                    pattern="nonexistent_pattern", directory="src", context_lines=1
                )
            ]
        )
        result = search_files(request, ctx=ctx)

        # Should return empty results
        assert isinstance(result.results, dict)
        # Either empty dict or contains empty lists
        total_matches = sum(len(matches) for matches in result.results.values())
        assert total_matches == 0


def test_search_files_nonexistent_directory():
    """Test search_files with non-existent directory."""
    ctx = create_test_context(Path("/tmp"))

    request = SearchRequest(
        searches=[SearchSpec(pattern="test", directory="nonexistent")]
    )

    with pytest.raises(ValueError, match="Directory nonexistent does not exist"):
        search_files(request, ctx=ctx)


if __name__ == "__main__":
    pytest.main([__file__])
