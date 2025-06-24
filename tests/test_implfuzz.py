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

from portkit.config import ProjectConfig
from portkit.implfuzz import BuilderContext, generate_unified_prompt
from portkit.sourcemap import SourceMap, Symbol
from portkit.tinyagent.agent import (
    TaskStatus,
    TaskStatusType,
)
from portkit.tidyllm.library import FunctionLibrary
from portkit.tools.read_files import ReadFileRequest, read_files
from portkit.tools.replace_file import WriteFileRequest, replace_file
from portkit.tools.search_files import SearchRequest, SearchSpec, search_files
# edit_code tests moved to portkit/tools/patch/test.py


def get_portkit_tools():
    """Get all registered PortKit tools as FunctionDescription objects."""
    from pathlib import Path
    from portkit.tidyllm.discover import discover_tools_in_directory
    
    tools_dir = Path(__file__).parent.parent / "portkit" / "tools"
    return discover_tools_in_directory(
        tools_dir, 
        recursive=True,
    )


def create_test_context(project_root: Path) -> BuilderContext:
    """Helper function to create BuilderContext for tests."""
    config = ProjectConfig(project_name="test", library_name="test", project_root=project_root)
    return BuilderContext(
        project_root=project_root,
        config=config,
        source_map=SourceMap(project_root, config),
    )


def test_tools_spec_generation():
    """Test that tool specs are generated correctly."""
    from portkit.tidyllm import REGISTRY  # noqa: F401
    from portkit.tools.shell import shell  # noqa: F401

    specs = REGISTRY.get_schemas()
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
        ctx = create_test_context(Path(temp_path).parent)

        request = ReadFileRequest(paths=[Path(temp_path).name])
        result = read_files(request, ctx=ctx)

        file_content = result.files[Path(temp_path).name]
        assert "/* Test header */" in file_content
        assert "int test_function(void);" in file_content
    finally:
        Path(temp_path).unlink()


def test_read_nonexistent_c_source_file():
    """Test reading a non-existent file raises appropriate error."""
    ctx = create_test_context(Path("/tmp"))
    request = ReadFileRequest(paths=["nonexistent.h"])

    with pytest.raises(ValueError):
        read_files(request, ctx=ctx)



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

        ctx = create_test_context(temp_path)

        request = WriteFileRequest(
            path="rust/fuzz/fuzz_targets/test_target.rs",
            content="#![no_main]\nuse libfuzzer_sys::fuzz_target;\nfuzz_target!(|data: &[u8]| {});",
        )
        result = replace_file(request, ctx=ctx)

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

        ctx = create_test_context(temp_path)

        request = WriteFileRequest(
            path="rust/fuzz/fuzz_targets/test_target.rs", content="test content"
        )
        result = replace_file(request, ctx=ctx)

        # Should return success without trying to compile
        assert result.success is True

        # Check Cargo.toml wasn't modified (no duplicate entries)
        cargo_content = fuzz_cargo_toml.read_text()
        assert cargo_content.count('name = "test_target"') == 1




def test_tool_execution_success():
    """Test successful tool execution through handler."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".h", delete=False) as f:
        f.write("test content")
        temp_path = f.name

    try:
        ctx = create_test_context(Path(temp_path).parent)
        
        library = FunctionLibrary(
            function_descriptions=get_portkit_tools(),
            context=ctx
        )

        args = {"paths": [Path(temp_path).name]}
        result = library.call_with_tool_response("read_files", args, "test_id")

        assert result["role"] == "tool"
        assert result["tool_call_id"] == "test_id"
        assert "test content" in result["content"]
    finally:
        Path(temp_path).unlink()


def test_tool_execution_error():
    """Test tool execution with error."""
    ctx = create_test_context(Path("/tmp"))
    
    library = FunctionLibrary(
        function_descriptions=get_portkit_tools(),
        context=ctx
    )

    args = {"paths": ["nonexistent.h"]}
    result = library.call_with_tool_response("read_files", args, "test_id")

    assert result["role"] == "tool"
    assert result["tool_call_id"] == "test_id"

    # Should contain error information
    content = json.loads(result["content"])
    assert "error" in content


def test_unknown_tool_error():
    """Test calling unknown tool."""
    ctx = create_test_context(Path("/tmp"))
    
    library = FunctionLibrary(
        function_descriptions=get_portkit_tools(),
        context=ctx
    )

    result = library.call_with_tool_response("unknown_tool", {}, "test_id")

    content = json.loads(result["content"])
    assert "error" in content
    assert "unknown_tool" in content["error"]


def test_context_creation():
    """Test that BuilderContext can be created with different paths."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        ctx = create_test_context(temp_path)

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
        test_h_file.write_text("extern int func();\nstruct TestStruct {\n    int value;\n};")

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
        test_h_file.write_text("struct TestStruct {\n    float value;\n    char* name;\n};")

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
                    assert "comment" in match.context.lower() or "printf" in match.context
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


