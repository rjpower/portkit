#!/usr/bin/env python3

from pathlib import Path
from typing import Protocol

from rich.console import Console

from portkit.config import ProjectConfig
from portkit.interrupt import InterruptHandler
from portkit.sourcemap import SourceMap


class PortKitContext(Protocol):
    """Context protocol for PortKit-specific tools."""

    console: Console
    project_root: Path
    source_map: SourceMap
    read_files: set[str]
    interrupt_handler: InterruptHandler
    config: ProjectConfig
