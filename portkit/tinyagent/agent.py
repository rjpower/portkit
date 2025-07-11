#!/usr/bin/env python3

import json
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, cast

import litellm
import litellm.types
import litellm.types.utils
from pydantic import BaseModel, Field

from portkit.interrupt import InterruptSignal

from portkit.tidyllm.library import FunctionLibrary
from portkit.tinyagent.context import PortKitContext

DEFAULT_MODEL = "gemini/gemini-2.5-pro"
MAX_LLM_CALLS = 25


class TaskStatusType(str, Enum):
    DONE = "DONE"
    INCOMPLETE = "INCOMPLETE"


class TaskStatus(BaseModel):
    status: TaskStatusType = TaskStatusType.DONE
    errors: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)

    def error(self, msg: str) -> None:
        """Add an error message and mark status as INCOMPLETE."""
        self.status = TaskStatusType.INCOMPLETE
        self.errors.append(msg)

    def diagnostic(self, msg: str) -> None:
        """Add a diagnostic message."""
        self.diagnostics.append(msg)

    def is_done(self) -> bool:
        """Check if task completed successfully."""
        return self.status == TaskStatusType.DONE

    def get_feedback(self) -> str:
        """Get formatted feedback for LLM."""
        if self.status == TaskStatusType.DONE:
            return "Progress: task completed successfully."
        else:
            errors_text = "\n".join(f"- {error}" for error in self.errors)
            diagnostics_text = "\n".join(
                f"- {diagnostic}" for diagnostic in self.diagnostics
            )
            return f"Progress: Task is not yet complete. The following issues were encountered:\n{errors_text}\n{diagnostics_text}"


class ToolCall(BaseModel):
    id: str = ""
    type: str = ""
    name: str = ""
    arguments: str = ""

async def call_with_tools(
    messages: list[dict[str, Any]],
    library: FunctionLibrary,
    model: str,
    *,
    ctx: PortKitContext,
) -> list[dict[str, Any]]:
    """Stream completion with function calling support."""

    # Log the completion request
    timestamp = datetime.now().isoformat().replace(":", "_")
    logs_dir = Path("logs/litellm")
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Get tools from the function library
    tools_spec = library.get_schemas()

    log_data = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "messages": messages,
        "tools": tools_spec,
        "stream": True,
    }

    log_file = logs_dir / f"{timestamp}.json"
    with open(log_file, "w") as f:
        json.dump(log_data, f, indent=2)

    ctx.console.print(f"[dim]Logged completion request to {log_file}[/dim]")

    response = await litellm.acompletion(
        model=model,
        messages=messages,
        tools=tools_spec,
        tool_choice="auto",
        stream=True,
        stream_options={"include_usage": True},
        reasoning_effort="low",
        max_tokens=8000,
    )

    content_parts = []
    tool_calls_by_index: dict[int, ToolCall] = {}
    usage_data = None

    async for chunk in cast(litellm.CustomStreamWrapper, response):
        # Check for interrupt on every chunk
        message = ctx.interrupt_handler.check_interrupt()
        if message is not None:
            raise InterruptSignal(message)

        choice = cast(litellm.types.utils.StreamingChoices, chunk.choices[0])

        if (
            hasattr(choice.delta, "thinking_blocks")
            and choice.delta.thinking_blocks is not None
        ):
            for block in choice.delta.thinking_blocks:
                if block["type"] == "thinking":
                    print(block["thinking"], end="", flush=True)  # type: ignore
        if choice.delta.content is not None:
            content = choice.delta.content
            content_parts.append(content)
            sys.stdout.write(content)
            sys.stdout.flush()
        if choice.delta.tool_calls:
            for tool_call_delta in choice.delta.tool_calls:
                index = tool_call_delta.index
                if index not in tool_calls_by_index:
                    tool_calls_by_index[index] = ToolCall(
                        id=tool_call_delta.id or "",
                        type=tool_call_delta.type or "",
                    )

                tool_call = tool_calls_by_index[index]

                # Accumulate function arguments
                if tool_call_delta.function and tool_call_delta.function.arguments:
                    tool_call.arguments += tool_call_delta.function.arguments

                # Update name if provided
                if tool_call_delta.function and tool_call_delta.function.name:
                    tool_call.name = tool_call_delta.function.name
        if hasattr(chunk, "usage") and chunk.usage is not None:  # type: ignore
            usage_data = chunk.usage  # type: ignore

    # Log token usage and cost information
    if usage_data:
        prompt_tokens = getattr(usage_data, "prompt_tokens", 0)
        completion_tokens = getattr(usage_data, "completion_tokens", 0)
        total_tokens = getattr(usage_data, "total_tokens", 0)
        cost = litellm.completion_cost(completion_response=chunk)  # type: ignore
        ctx.running_cost += cost
        ctx.console.print(
            f"[dim]Token usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens} Call cost: ${cost:.4f} Running cost: ${ctx.running_cost:.4f}[/dim]"
        )

    assistant_message: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(content_parts),
    }

    # Convert aggregated tool calls to list
    tool_calls = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index.keys())]

    if tool_calls:
        assistant_message["tool_calls"] = [
            tool_call.model_dump() for tool_call in tool_calls
        ]

    messages.append(assistant_message)

    if tool_calls:
        # Check for interrupt before tool execution
        message = ctx.interrupt_handler.check_interrupt()
        if message is not None:
            raise InterruptSignal(message)

        for tool_call in tool_calls:
            # Check for interrupt before each tool
            message = ctx.interrupt_handler.check_interrupt()
            if message is not None:
                raise InterruptSignal(message)

            tool_name = tool_call.name
            args_json = tool_call.arguments
            args = json.loads(args_json)

            result_message = library.call_with_tool_response(tool_name, args, tool_call.id)
            messages.append(result_message)

    return messages