def test_generate_unified_prompt_function_basic():
    """Test generate_unified_prompt with basic function parameters."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create the directory structure
        (temp_path / "src" / "zopfli").mkdir(parents=True)

        # Create test header file with symbol declaration
        test_header = temp_path / "src" / "zopfli" / "test.h"
        test_header.write_text("int test_function(int x);")

        # Create test source file with symbol definition
        test_source = temp_path / "src" / "zopfli" / "test.c"
        test_source.write_text("int test_function(int x) { return x + 1; }")

        ctx = create_test_context(temp_path)

        # Get symbols (parsing happens at SourceMap init)
        symbols = ctx.source_map.parse_project()

        # Find the parsed symbol or create one if not found
        parsed_symbol = None
        for s in symbols:
            if s.name == "test_function" and s.language == "c":
                parsed_symbol = s
                break

        if parsed_symbol:
            symbol = parsed_symbol
        else:
            # Create a Symbol object with relative paths as fallback
            symbol = Symbol(
                name="test_function",
                kind="function",
                language="c",
                signature="int test_function(int x)",
                declaration_file=test_header.relative_to(temp_path),
                declaration_line=1,
                definition_file=test_source.relative_to(temp_path),
                definition_line=1,
            )

        prompt = generate_unified_prompt(
            symbol=symbol,
            ctx=ctx,
        )

        # Check that basic prompt structure exists
        assert "Port this symbol: test_function" in prompt
        assert "Kind: function" in prompt
        assert "C Header: src/zopfli/test.h" in prompt
        assert "C Source: src/zopfli/test.c" in prompt
        # Check that basic structure includes references to file paths
        assert "test_function" in prompt
        assert "function" in prompt

        # Check C declaration and definition tags (updated)
        assert "<c_declaration>" in prompt
        assert "<c_definition>" in prompt
        assert "int test_function(int x) { return x + 1; }" in prompt
        assert "</c_declaration>" in prompt
        assert "</c_definition>" in prompt

        # Check that no Rust source or fuzz test tags appear since they're empty
        assert "<rust_symbol_definition>" not in prompt
        assert "<fuzz_test>" not in prompt

        # Check that processed symbols section appears but is empty
        assert "<processed_symbols>" in prompt


def test_generate_unified_prompt_struct_no_fuzz_test():
    """Test generate_unified_prompt with struct type (no fuzz test)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create the directory structure
        (temp_path / "src" / "zopfli").mkdir(parents=True)

        # Create test header file with struct definition
        test_header = temp_path / "src" / "zopfli" / "test.h"
        test_header.write_text("struct TestStruct { int x; int y; };")

        # Create test source file
        test_source = temp_path / "src" / "zopfli" / "test.c"
        test_source.write_text("// source file")

        ctx = create_test_context(temp_path)

        # Create a Symbol object with relative paths
        symbol = Symbol(
            name="TestStruct",
            kind="struct",
            language="c",
            signature="struct TestStruct { int x; int y; };",
            declaration_file=test_header.relative_to(temp_path),
            declaration_line=1,
        )

        prompt = generate_unified_prompt(
            symbol=symbol,
            ctx=ctx,
        )

        # Check that fuzz test content is not included when file doesn't exist
        assert "<fuzz_test>" not in prompt

        # Check C source is still included
        assert "struct TestStruct { int x; int y; }" in prompt


