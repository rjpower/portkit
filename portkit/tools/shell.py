#!/usr/bin/env python3

import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from portkit.tidyllm.registry import register
from portkit.tools.common import LibContext


class ShellRequest(BaseModel):
    """Run a shell command in the project directory or subdirectory."""

    command: list[str] = Field(description="Command to run as list of arguments")
    cwd: str = Field(default=".", description="Working directory relative to project root")


class ShellResult(BaseModel):
    """Result of shell command execution."""

    stdout: str = Field(description="Standard output")
    stderr: str = Field(description="Standard error")
    returncode: int = Field(description="Exit code")
    command: list[str] = Field(description="Command that was executed")
    cwd: str = Field(description="Working directory used")


@register(doc="Run shell commands safely within the project directory")
def shell(args: ShellRequest, *, ctx: LibContext) -> ShellResult:
    """Execute shell commands with path validation."""

    # Resolve project root and target directory
    project_root = Path(ctx.config.project_root).resolve()
    target_cwd = (project_root / args.cwd).resolve()

    # Security check: ensure target directory is within project root
    try:
        target_cwd.relative_to(project_root)
    except ValueError as e:
        raise ValueError(
            f"Working directory {target_cwd} is outside project root {project_root}"
        ) from e

    # Ensure target directory exists
    if not target_cwd.exists():
        raise FileNotFoundError(f"Working directory {target_cwd} does not exist")

    # Execute command
    try:
        result = subprocess.run(
            args.command,
            cwd=target_cwd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        return ShellResult(
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            command=args.command,
            cwd=str(target_cwd),
        )

    except subprocess.TimeoutExpired as e:
        raise TimeoutError(f"Command {args.command} timed out after 5 minutes") from e
    except Exception as e:
        raise RuntimeError(f"Failed to execute command {args.command}: {e}") from e
