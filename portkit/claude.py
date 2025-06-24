#!/usr/bin/env python3

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from portkit.sourcemap import SourceMap, Symbol

if TYPE_CHECKING:
    from portkit.config import ProjectConfig


def compile_project(config: "ProjectConfig") -> None:
    """Compile the Rust project using cargo fuzz build."""
    result = subprocess.run(
        ["cargo", "fuzz", "build"],
        cwd=config.rust_root_path(),
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
    symbol: Symbol, source_map: SourceMap, config: "ProjectConfig"
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
            config.project_root / locations.c_source_path, symbol.name
        )
    c_declaration = ""
    if locations.c_header_path:
        c_declaration = source_map.find_c_symbol_definition(
            config.project_root / locations.c_header_path, symbol.name
        )

    return f"""You are an expert C to Rust translator. Your task is to create:

1. A Rust implementation (identical struct or function to the original)
2. FFI bindings for the C version of the symbol
3. A fuzz test that compares C and Rust implementations

Symbol: {symbol.name}
Kind: {symbol.kind}

Project structure:
- C source is in {config.c_source_dir}/
- Rust project is in {config.rust_dir}/
- Rust source is in {config.rust_dir}/{config.rust_src_dir}/
- Rust fuzz tests are in {config.rust_dir}/{config.fuzz_dir}/{config.fuzz_targets_dir}/

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
5. C FFI implementations are in the {config.library_name}::ffi module
6. Rust implementations are in {config.library_name}::{rust_module}

Create:
1. Rust implementation stub in {config.rust_dir}/{config.rust_src_dir}/{rust_module}.rs
2. FFI binding in {config.rust_dir}/{config.rust_src_dir}/ffi.rs
3. Fuzz test in {config.rust_dir}/{config.fuzz_dir}/{config.fuzz_targets_dir}/fuzz_{symbol.name}.rs

<fuzzing>
{load_prompt("example_fuzz_test")}
</fuzzing>

<c_declaration>
{c_declaration}
</c_declaration>

<c_source>
{c_definition}
</c_source>
"""


async def port_symbol_claude(
    symbol: Symbol, *, source_map: SourceMap, config: "ProjectConfig"
) -> None:
    """Port a single symbol using Claude Code."""
    print(f"Processing {symbol.kind} {symbol.name} from {symbol.source_path or symbol.header_path}")
    print(f"Dependencies: {symbol.dependencies if symbol.dependencies else 'none'}")

    # Check if symbol is already fully ported
    locations = source_map.lookup_symbol(symbol.name)

    # Check if FFI binding exists
    ffi_exists = locations.ffi_path and source_map.find_ffi_binding_definition(
        config.project_root / locations.ffi_path, symbol.name
    )

    # Check if Rust implementation exists and is not a stub
    rust_impl_exists = False
    if locations.rust_src_path:
        rust_content = source_map.find_rust_symbol_definition(
            config.project_root / locations.rust_src_path, symbol.name
        )
        rust_impl_exists = rust_content and "unimplemented!()" not in rust_content

    # Check if fuzz test exists
    fuzz_exists = (
        locations.rust_fuzz_path and (config.project_root / locations.rust_fuzz_path).exists()
    )

    if ffi_exists and rust_impl_exists and fuzz_exists:
        print(f"Symbol {symbol.name} is already fully ported, skipping...")
        return

    print(f"\nGenerating stub, FFI, and fuzz test for {symbol.name}...")
    stub_fuzz_prompt = create_claude_fuzz_prompt(symbol, source_map, config)
    call_claude_code(stub_fuzz_prompt, config.project_root)
    print(f"Stub, FFI, and fuzz test generation completed for {symbol.name}")

    compile_project(config)
    print(f"\nSuccessfully processed {symbol.name}")