def test_generate_unified_prompt_with_existing_rust_code():
    """Test generate_unified_prompt with existing Rust source content."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create the directory structure
        (temp_path / "src" / "zopfli").mkdir(parents=True)
        (temp_path / "rust" / "src").mkdir(parents=True)

        # Create test header file with symbol definition
        test_header = temp_path / "src" / "zopfli" / "test.h"
        test_header.write_text("int test_function(int x) { return x + 1; }")

        # Create Rust source file with existing content
        rust_src = temp_path / "rust" / "src" / "test.rs"
        rust_src.write_text("pub fn test_function(x: i32) -> i32 { unimplemented!() }")

        ctx = create_test_context(temp_path)

        # Create a Symbol object
        symbol = Symbol(
            name="test_function",
            kind="function",
            language="c",
            signature="int test_function(int x)",
            declaration_file=test_header,
            declaration_line=1,
        )

        prompt = generate_unified_prompt(
            symbol=symbol,
            ctx=ctx,
        )

        # Check that Rust source is included with tags
        assert "<rust_symbol_definition>" in prompt
        assert "pub fn test_function(x: i32) -> i32 { unimplemented!() }" in prompt
        assert "</rust_symbol_definition>" in prompt


def test_generate_unified_prompt_with_existing_fuzz_test():
    """Test generate_unified_prompt with existing fuzz test content."""
    fuzz_content = """#![no_main]
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    // Existing fuzz test
});"""

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create the directory structure
        (temp_path / "src" / "zopfli").mkdir(parents=True)
        (temp_path / "rust" / "fuzz" / "fuzz_targets").mkdir(parents=True)

        # Create test header file with symbol definition
        test_header = temp_path / "src" / "zopfli" / "test.h"
        test_header.write_text("int test_function(int x) { return x + 1; }")

        # Create fuzz test file with existing content
        fuzz_test = temp_path / "rust" / "fuzz" / "fuzz_targets" / "fuzz_test_function.rs"
        fuzz_test.write_text(fuzz_content)

        ctx = create_test_context(temp_path)

        # Create a Symbol object
        symbol = Symbol(
            name="test_function",
            kind="function",
            language="c",
            signature="int test_function(int x)",
            declaration_file=test_header,
            declaration_line=1,
        )

        prompt = generate_unified_prompt(
            symbol=symbol,
            ctx=ctx,
        )

        # Check that fuzz test is included with tags
        assert "<fuzz_test>" in prompt
        assert "use libfuzzer_sys::fuzz_target;" in prompt
        assert "// Existing fuzz test" in prompt
        assert "</fuzz_test>" in prompt


def test_generate_unified_prompt_struct_with_fuzz_content_ignored():
    """Test that fuzz test content is included for struct types."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create the directory structure
        (temp_path / "src" / "zopfli").mkdir(parents=True)
        (temp_path / "rust" / "fuzz" / "fuzz_targets").mkdir(parents=True)

        # Create test header file with struct definition
        test_header = temp_path / "src" / "zopfli" / "test.h"
        test_header.write_text("struct TestStruct { int x; int y; };")

        # Create test source file
        test_source = temp_path / "src" / "zopfli" / "test.c"
        test_source.write_text("// source file")

        # Create fuzz test file that should be ignored for structs
        fuzz_test = temp_path / "rust" / "fuzz" / "fuzz_targets" / "fuzz_TestStruct.rs"
        fuzz_test.write_text("// This should be ignored for structs")

        ctx = create_test_context(temp_path)

        # Create a Symbol object
        symbol = Symbol(
            name="TestStruct",
            kind="struct",
            language="c",
            signature="struct TestStruct { int x; int y; };",
            declaration_file=test_header.relative_to(temp_path),
            declaration_line=1,
            definition_file=test_source.relative_to(temp_path),
            definition_line=1,
        )

        prompt = generate_unified_prompt(
            symbol=symbol,
            ctx=ctx,
        )

        # Check that fuzz test content is included for structs
        assert "<fuzz_test>" in prompt
        assert "This should be ignored for structs" in prompt


