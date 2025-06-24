#!/usr/bin/env python3

import glob
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from portkit.config import ProjectConfig
from portkit.tidyllm import register


class ListFilesContext(Protocol):
    config: ProjectConfig


class ListFilesRequest(BaseModel):
    directory: str = "."
    extensions: list[str] = ["c", "h", "rs"]


class ListFilesResult(BaseModel):
    files: list[str]


@register()
def list_files(args: ListFilesRequest, *, ctx: ListFilesContext) -> ListFilesResult:
    """List files in the specified directory relative to project root."""
    search_dir = ctx.config.project_root / args.directory

    if not search_dir.exists():
        return ListFilesResult(files=[])

    files = []
    for ext in args.extensions:
        pattern = f"**/*.{ext}"
        matches = glob.glob(str(search_dir / pattern), recursive=True)
        # Convert to relative paths from the project root
        for match in matches:
            rel_path = Path(match).relative_to(ctx.config.project_root)
            files.append(str(rel_path))

    return ListFilesResult(files=sorted(files))


if __name__ == "__main__":
    from portkit.tidyllm import cli_main

    cli_main(list_files)
