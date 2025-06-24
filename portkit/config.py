#!/usr/bin/env python3

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    """Configuration for a C-to-Rust porting project."""

    # Project identification
    project_name: str
    library_name: str  # for cargo package names
    project_root: Path

    # Directory structure
    c_source_dir: str = "src"  # relative to project root
    rust_dir: str = "rust"
    rust_src_dir: str = "src"
    fuzz_dir: str = "fuzz"
    fuzz_targets_dir: str = "fuzz_targets"

    # Build configuration
    build_dependencies: dict[str, str] = Field(default_factory=lambda: {"cc": "1.0", "glob": "0.3"})
    dependencies: dict[str, str] = Field(default_factory=lambda: {"libc": "0.2"})
    dev_dependencies: dict[str, str] = Field(
        default_factory=lambda: {"proptest": "1.0", "criterion": "0.5", "rand": "0.8"}
    )

    # C compilation settings
    c_files: list[str] = Field(default_factory=list)  # List of C files to compile
    include_dirs: list[str] = Field(default_factory=list)  # Include directories
    compile_flags: list[str] = Field(default_factory=lambda: ["-Wno-unused-function"])

    # Metadata
    authors: list[str] = Field(default_factory=list)
    description: str = ""
    license: str = "Apache-2.0"
    repository: str | None = None

    def c_source_path(self) -> Path:
        """Get the full path to C source directory."""
        return self.project_root / self.c_source_dir

    def rust_root_path(self) -> Path:
        """Get the full path to Rust project root."""
        return self.project_root / self.rust_dir

    def rust_src_path(self) -> Path:
        """Get the full path to Rust source directory."""
        return self.rust_root_path() / self.rust_src_dir

    def rust_ffi_path(self) -> Path:
        """Get the full path to FFI bindings file."""
        return self.rust_src_path() / "ffi.rs"

    def rust_fuzz_root_path(self) -> Path:
        """Get the full path to fuzz test root directory."""
        return self.rust_root_path() / self.fuzz_dir

    def rust_fuzz_targets_path(self) -> Path:
        """Get the full path to fuzz targets directory."""
        return self.rust_fuzz_root_path() / self.fuzz_targets_dir

    def rust_fuzz_path_for_symbol(self, symbol_name: str) -> Path:
        """Get the full path to fuzz test for a specific symbol."""
        return self.rust_fuzz_targets_path() / f"fuzz_{symbol_name}.rs"

    def rust_src_path_for_symbol(self, source_file: Path | None) -> Path:
        """Get the Rust source path for a symbol based on its original C source file."""
        if source_file:
            return self.rust_src_path() / f"{source_file.stem}.rs"
        else:
            return self.rust_src_path() / "lib.rs"

    @classmethod
    def load_from_file(cls, config_path: Path) -> "ProjectConfig":
        """Load configuration from a JSON file."""
        args = json.loads(config_path.read_text())
        args["project_root"] = config_path.parent
        data = cls.model_validate(args)
        return data

    def save_to_file(self, config_path: Path) -> None:
        """Save configuration to a JSON file."""
        # Don't save project_root to the file since it's derived from the file location
        data = self.model_dump(exclude={"project_root"})
        config_path.write_text(json.dumps(data, indent=2))

    @classmethod
    def find_project_config(cls, start_path: Path) -> Optional["ProjectConfig"]:
        """Find project configuration by searching up the directory tree."""
        current = start_path.resolve()
        while current != current.parent:
            config_file = current / "portkit_config.json"
            if config_file.exists():
                return cls.load_from_file(config_file)
            current = current.parent
        return None
