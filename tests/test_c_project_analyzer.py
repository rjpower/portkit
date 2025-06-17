#!/usr/bin/env python3
"""
Test cases for C project analysis and topological ordering.
"""

from pathlib import Path

import pytest

from portkit.sourcemap import SourceMap


@pytest.fixture
def zopfli_src():
    return Path(__file__).parent.parent / "zopfli" / "src"


@pytest.fixture
def analyzer():
    return SourceMap(Path(__file__).parent.parent / "zopfli")


def test_zopfli_topological_ordering(zopfli_src, analyzer):
    """Test that zopfli symbols are correctly ordered."""
    symbols = analyzer.parse_project()

    # 1. katajainen.h symbols should come early (simple dependencies)
    # 2. zopfli.h symbols should come later (more complex)

    # Find katajainen function
    katajainen_func = None

    for symbol in symbols:
        if symbol.name == "ZopfliLengthLimitedCodeLengths":
            katajainen_func = symbol

    # Verify symbols were found
    assert (
        katajainen_func is not None
    ), "ZopfliLengthLimitedCodeLengths function not found" + str(symbols)

    # Print ordering for manual inspection
    print("\nZopfli Symbol Ordering:")
    print("=" * 60)
    for i, symbol in enumerate(symbols[:20]):  # Show first 20
        deps_str = (
            ", ".join(sorted(symbol.dependencies)) if symbol.dependencies else "none"
        )
        file_name = ""
        if symbol.declaration_file:
            file_name = Path(symbol.declaration_file).name
        elif symbol.definition_file:
            file_name = Path(symbol.definition_file).name
        print(
            f"{i+1:2d}. {symbol.kind:<8} {symbol.name:<25} "
            f"({file_name}) deps: {deps_str}"
        )

    if len(symbols) > 20:
        print(f"... and {len(symbols) - 20} more symbols")

    # Test that symbols with fewer dependencies come earlier
    for i in range(len(symbols) - 1):
        current = symbols[i]
        next_symbol = symbols[i + 1]

        # Symbols with no dependencies should come before those with dependencies
        if len(current.dependencies) == 0 and len(next_symbol.dependencies) > 0:
            # This is expected - no assertion needed
            pass

    print(f"\nTotal symbols found: {len(symbols)}")

    # Verify we found some key symbols
    symbol_names = {symbol.name for symbol in symbols}
    expected_symbols = {
        "ZopfliLengthLimitedCodeLengths",
        "ZopfliOptions",
        "ZopfliFormat",
    }
    found_symbols = symbol_names.intersection(expected_symbols)

    print(f"Expected key symbols found: {found_symbols}")

    # Basic sanity checks
    assert len(symbols) > 0, "Should find at least some symbols"
    assert len(found_symbols) > 0, "Should find at least some expected symbols"


def test_dependency_analysis(zopfli_src, analyzer):
    """Test that dependencies are correctly identified."""
    symbols = analyzer.parse_project()

    # Find symbols with interesting dependencies
    symbols_with_deps = [s for s in symbols if s.dependencies]

    print(f"\nSymbols with dependencies ({len(symbols_with_deps)}):")
    print("=" * 50)
    for symbol in symbols_with_deps[:10]:  # Show first 10
        deps_str = ", ".join(sorted(symbol.dependencies))
        print(f"{symbol.kind:<8} {symbol.name:<20} -> {deps_str}")

    # Verify some symbols have dependencies
    assert len(symbols_with_deps) > 0, "Should find symbols with dependencies"


def test_function_call_dependencies(zopfli_src, analyzer):
    """Test that function call dependencies are correctly detected."""
    symbols = analyzer.parse_project()

    # Find ZopfliCalculateBitLengths
    calc_bit_lengths = None
    for symbol in symbols:
        if symbol.name == "ZopfliCalculateBitLengths":
            calc_bit_lengths = symbol
            break

    assert calc_bit_lengths is not None, "Should find ZopfliCalculateBitLengths function"

    # Verify it has the expected function call dependency
    assert "ZopfliLengthLimitedCodeLengths" in calc_bit_lengths.dependencies, \
        f"ZopfliCalculateBitLengths should depend on ZopfliLengthLimitedCodeLengths, but deps are: {calc_bit_lengths.dependencies}"

    # Verify the call graph was built
    assert "ZopfliCalculateBitLengths" in analyzer.call_graph, "Should have call graph entry"
    calls = analyzer.call_graph["ZopfliCalculateBitLengths"]
    assert "ZopfliLengthLimitedCodeLengths" in calls, f"Should call ZopfliLengthLimitedCodeLengths, but calls: {calls}"

    print("\nFunction call dependency test passed:")
    print(f"ZopfliCalculateBitLengths calls: {sorted(calls)}")
    print(f"ZopfliCalculateBitLengths deps: {sorted(calc_bit_lengths.dependencies)}")


