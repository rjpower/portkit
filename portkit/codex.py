#!/usr/bin/env python3

import tempfile
from pathlib import Path
from typing import Any, Protocol

from rich.console import Console


class ToolContext(Protocol):
    console: Console
    project_root: Path


class CompletionProtocol(Protocol):
    def __call__(self, initial: bool): ...


async def call_with_codex_retry(
    messages: list[dict[str, Any]],
    completion_fn,
    project_root: Path,
    max_attempts: int = 3,
    *,
    ctx: ToolContext,
) -> list[dict[str, Any]]:
    """Call Codex with retry and completion checking."""

    def _check_status(initial: bool):
        try:
            return completion_fn(initial=initial)
        except Exception as e:
            from portkit.tinyagent.agent import TaskStatus

            status = TaskStatus()
            status.error(str(e))
            return status

    status = _check_status(initial=True)
    if status.is_done():
        return messages

    ctx.console.print(f"[yellow]Initial status: {status}[/yellow]")
    messages.append(
        {"role": "user", "content": f"Initial status: {status.get_feedback()}"}
    )

    for attempt in range(max_attempts):
        ctx.console.print(f"[bold cyan]Codex attempt {attempt + 1} of {max_attempts}[/bold cyan]")

        messages = await call_with_codex(messages, project_root, ctx=ctx)

        # Check completion status
        last_message = messages[-1] if messages else {}
        if last_message.get("role") == "assistant":
            content = last_message.get("content", "")
            if "TASK COMPLETE" in content:
                ctx.console.print("[green]Codex signaled task completion[/green]")
                status = _check_status(initial=False)
                if status.is_done():
                    return messages
                else:
                    messages.append({"role": "user", "content": status.get_feedback()})
                    continue
            elif "GIVE UP" in content:
                ctx.console.print("[red]Codex signaled it cannot proceed further[/red]")
                raise Exception(f"Codex gave up: {content}")

        # Check status after this attempt
        status = _check_status(initial=False)
        if status.is_done():
            return messages
        elif attempt < max_attempts - 1:
            messages.append({"role": "user", "content": status.get_feedback()})

    raise Exception("Codex failed to complete task after all attempts")


async def call_with_codex(
    messages: list[dict[str, Any]],
    project_root: Path,
    *,
    ctx: ToolContext,
) -> list[dict[str, Any]]:
    """Stream completion using Codex CLI editor."""
    ctx.console.print("[bold blue]Using Codex CLI editor...[/bold blue]")

    # Convert messages to a prompt for Codex
    prompt_parts = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Handle structured content (like system messages with multiple parts)
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    prompt_parts.append(f"{role.title()}: {part.get('text', '')}")
        elif role == "system":
            prompt_parts.append(f"System: {content}")
        elif role == "user":
            prompt_parts.append(f"User: {content}")
        elif role == "assistant":
            prompt_parts.append(f"Assistant: {content}")

    full_prompt = "\n\n".join(prompt_parts)

    # Write prompt to temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(full_prompt)
        prompt_file = f.name

    try:
        # Run Codex CLI
        ctx.console.print("[yellow]Running Codex CLI with prompt...[/yellow]")
        import subprocess
        result = subprocess.run(
            ["codex", "--approval-mode", "auto-edit", f"@{prompt_file}"],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        
        # Since we're not using interrupts for codex, just use the result directly

        if result.returncode != 0:
            ctx.console.print(f"[red]Codex failed: {result.stderr}[/red]")
            raise Exception(f"Codex CLI failed: {result.stderr}")

        # Parse Codex response and convert back to messages format
        assistant_response = result.stdout.strip()
        ctx.console.print(f"[green]Codex response:[/green]\n{assistant_response}")

        # Add assistant message to conversation
        messages.append({"role": "assistant", "content": assistant_response})

        return messages

    finally:
        # Clean up temp file
        Path(prompt_file).unlink(missing_ok=True)
