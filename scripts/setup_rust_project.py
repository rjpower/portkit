#!/usr/bin/env python3

"""Configures a Rust project for a C library."""

from pathlib import Path

import click

from portkit.config import ProjectConfig


def format_dependencies(deps: dict[str, str]) -> str:
    """Format dependencies for Cargo.toml."""
    lines = []
    for name, version in deps.items():
        if "optional" in version or "{" in version:
            lines.append(f"{name} = {version}")
        else:
            lines.append(f'{name} = "{version}"')
    return "\n".join(lines)


def format_build_dependencies(deps: dict[str, str]) -> str:
    """Format build dependencies with optional flags for Cargo.toml."""
    lines = []
    for name, version in deps.items():
        lines.append(f'{name} = {{ version = "{version}", optional = true }}')
    return "\n".join(lines)


def generate_rerun_directives(c_source_path: str, c_files: list[str]) -> str:
    """Generate cargo:rerun-if-changed directives for C files."""
    if not c_files:
        return ""

    lines = []
    for c_file in c_files:
        lines.append(
            f'    println!("cargo:rerun-if-changed={c_source_path}/{c_file}");'
        )
    return "\n".join(lines)


def generate_compile_flags(flags: list[str]) -> str:
    """Generate compile flags for build.rs."""
    if not flags:
        return ""

    lines = []
    for flag in flags:
        lines.append(f'        .flag("{flag}")')
    return "\n".join(lines)


def generate_file_directives(c_source_path: str, c_files: list[str]) -> str:
    """Generate .file() directives for build.rs."""
    if not c_files:
        return ""

    lines = []
    for c_file in c_files:
        lines.append(f'        .file("{c_source_path}/{c_file}")')
    return "\n".join(lines)


def generate_include_directives(c_source_path: str, include_dirs: list[str]) -> str:
    """Generate .include() directives for build.rs."""
    if not include_dirs:
        return f'        .include("{c_source_path}")'

    lines = [f'        .include("{c_source_path}")']
    for include_dir in include_dirs:
        if include_dir != ".":  # Don't duplicate the main source path
            lines.append(f'        .include("{c_source_path}/{include_dir}")')
    return "\n".join(lines)


def create_main_cargo_toml(rust_root: Path, config: ProjectConfig) -> None:
    """Generate main Cargo.toml file."""
    
    cargo_toml_path = rust_root / "Cargo.toml"
    if cargo_toml_path.exists():
        return

    authors_str = str(config.authors) if config.authors else "[]"
    repo_line = f'repository = "{config.repository}"' if config.repository else ""

    cargo_toml = f"""[package]
name = "{config.library_name}"
version = "0.1.0"
edition = "2021"
authors = {authors_str}
description = "{config.description}"
license = "{config.license}"
{repo_line}

[features]
default = {list(config.build_dependencies.keys())}
pure-rust = []

[dependencies]
{format_dependencies(config.dependencies)}

[build-dependencies]
{format_build_dependencies(config.build_dependencies)}

[dev-dependencies]
{format_dependencies(config.dev_dependencies)}

[profile.dev]
debug = true
overflow-checks = true

[profile.release]
lto = true
codegen-units = 1

[profile.release-with-debug]
inherits = "release"
debug = true
"""

    cargo_toml_path.write_text(cargo_toml)


def create_fuzz_cargo_toml(fuzz_root: Path, config: ProjectConfig) -> None:
    """Generate fuzz Cargo.toml file."""
    
    fuzz_cargo_toml_path = fuzz_root / "Cargo.toml"
    if fuzz_cargo_toml_path.exists():
        return

    fuzz_cargo_toml = f"""[package]
name = "{config.library_name}-fuzz"
version = "0.0.0"
publish = false
edition = "2021"

[package.metadata]
cargo-fuzz = true

[features]
default = {list(config.build_dependencies.keys())}

[dependencies]
libfuzzer-sys = "0.4"
arbitrary = {{ version = "1", features = ["derive"] }}
{format_dependencies(config.dependencies)}

[build-dependencies]
{format_build_dependencies(config.build_dependencies)}

[dependencies.{config.library_name}]
path = ".."

[[bin]]
name = "fuzz_dummy"
path = "fuzz_targets/fuzz_dummy.rs"
test = false
doc = false
"""

    fuzz_cargo_toml_path.write_text(fuzz_cargo_toml)