class CompletionProtocol(Protocol):
    def __call__(self, initial: bool) -> TaskStatus: ...


async def call_with_retry(
    messages: list[dict[str, Any]],
    completion_fn: CompletionProtocol,
    model: str = DEFAULT_MODEL,
    max_llm_calls: int = 25,
    *,
    ctx: PortKitContext,
) -> list[dict[str, Any]]:
    """Stream completion with retry using TASK COMPLETE detection."""

    def get_portkit_tools():
        """Get all registered PortKit tools as FunctionDescription objects."""
        from pathlib import Path
        from portkit.tidyllm.discover import discover_tools_in_directory
        
        tools_dir = Path(__file__).parent.parent / "tools"
        return discover_tools_in_directory(
            tools_dir, 
            recursive=True,
        )

    library = FunctionLibrary(
        function_descriptions=get_portkit_tools(),
        context=ctx
    )
    ctx.read_files.clear()

    def _check_status(initial: bool) -> TaskStatus:
        try:
            return completion_fn(initial=initial)
        except Exception as e:
            status = TaskStatus()
            status.error(str(e))
            return status

    status = _check_status(initial=True)
    if status.is_done():
        return messages

    ctx.console.print(f"[yellow]Initial status: {status}[/yellow]")

    # add initial status to the messages
    messages.append(
        {"role": "user", "content": f"Initial status: {status.get_feedback()}"}
    )

    for attempt in range(max_llm_calls):
        ctx.console.print(
            f"[bold cyan]Editor call {attempt + 1} of {max_llm_calls}[/bold cyan]"
        )

        messages = await call_with_tools(messages, library, model=model, ctx=ctx)

        # Check if LLM signaled completion or gave up
        last_message = messages[-1] if messages else {}
        if last_message.get("role") == "assistant":
            content = last_message.get("content", "")
            if "TASK COMPLETE" in content:
                ctx.console.print("[green]Editor signaled task completion[/green]")
                # Run final verification
                status = _check_status(initial=False)
                if status.is_done():
                    return messages
                else:
                    messages.append({"role": "user", "content": status.get_feedback()})
                    continue
            elif "GIVE UP" in content:
                ctx.console.print(
                    "[red]Editor signaled it cannot proceed further[/red]"
                )
                raise Exception(f"Editor gave up: {content}")

    raise Exception("Editor failed to complete task after all attempts")
