#!/usr/bin/env python3
"""
Debug script to print the unified prompt for testing and inspection.
"""

from pathlib import Path

from portkit.implfuzz import BuilderContext, generate_unified_prompt
from portkit.sourcemap import SourceMap


def create_builder_ctx(project_root: Path) -> BuilderContext:
    ctx = BuilderContext(
        project_root=project_root, source_map=SourceMap(project_root=project_root)
    )
    ctx.processed_symbols.add("ZopfliOptions")
    ctx.processed_symbols.add("ZopfliDeflate")
    ctx.processed_symbols.add("ZopfliLZ77Store")
    ctx.processed_symbols.add("ZopfliInitOptions")

    return ctx


def main():
    """Generate and print a sample prompt."""
    print("=" * 80)
    print("PORTKIT PROMPT DEBUG SCRIPT")
    print("=" * 80)

    ctx = create_builder_ctx(Path("zopfli-gemini-pro"))

    # Generate prompt for a function
    print("\n1. FUNCTION PROMPT (with all content):")
    print("-" * 40)

    function_prompt = generate_unified_prompt(
        symbol=ctx.source_map.get_symbol("ZopfliCompress"),
        ctx=ctx,
    )
    print(function_prompt)

    print("\n" + "=" * 80)
    print("\n2. STRUCT PROMPT (no fuzz test):")
    print("-" * 40)

    # Generate prompt for a struct (should not include fuzz test)
    struct_prompt = generate_unified_prompt(
        symbol=ctx.source_map.get_symbol("ZopfliOptions"),
        ctx=ctx,
    )
    print(struct_prompt)

if __name__ == "__main__":
    main()