def create_build_rs(rust_root: Path, config: ProjectConfig) -> None:
    """Generate build.rs file."""
    
    build_rs_path = rust_root / "build.rs"
    if build_rs_path.exists():
        return

    c_source_path = f"../{config.c_source_dir}"

    rerun_directives = generate_rerun_directives(c_source_path, config.c_files)
    compile_flags = generate_compile_flags(config.compile_flags)
    file_directives = generate_file_directives(c_source_path, config.c_files)
    include_directives = generate_include_directives(c_source_path, config.include_dirs)

    build_rs = f"""fn main() {{
    use cc::Build;
    use std::path::Path;
    use std::fs;
    
    // Add rerun-if-changed directives for C files
{rerun_directives}
    
    Build::new()
{compile_flags}
{file_directives}
{include_directives}
        .compile("{config.library_name}_c");
}}"""

    build_rs_path.write_text(build_rs)


def create_lib_rs(rust_src: Path, config: ProjectConfig) -> None:
    """Generate lib.rs file."""
    
    lib_rs_path = rust_src / "lib.rs"
    if not lib_rs_path.exists():
        lib_rs = """#![allow(non_snake_case)]
#![allow(dead_code)]
#![allow(unused_variables)]
#![allow(unused_imports)]

pub mod ffi;

// Re-export main functionality
pub use ffi::*;
"""
        lib_rs_path.write_text(lib_rs)

    # Create empty ffi.rs
    ffi_rs_path = rust_src / "ffi.rs"
    if not ffi_rs_path.exists():
        ffi_rs_path.write_text("// FFI bindings will be generated here\n")


def create_dummy_fuzz_test(fuzz_targets: Path, config: ProjectConfig) -> None:
    """Generate dummy fuzz test."""
    
    dummy_fuzz_path = fuzz_targets / "fuzz_dummy.rs"
    if dummy_fuzz_path.exists():
        return

    dummy_fuzz = """#![no_main]
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    // Dummy fuzz test - replace with actual implementation
    if data.len() > 0 {
        // Add your fuzz testing logic here
    }
});
"""

    dummy_fuzz_path.write_text(dummy_fuzz)


def setup_project(project_root: Path, config: ProjectConfig) -> None:
    """Create the Rust project structure based on config."""

    rust_root = config.rust_root_path()
    rust_src = config.rust_src_path()
    fuzz_root = config.rust_fuzz_root_path()
    fuzz_targets = config.rust_fuzz_targets_path()

    # Create directories
    rust_src.mkdir(parents=True, exist_ok=True)
    fuzz_targets.mkdir(parents=True, exist_ok=True)

    # Generate main Cargo.toml
    create_main_cargo_toml(rust_root, config)

    # Generate fuzz Cargo.toml
    create_fuzz_cargo_toml(fuzz_root, config)

    # Generate build.rs
    create_build_rs(rust_root, config)

    # Generate lib.rs
    create_lib_rs(rust_src, config)

    # Generate dummy fuzz test
    create_dummy_fuzz_test(fuzz_targets, config)

    # Save config for future use
    config.save_to_file(project_root / "portkit_config.json")


@click.command()
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    required=True,
)
@click.option("--library-name", help="Rust library name (defaults to project_name)")
@click.option(
    "--c-source-dir",
    help="C source directory relative to project root",
    required=True,
)
@click.option("--config-file", help="Path to existing config file")
def setup_rust_project(
    project_root: str,
    library_name: str | None = None,
    c_source_dir: str = "src",
    config_file: str | None = None,
):
    project_root = Path(project_root)
    assert project_root.exists(), f"Project root {project_root} does not exist"
    assert (
        project_root / c_source_dir
    ).exists(), f"C source directory {project_root / c_source_dir} does not exist"

    """Set up Rust project structure for C library porting."""
    project_name = project_root.name

    if config_file:
        config = ProjectConfig.load_from_file(Path(config_file))
    else:
        config = ProjectConfig(
            project_name=project_name,
            library_name=library_name or project_name,
            project_root=project_root,
            c_source_dir=c_source_dir,
        )

    setup_project(project_root, config)

    click.echo(f"✅ Created Rust project structure for {project_name}")
    click.echo(f"📁 Project root: {project_root}")
    click.echo(f"⚙️  Configuration saved to: {project_root}/portkit_config.json")


if __name__ == "__main__":
    setup_rust_project()