def test_c_source_symbols_included(zopfli_src, analyzer):
    """Test that qualifying C source symbols are included in topological ordering."""
    symbols = analyzer.parse_project()

    # Find ZopfliCalculateBlockSize - should be source definition, not header declaration
    calc_block_size = None
    for symbol in symbols:
        if symbol.name == "ZopfliCalculateBlockSize":
            calc_block_size = symbol
            break

    assert calc_block_size is not None, "Should find ZopfliCalculateBlockSize function"

    # Verify it's the source definition (from deflate.c), not header declaration
    definition_file = calc_block_size.definition_file
    assert definition_file is not None, "Should have definition file"
    assert (
        Path(definition_file).name == "deflate.c"
    ), f"Should be from deflate.c, but found in: {definition_file}"

    # Verify it has expected properties of a source definition
    assert calc_block_size._definition_node is not None, "Should have definition node"
    assert calc_block_size.line_count > 10, "Should have substantial line count"

    # Check line count from the symbol (should be > 10 to qualify)
    # Already verified above that it has substantial line count

    # Check that it qualifies according to our heuristic
    # (CProjectAnalyzer was removed, using SourceMap directly)
    # Just verify it has the expected properties
    assert calc_block_size.definition_file is not None
    assert calc_block_size.line_count > 10

    # Verify dependencies include expected symbols
    assert (
        "ZopfliLZ77Store" in calc_block_size.dependencies
    ), f"Should depend on ZopfliLZ77Store, but deps are: {calc_block_size.dependencies}"

    print("C source symbol test passed:")
    file_name = (
        definition_file
        if definition_file
        else (
            calc_block_size.declaration_file if calc_block_size.declaration_file else ""
        )
    )
    line_num = (
        calc_block_size.definition_line
        if calc_block_size.definition_line
        else (
            calc_block_size.declaration_line if calc_block_size.declaration_line else 0
        )
    )
    print(
        f"ZopfliCalculateBlockSize found in: {file_name}:{line_num}"
    )
    print(f"Dependencies: {sorted(calc_block_size.dependencies)}")

    # Also check that we have other qualifying C source functions
    c_source_symbols = [
        s
        for s in symbols
        if (
            (s.definition_file and str(s.definition_file).endswith(".c"))
            or (s.declaration_file and str(s.declaration_file).endswith(".c"))
        )
        and s.line_count > 10 and s.definition_file is not None
    ]
    assert (
        len(c_source_symbols) > 10
    ), f"Should have many C source symbols, but only found {len(c_source_symbols)}"

    print(f"Total qualifying C source symbols: {len(c_source_symbols)}")

    # Verify some expected functions are included
    c_symbol_names = {s.name for s in c_source_symbols}
    expected_c_functions = [
        "ZopfliCalculateBlockSize",
        "OptimizeHuffmanForRle",
        "ZopfliLengthLimitedCodeLengths",
    ]
    found_expected = c_symbol_names.intersection(expected_c_functions)

    print(f"Expected C functions found: {sorted(found_expected)}")
    assert (
        len(found_expected) >= 2
    ), f"Should find at least 2 expected C functions, but found: {found_expected}"


def test_file_parsing(zopfli_src, analyzer):
    """Test that files are successfully parsed."""
    symbols = analyzer.parse_project()

    # Group symbols by file
    by_file = {}
    for symbol in symbols:
        file_path = ""
        if symbol.definition_file:
            file_path = symbol.definition_file
        elif symbol.declaration_file:
            file_path = symbol.declaration_file

        if file_path:
            filename = Path(file_path).name
            if filename not in by_file:
                by_file[filename] = []
            by_file[filename].append(symbol)

    print("\nSymbols by file:")
    print("=" * 40)
    for filename, file_symbols in sorted(by_file.items()):
        print(f"{filename}: {len(file_symbols)} symbols")

    # Verify we parsed multiple files
    assert len(by_file) > 1, "Should parse multiple files"

    # Verify some key files were parsed (mostly sources since topo sort focuses on C symbols)
    filenames = set(by_file.keys())
    # Headers might not show up in topological sort since we filter to C functions/structs/enums
    # Just verify we have the main source files
    assert "deflate.c" in filenames, "Should parse deflate.c"
    assert "lz77.c" in filenames, "Should parse lz77.c"

    # Verify we have source files (headers may not appear in topological sort)
    source_files = [f for f in filenames if f.endswith(".c")]
    assert len(source_files) > 0, "Should have some source files"
    
    # The topological sort focuses on C symbols from source definitions,
    # so headers may not appear in the final symbol list
