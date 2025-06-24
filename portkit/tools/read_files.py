#!/usr/bin/env python3

from typing import Protocol

from pydantic import BaseModel

from portkit.config import ProjectConfig
from portkit.tidyllm import register


class ReadFilesContext(Protocol):
    config: ProjectConfig
    read_files: set[str]


class ReadFileResult(BaseModel):
    files: dict[str, str]  # path -> content mapping


class ReadFileRequest(BaseModel):
    paths: list[str]  # multiple file paths


@register()
def read_files(args: ReadFileRequest, *, ctx: ReadFilesContext) -> ReadFileResult:
    """Read the contents of multiple files.

    Args:
        paths: List of file paths relative to project root

    Returns:
        Dictionary mapping file paths to their contents

    Example:
        read_files({ "paths": ["rust/src/foo.rs", "src/bar.c"] })
    """
    files = {}
    for path in args.paths:
        file_path = ctx.config.project_root / path
        if not file_path.exists():
            raise ValueError(f"File {path} does not exist")

        ctx.read_files.add(path)
        files[path] = file_path.read_text()

    return ReadFileResult(files=files)


if __name__ == "__main__":
    from portkit.tidyllm import cli_main

    cli_main(read_files)
