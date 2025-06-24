#!/usr/bin/env python3

from pathlib import Path

from portkit.tidyllm import REGISTRY
from portkit.tidyllm import register as tool


def read_prompt(tool_dir: Path) -> str:
    """Read the prompt.md file for a tool."""
    prompt_file = tool_dir / "prompt.md"
    if prompt_file.exists():
        return prompt_file.read_text().strip()
    return ""


__all__ = ["tool", "read_prompt", "REGISTRY"]
