#!/usr/bin/env python3

import re
from bisect import bisect_left
from collections import defaultdict
from typing import Protocol

from pydantic import BaseModel

from portkit.config import ProjectConfig
from portkit.tidyllm import register


class SearchFilesContext(Protocol):
    config: ProjectConfig


class SearchSpec(BaseModel):
    pattern: str
    directory: str
    context_lines: int = 5


class SearchRequest(BaseModel):
    searches: list[SearchSpec]


class SearchItemResult(BaseModel):
    path: str
    line: int
    context: str


class SearchResult(BaseModel):
    results: dict[str, list[SearchItemResult]]


@register()
def search_files(args: SearchRequest, *, ctx: SearchFilesContext) -> SearchResult:
    """Search for multiple regular expression patterns in files using Python's re module.

    search_files({
        "searches": [
            { "pattern": "ZOPFLI_NUM_LL|ZOPFLI_MAX_MATCH", "directory": "rust/src", "context_lines": 3 },
            { "pattern": "struct.*Hash", "directory": "src", "context_lines": 2 }
        ]
    })
    """
    search_results = defaultdict(list)
    for search_spec in args.searches:
        search_dir = ctx.config.project_root / search_spec.directory

        if not search_dir.exists():
            raise ValueError(f"Directory {search_spec.directory} does not exist")

        pattern = re.compile(search_spec.pattern)

        for ext in ["c", "h", "rs"]:
            for file_path in search_dir.rglob(f"*.{ext}"):
                content = file_path.read_text()
                content_lines = content.split("\n")
                content_offsets = [0]  # Start of file
                offset = 0
                for line in content_lines[:-1]:  # All lines except the last
                    offset += len(line) + 1  # +1 for newline character
                    content_offsets.append(offset)

                for group in pattern.finditer(content):
                    # binary search for the line number
                    line_index = bisect_left(content_offsets, group.start())
                    if (
                        line_index < len(content_offsets)
                        and content_offsets[line_index] > group.start()
                    ):
                        line_index -= 1
                    line_num = line_index + 1  # Convert to 1-based line number
                    context_lines = content_lines[
                        max(0, line_index - search_spec.context_lines) : (
                            line_index + search_spec.context_lines + 1
                        )
                    ]
                    context_text = "\n".join(context_lines)
                    search_results[search_spec.pattern].append(
                        SearchItemResult(
                            path=str(file_path.relative_to(ctx.config.project_root)),
                            line=line_num,
                            context=context_text,
                        )
                    )
    return SearchResult(results=search_results)


if __name__ == "__main__":
    from portkit.tidyllm import cli_main

    cli_main(search_files)
