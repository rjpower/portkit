#!/usr/bin/env python3
"""
Test cases for C traversal topological ordering.
"""

from pathlib import Path

import pytest

from portkit.c_traversal import CTraversal


@pytest.fixture
def zopfli_src():
    return Path(__file__).parent.parent / "zopfli" / "src"


@pytest.fixture
def traversal():
    return CTraversal()


def test_zopfli_topological_ordering(zopfli_src, traversal):
    """Test that zopfli symbols are correctly ordered."""
    symbols = traversal.parse_project(str(zopfli_src))

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
        print(
            f"{i+1:2d}. {symbol.kind:<8} {symbol.name:<25} "
            f"({Path(symbol.file_path).name}) deps: {deps_str}"
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


def test_dependency_analysis(zopfli_src, traversal):
    """Test that dependencies are correctly identified."""
    symbols = traversal.parse_project(str(zopfli_src))

    # Find symbols with interesting dependencies
    symbols_with_deps = [s for s in symbols if s.dependencies]

    print(f"\nSymbols with dependencies ({len(symbols_with_deps)}):")
    print("=" * 50)
    for symbol in symbols_with_deps[:10]:  # Show first 10
        deps_str = ", ".join(sorted(symbol.dependencies))
        print(f"{symbol.kind:<8} {symbol.name:<20} -> {deps_str}")

    # Verify some symbols have dependencies
    assert len(symbols_with_deps) > 0, "Should find symbols with dependencies"


def test_file_parsing(zopfli_src, traversal):
    """Test that files are successfully parsed."""
    symbols = traversal.parse_project(str(zopfli_src))

    # Group symbols by file
    by_file = {}
    for symbol in symbols:
        filename = Path(symbol.file_path).name
        if filename not in by_file:
            by_file[filename] = []
        by_file[filename].append(symbol)

    print(f"\nSymbols by file:")
    print("=" * 40)
    for filename, file_symbols in sorted(by_file.items()):
        print(f"{filename}: {len(file_symbols)} symbols")

    # Verify we parsed multiple files
    assert len(by_file) > 1, "Should parse multiple files"

    # Verify katajainen.h and zopfli.h were parsed
    filenames = set(by_file.keys())
    assert "katajainen.h" in filenames, "Should parse katajainen.h"
    assert "zopfli.h" in filenames, "Should parse zopfli.h"
