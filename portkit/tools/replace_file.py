#!/usr/bin/env python3


from typing import Protocol

from pydantic import BaseModel

from portkit.config import ProjectConfig
from portkit.tidyllm import register
from portkit.tools.common import update_fuzz_cargo_toml, update_lib_rs


class ReplaceFileContext(Protocol):
    config: ProjectConfig
    read_files: set[str]


class WriteFileRequest(BaseModel):
    path: str
    content: str


class WriteFileResult(BaseModel):
    success: bool


@register()
def replace_file(args: WriteFileRequest, *, ctx: ReplaceFileContext) -> WriteFileResult:
    """Write content to a file, replacing the existing content.

    The file path must be relative to the project root, e.g. "rust/src/foo.rs"
    The lib.rs imports and Cargo.toml will be automatically updated to include the new file.
    """
    file_path = ctx.config.project_root / args.path
    # must be in the rust/src or rust/fuzz/
    rust_src_path = str(ctx.config.rust_src_path())
    rust_fuzz_path = str(ctx.config.rust_fuzz_root_path())
    if rust_src_path not in str(file_path) and rust_fuzz_path not in str(file_path):
        raise ValueError(
            f"File {args.path} must be in the {ctx.config.rust_src_dir} or {ctx.config.fuzz_dir} directory"
        )

    # Check if file was read first, unless it doesn't exist yet
    if file_path.exists() and args.path not in ctx.read_files:
        raise ValueError(
            f"File {args.path} already exists. Read it first before writing to it. After reading the file you may issue write/append/edit calls."
        )

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(args.content)

    # Writing a new file counts as reading it
    ctx.read_files.add(args.path)

    update_lib_rs(ctx, file_path)
    update_fuzz_cargo_toml(ctx, file_path)
    return WriteFileResult(success=True)


if __name__ == "__main__":
    from portkit.tidyllm import cli_main

    cli_main(replace_file)
