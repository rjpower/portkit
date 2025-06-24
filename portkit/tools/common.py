from pathlib import Path
from typing import Protocol

from portkit.config import ProjectConfig


class LibContext(Protocol):
    config: ProjectConfig


def update_lib_rs(ctx: LibContext, path: Path):
    if ctx.config.fuzz_dir in str(path):
        return

    lib_rs_path = ctx.config.rust_src_path() / "lib.rs"

    # don't add lib.rs to lib.rs
    if path.stem == "lib":
        return

    # Create lib.rs if it doesn't exist
    if not lib_rs_path.exists():
        lib_rs_path.write_text("")

    lib_content = lib_rs_path.read_text()
    if path.stem not in lib_content:
        with open(lib_rs_path, "a") as f:
            f.write(f"\npub mod {path.stem};\n")


def update_fuzz_cargo_toml(ctx: LibContext, path: Path):
    if ctx.config.fuzz_targets_dir not in str(path):
        return

    cargo_toml_path = ctx.config.rust_fuzz_root_path() / "Cargo.toml"

    # Check if Cargo.toml exists, if not, skip updating it
    if not cargo_toml_path.exists():
        return

    cargo_content = cargo_toml_path.read_text()
    # Check if there's already a [[bin]] section with this exact name
    bin_pattern = f'name = "{path.stem}"'
    if bin_pattern not in cargo_content:
        with open(cargo_toml_path, "a") as f:
            f.write(
                f"""
[[bin]]
name = "{path.stem}"
path = "{ctx.config.fuzz_targets_dir}/{path.stem}.rs"
test = false
doc = false
"""
            )
