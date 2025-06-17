#!/usr/bin/env python3

import subprocess
from pathlib import Path

from portkit.sourcemap import SourceMap, Symbol, SymbolInfo


def compile_project(project_root: Path) -> None:
    """Compile the Rust project using cargo fuzz build."""
    result = subprocess.run(
        ["cargo", "fuzz", "build"],
        cwd=project_root / "rust",
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Compilation failed: {result.stderr}")


def call_claude_code(prompt: str, working_dir: Path) -> None:
    """Call Claude Code as a Unix-style utility with the given prompt."""
    print(f"Calling Claude Code with prompt: {prompt}")
    claude = "/Users/power/.claude/local/claude"

    subprocess.run(
        [
            claude,
            "--allowedTools",
            "Bash(*) Edit(*) Glob Grep Read Write MultiEdit",
        ],
        input=prompt,
        cwd=working_dir,
        text=True,
        check=True,
    )


def create_claude_fuzz_prompt(
    symbol: Symbol, c_source: str, source_map: SourceMap, project_root: Path
) -> str:
    from portkit.implfuzz import load_prompt

    """Create a prompt for Claude Code to generate implementation,FFI, and fuzz test."""
    locations = source_map.lookup_symbol(symbol.name)

    # Determine the module name from locations
    rust_module = "unknown"
    if locations.rust_src_path:
        rust_module = Path(locations.rust_src_path).stem
    elif symbol.source_path:
        rust_module = symbol.source_path.stem
    elif symbol.header_path:
        rust_module = symbol.header_path.stem

    c_definition = ""
    if locations.c_source_path:
        c_definition = source_map.find_c_symbol_definition(
            project_root / locations.c_source_path, symbol.name
        )
    c_declaration = ""
    if locations.c_header_path:
        c_declaration = source_map.find_c_symbol_definition(
            project_root / locations.c_header_path, symbol.name
        )

    return f"""You are an expert C to Rust translator. Your task is to create:

1. A Rust implementation (identical struct or function to the original)
2. FFI bindings for the C version of the symbol
3. A fuzz test that compares C and Rust implementations

Symbol: {symbol.name}
Kind: {symbol.kind}
C Source: <symbol>
{c_source}
</symbol>

Project structure:
- C source is in src/
- Rust project is in rust/
- Rust source is in rust/src/
- Rust fuzz tests are in rust/fuzz/fuzz_targets/

Guidelines:
- For functions: Create implementation with correct signature and implementation
- For structs: Create identical layout with proper field types and padding
- For typedefs: Create equivalent Rust type alias
- Rust implementations should NOT be marked with `#[no_mangle]` or `#[export_name]`
- Always create FFI binding for the C version
- Use identical function and argument names as the C function
- Assume all ifdefs are set to defined when reading C code
- Use the same symbol names for Rust and C code

Fuzz test requirements:
1. Use libfuzzer_sys to generate random inputs
2. Call both C implementation (via FFI) and Rust implementation
3. Compare outputs and assert they are identical
4. Handle edge cases gracefully with clear assertion messages
5. C FFI implementations are in the zopfli::ffi module
6. Rust implementations are in zopfli::{rust_module}

Create:
1. Rust implementation stub in rust/src/{rust_module}.rs
2. FFI binding in rust/src/ffi.rs
3. Fuzz test in rust/fuzz/fuzz_targets/fuzz_{symbol.name}.rs

<fuzzing>
{load_prompt("example_fuzz_test")}
</fuzzing>
"""


def create_claude_impl_prompt(
    symbol: Symbol, c_source: str, source_map: SourceMap, project_root: Path
) -> str:
    """Create a prompt for Claude Code to generate the full implementation."""
    locations = source_map.lookup_symbol(symbol.name)

    # Determine the module name from locations
    rust_module = "unknown"
    if locations.rust_src_path:
        rust_module = Path(locations.rust_src_path).stem
    elif symbol.source_path:
        rust_module = symbol.source_path.stem
    elif symbol.header_path:
        rust_module = symbol.header_path.stem

    return f"""You are an expert C to Rust translator. Implement the following C symbol in Rust.

Symbol: {symbol.name}
Kind: {symbol.kind}
C Source: <symbol>
{c_source}
</symbol>

Requirements:
- Exactly match the C implementation's behavior
- Use idiomatic Rust while maintaining exact behavioral compatibility
- Replace the existing stub implementation
- All C dependencies have already been implemented in Rust

Project structure:
- There is an existing stub in rust/src/{rust_module}.rs
- Replace the stub with complete implementation
- Fuzz test exists at rust/fuzz/fuzz_targets/fuzz_{symbol.name}.rs

Guidelines:
- Assume all ifdefs are set to defined when reading C code
- Use the same symbol names for Rust and C code
- Don't switch to snake case
- Static functions in header files have been exported

Testing instructions:
- After implementing, run the fuzz test with: `cargo fuzz run fuzz_{symbol.name} -- -max_total_time=10`
- If the fuzz test fails, analyze the failure and fix the implementation
- Iterate until the fuzz test passes consistently
- The fuzz test compares your Rust implementation against the C version via FFI

Implement the Rust version of {symbol.name} and iterate until the fuzz test passes.
"""


async def port_symbol_claude(
    symbol: Symbol, c_source: str, *, project_root: Path, source_map: SourceMap
) -> None:
    """Port a single symbol using Claude Code."""
    print(
        f"Processing {symbol.kind} {symbol.name} from {symbol.source_path or symbol.header_path}"
    )
    print(f"Dependencies: {symbol.dependencies if symbol.dependencies else 'none'}")

    # Check if symbol is already fully ported
    locations = source_map.lookup_symbol(symbol.name)

    # Check if FFI binding exists
    ffi_exists = locations.ffi_path and source_map.find_ffi_binding_definition(
        project_root / locations.ffi_path, symbol.name
    )

    # Check if Rust implementation exists and is not a stub
    rust_impl_exists = False
    if locations.rust_src_path:
        rust_content = source_map.find_rust_symbol_definition(
            project_root / locations.rust_src_path, symbol.name
        )
        rust_impl_exists = rust_content and "unimplemented!()" not in rust_content

    # Check if fuzz test exists
    fuzz_exists = (
        locations.rust_fuzz_path and (project_root / locations.rust_fuzz_path).exists()
    )

    if ffi_exists and rust_impl_exists and fuzz_exists:
        print(f"Symbol {symbol.name} is already fully ported, skipping...")
        return

    if not ffi_exists or not rust_impl_exists or not fuzz_exists:
        print(f"\nGenerating stub, FFI, and fuzz test for {symbol.name}...")
        stub_fuzz_prompt = create_claude_fuzz_prompt(
            symbol, c_source, source_map, project_root
        )
        call_claude_code(stub_fuzz_prompt, project_root)
        print(f"Stub, FFI, and fuzz test generation completed for {symbol.name}")

        compile_project(project_root)

    # Refresh locations after stub generation
    locations = source_map.lookup_symbol(symbol.name)

    if symbol.kind != "struct" and locations.rust_src_path:
        # Check if implementation is still needed
        rust_content = source_map.find_rust_symbol_definition(
            project_root / locations.rust_src_path, symbol.name
        )
        if rust_content and "unimplemented!()" in rust_content:
            # Generate implementation with fuzz test iteration
            print(f"\nGenerating implementation with fuzz testing for {symbol.name}...")
            impl_prompt = create_claude_impl_prompt(
                symbol, c_source, source_map, project_root
            )
            call_claude_code(impl_prompt, project_root)
            print(f"Implementation with fuzz testing completed for {symbol.name}")

    print(f"\nSuccessfully processed {symbol.name}")