def test_generate_unified_prompt_typedef_no_fuzz_test():
    """Test generate_unified_prompt with typedef (no fuzz test)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create the directory structure
        (temp_path / "src" / "zopfli").mkdir(parents=True)

        # Create test header file with typedef definition
        test_header = temp_path / "src" / "zopfli" / "test.h"
        test_header.write_text("typedef struct { int x; int y; } TestType;")

        # Create test source file
        test_source = temp_path / "src" / "zopfli" / "test.c"
        test_source.write_text("// source file")

        ctx = create_test_context(temp_path)

        # Create a Symbol object
        symbol = Symbol(
            name="TestType",
            kind="typedef",
            language="c",
            signature="typedef struct { int x; int y; } TestType;",
            declaration_file=test_header,
            declaration_line=1,
            definition_file=test_source,
            definition_line=1,
        )

        prompt = generate_unified_prompt(
            symbol=symbol,
            ctx=ctx,
        )

        # Check that fuzz test content is not included when file doesn't exist
        assert "<fuzz_test>" not in prompt

        # Check C source is still included
        print(prompt)
        assert "typedef struct { int x; int y; } TestType;" in prompt


def test_generate_unified_prompt_with_processed_symbols():
    """Test generate_unified_prompt includes processed symbols when they exist."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create the directory structure
        (temp_path / "src" / "zopfli").mkdir(parents=True)

        # Create test header file with symbol definition
        test_header = temp_path / "src" / "zopfli" / "test.h"
        test_header.write_text("int test_function(int x) { return x + 1; }")

        # Create test source file
        test_source = temp_path / "src" / "zopfli" / "test.c"
        test_source.write_text("int test_function(int x) { return x + 1; }")

        ctx = create_test_context(temp_path)

        # Add some processed symbols
        ctx.processed_symbols.add("symbol_a")
        ctx.processed_symbols.add("symbol_b")
        ctx.processed_symbols.add("symbol_c")

        # Create a Symbol object
        symbol = Symbol(
            name="test_function",
            kind="function",
            language="c",
            signature="int test_function(int x)",
            declaration_file=test_header,
            declaration_line=1,
            definition_file=test_source,
            definition_line=1,
        )

        prompt = generate_unified_prompt(
            symbol=symbol,
            ctx=ctx,
        )

        # Check that processed symbols section is included
        assert "<processed_symbols>" in prompt
        assert "</processed_symbols>" in prompt
        assert "The following symbols have already been successfully ported:" in prompt
        assert "symbol_a, symbol_b, symbol_c" in prompt


def test_generate_unified_prompt_empty_processed_symbols():
    """Test generate_unified_prompt includes processed symbols section even when empty."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create the directory structure
        (temp_path / "src" / "zopfli").mkdir(parents=True)

        # Create test header file with symbol definition
        test_header = temp_path / "src" / "zopfli" / "test.h"
        test_header.write_text("int test_function(int x) { return x + 1; }")

        # Create test source file
        test_source = temp_path / "src" / "zopfli" / "test.c"
        test_source.write_text("int test_function(int x) { return x + 1; }")

        ctx = create_test_context(temp_path)
        # Don't add any processed symbols (empty set)

        # Create a Symbol object
        symbol = Symbol(
            name="test_function",
            kind="function",
            language="c",
            signature="int test_function(int x)",
            declaration_file=test_header,
            declaration_line=1,
            definition_file=test_source,
            definition_line=1,
        )

        prompt = generate_unified_prompt(
            symbol=symbol,
            ctx=ctx,
        )

        # Check that processed symbols section is included but empty
        assert "<processed_symbols>" in prompt
        assert "The following symbols have already been successfully ported:" in prompt
        assert "symbol_a, symbol_b, symbol_c" not in prompt


def test_builder_context_processed_symbols():
    """Test BuilderContext processed_symbols functionality."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        ctx = create_test_context(temp_path)

        # Should start empty
        assert len(ctx.processed_symbols) == 0

        # Should be able to add symbols
        ctx.processed_symbols.add("symbol1")
        ctx.processed_symbols.add("symbol2")
        assert len(ctx.processed_symbols) == 2
        assert "symbol1" in ctx.processed_symbols
        assert "symbol2" in ctx.processed_symbols

        # Should handle duplicates
        ctx.processed_symbols.add("symbol1")
        assert len(ctx.processed_symbols) == 2  # Still 2, no duplicates


if __name__ == "__main__":
    pytest.main([__file__])
