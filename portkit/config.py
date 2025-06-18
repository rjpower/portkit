#!/usr/bin/env python3

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    """Configuration for a C-to-Rust porting project."""
    
    # Project identification
    project_name: str
    library_name: str  # for cargo package names
    
    # Directory structure  
    c_source_dir: str = "src"  # relative to project root
    c_source_subdir: str | None = None  # e.g., "zopfli" for zopfli/src/zopfli
    rust_dir: str = "rust"
    rust_src_dir: str = "src" 
    fuzz_dir: str = "fuzz"
    fuzz_targets_dir: str = "fuzz_targets"
    
    # Build configuration
    build_dependencies: dict[str, str] = Field(default_factory=lambda: {"cc": "1.0", "glob": "0.3"})
    dependencies: dict[str, str] = Field(default_factory=lambda: {"libc": "0.2"})
    dev_dependencies: dict[str, str] = Field(default_factory=lambda: {
        "proptest": "1.0", 
        "criterion": "0.5", 
        "rand": "0.8"
    })
    
    # C compilation settings
    c_files: list[str] = Field(default_factory=list)  # List of C files to compile
    include_dirs: list[str] = Field(default_factory=list)  # Include directories
    compile_flags: list[str] = Field(default_factory=lambda: ["-Wno-unused-function"])
    
    # Metadata
    authors: list[str] = Field(default_factory=list)
    description: str = ""
    license: str = "Apache-2.0"
    repository: str | None = None

    def c_source_path(self, project_root: Path) -> Path:
        """Get the full path to C source directory."""
        path = project_root / self.c_source_dir
        if self.c_source_subdir:
            path = path / self.c_source_subdir
        return path

    def rust_root_path(self, project_root: Path) -> Path:
        """Get the full path to Rust project root."""
        return project_root / self.rust_dir

    def rust_src_path(self, project_root: Path) -> Path:
        """Get the full path to Rust source directory."""
        return project_root / self.rust_dir / self.rust_src_dir

    def rust_ffi_path(self, project_root: Path) -> Path:
        """Get the full path to FFI bindings file."""
        return self.rust_src_path(project_root) / "ffi.rs"

    def rust_fuzz_root_path(self, project_root: Path) -> Path:
        """Get the full path to fuzz test root directory."""
        return project_root / self.rust_dir / self.fuzz_dir

    def rust_fuzz_targets_path(self, project_root: Path) -> Path:
        """Get the full path to fuzz targets directory."""
        return self.rust_fuzz_root_path(project_root) / self.fuzz_targets_dir

    def rust_fuzz_path_for_symbol(self, project_root: Path, symbol_name: str) -> Path:
        """Get the full path to fuzz test for a specific symbol."""
        return self.rust_fuzz_targets_path(project_root) / f"fuzz_{symbol_name}.rs"

    def rust_src_path_for_symbol(self, project_root: Path, source_file: Path | None) -> Path:
        """Get the Rust source path for a symbol based on its original C source file."""
        if source_file:
            return self.rust_src_path(project_root) / f"{source_file.stem}.rs"
        else:
            return self.rust_src_path(project_root) / "lib.rs"

    @classmethod
    def load_from_file(cls, config_path: Path) -> "ProjectConfig":
        """Load configuration from a JSON file."""
        return cls.model_validate_json(config_path.read_text())

    def save_to_file(self, config_path: Path) -> None:
        """Save configuration to a JSON file."""
        config_path.write_text(self.model_dump_json(indent=2))

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