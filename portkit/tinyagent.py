#!/usr/bin/env python3

import glob
import json
import re
import subprocess
import sys
import traceback
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, cast

import litellm
from pydantic import BaseModel, Field

from portkit.console import Console
from portkit.interrupt import InterruptSignal
from portkit.patch import DiffFencedPatcher
from portkit.sourcemap import SourceMap, SymbolInfo

DEFAULT_FUZZ_TIMEOUT = 10
# MODEL = "gemini/gemini-2.5-flash-preview-05-20"
# MODEL = "anthropic/claude-sonnet-4-20250514"
DEFAULT_MODEL = "gemini/gemini-2.5-pro-preview-06-05"
MAX_LLM_CALLS = 25


class ToolContext(Protocol):
    console: Console  # Our custom Console, not Rich's
    project_root: Path
    source_map: SourceMap
    read_files: set[str]
    has_mutations: bool
    processed_symbols: set[str]
    failed_symbols: set[str]
    interrupt_handler: Any  # InterruptHandler from implfuzz


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


class ToolCallFunction(BaseModel):
    name: str | None = None
    arguments: str = ""


class ToolCall(BaseModel):
    id: str | None = None
    type: str | None = None
    function: ToolCallFunction = Field(default_factory=ToolCallFunction)


class ToolHandler:
    """Handle tool registration and dispatch with argument validation."""

    def __init__(self):
        self._tools: dict[str, tuple[Callable, type[BaseModel], bool]] = {}
        self._context: Any = None

    def set_context(self, context: Any):
        """Set the builder context for tool execution."""
        self._context = context

    def register(self, function: Callable | None = None, *, mutating: bool = False):
        """Register a tool with its function and argument model."""

        def decorator(func):
            name = func.__name__
            import inspect

            sig = inspect.signature(func)
            result_model = sig.return_annotation
            # must be empty or a BaseModel
            if result_model != inspect.Parameter.empty and not issubclass(
                result_model, BaseModel
            ):
                raise ValueError(f"Return type {result_model} is not a BaseModel")

            arg_model = sig.parameters["args"].annotation
            if not issubclass(arg_model, BaseModel):
                raise ValueError(f"Argument type {arg_model} is not a BaseModel")

            self._tools[name] = (func, arg_model, mutating)
            return func

        if function is None:
            return decorator
        return decorator(function)

    def get_tools_spec(self) -> list[dict[str, Any]]:
        """Get litellm function specs for all registered tools."""
        specs = []
        for tool_name, (function, arg_model, _) in self._tools.items():
            # Use function docstring as description if available
            description = function.__doc__ or f"Execute {tool_name}"
            description = description.strip()

            specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": description,
                        "parameters": arg_model.model_json_schema(),
                    },
                }
            )
        return specs

    def run(self, tool_name: str, args_json: str, tool_call_id: str) -> dict[str, Any]:
        """Run a tool call with JSON argument parsing and return result message."""
        try:
            if tool_name not in self._tools:
                raise ValueError(f"Unknown tool: {tool_name}")
            if self._context is None:
                raise ValueError("No context set on ToolHandler")

            function, arg_model, is_mutating = self._tools[tool_name]
            args = arg_model.model_validate_json(args_json)
            self._context.console.print(f"[blue]Calling {tool_name} with args: {args}[/blue]")  # type: ignore

            if is_mutating:
                self._context.has_mutations = True

            result = function(args, ctx=self._context)

            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result.model_dump_json(),
            }
        except Exception as e:
            traceback.print_exc()
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps({"error": str(e), "type": type(e).__name__}),
            }


async def call_with_tools(
    messages: list[dict[str, Any]],
    tools: ToolHandler,
    model: str,
    project_root: Path | None = None,
    *,
    ctx: ToolContext,
) -> list[dict[str, Any]]:
    """Stream completion with function calling support."""

    # Log the completion request
    if project_root:
        timestamp = datetime.now().isoformat().replace(":", "_")
        logs_dir = project_root / "logs" / "litellm"
        logs_dir.mkdir(parents=True, exist_ok=True)

        log_data = {
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "messages": messages,
            "tools": tools.get_tools_spec(),
            "stream": True,
        }

        log_file = logs_dir / f"{timestamp}.json"
        with open(log_file, "w") as f:
            json.dump(log_data, f, indent=2)

        ctx.console.print(f"[dim]Logged completion request to {log_file}[/dim]")

    response = await litellm.acompletion(
        model=model,
        messages=messages,
        tools=tools.get_tools_spec(),
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

        if (
            hasattr(chunk.choices[0].delta, "thinking_blocks")
            and chunk.choices[0].delta.thinking_blocks is not None
        ):
            for block in chunk.choices[0].delta.thinking_blocks:
                if block["type"] == "thinking":
                    print(block["thinking"], end="", flush=True)  # type: ignore
        if chunk.choices[0].delta.content is not None:
            content = chunk.choices[0].delta.content
            content_parts.append(content)
            sys.stdout.write(content)
            sys.stdout.flush()
        if chunk.choices[0].delta.tool_calls:
            for tool_call_delta in chunk.choices[0].delta.tool_calls:
                index = tool_call_delta.index
                if index not in tool_calls_by_index:
                    tool_calls_by_index[index] = ToolCall(
                        id=tool_call_delta.id,
                        type=tool_call_delta.type,
                        function=ToolCallFunction(),
                    )

                tool_call = tool_calls_by_index[index]

                # Accumulate function arguments
                if tool_call_delta.function and tool_call_delta.function.arguments:
                    tool_call.function.arguments += tool_call_delta.function.arguments

                # Update name if provided
                if tool_call_delta.function and tool_call_delta.function.name:
                    tool_call.function.name = tool_call_delta.function.name
        if hasattr(chunk, "usage") and chunk.usage is not None:  # type: ignore
            usage_data = chunk.usage  # type: ignore

    # Log token usage and cost information
    if usage_data:
        prompt_tokens = getattr(usage_data, "prompt_tokens", 0)
        completion_tokens = getattr(usage_data, "completion_tokens", 0)
        total_tokens = getattr(usage_data, "total_tokens", 0)
        cost = litellm.completion_cost(completion_response=chunk)  # type: ignore
        if hasattr(tools._context, "running_cost"):
            tools._context.running_cost += cost
            ctx.console.print(
                f"[dim]Token usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens} Call cost: ${cost:.4f} Running cost: ${tools._context.running_cost:.4f}[/dim]"
            )
        else:
            ctx.console.print(
                f"[dim]Token usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens} Call cost: ${cost:.4f}[/dim]"
            )

    assistant_message = {"role": "assistant", "content": "".join(content_parts)}

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

            tool_name = tool_call.function.name
            args_json = tool_call.function.arguments

            result_message = tools.run(tool_name, args_json, tool_call.id)
            messages.append(result_message)

    return messages


class CompletionProtocol(Protocol):
    def __call__(self, initial: bool) -> TaskStatus: ...


async def call_with_retry(
    messages: list[dict[str, Any]],
    tools: ToolHandler,
    completion_fn: CompletionProtocol,
    model: str = DEFAULT_MODEL,
    project_root: Path | None = None,
    max_llm_calls: int = 25,
    *,
    ctx: ToolContext,
) -> list[dict[str, Any]]:
    """Stream completion with retry using TASK COMPLETE detection."""

    if tools._context:
        tools._context.reset_read_files()

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

        # Call LLM with interrupt support
        try:
            messages = await call_with_tools(
                messages, tools, model, project_root, ctx=ctx
            )
        except Exception as e:
            # Check if this is an InterruptSignal
            if e.__class__.__name__ == "InterruptSignal":
                user_message = getattr(e, "user_message", "")
                if user_message:
                    messages.append({"role": "user", "content": user_message})
                    # Recheck status after user input
                    status = _check_status(initial=False)
                    if not status.is_done():
                        messages.append(
                            {"role": "user", "content": status.get_feedback()}
                        )
                continue
            else:
                # Re-raise other exceptions
                raise

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


class CompileError(Exception):
    stderr: str

    def __init__(self, stderr: str):
        self.stderr = stderr
        super().__init__("Compilation failed")

    def __str__(self):
        return f"Compilation failed: {self.stderr}"


def compile_rust_project(project_dir: Path, *, ctx: ToolContext) -> None:
    ctx.console.print(
        f"[yellow]Compiling rust project {project_dir}...[/yellow]", end=""
    )
    result = subprocess.run(
        ["cargo", "fuzz", "build"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    ctx.console.print("[green]done[/green]")
    if result.returncode != 0:
        ctx.console.print(f"[red]Compilation failed:[/red] {result.stderr}")
        raise CompileError(result.stderr)


class RunFuzzTestRequest(BaseModel):
    target: str
    timeout: int = DEFAULT_FUZZ_TIMEOUT
    runs: int = -1


class FuzzTestResult(BaseModel):
    success: bool


class ReadFileResult(BaseModel):
    files: dict[str, str]  # path -> content mapping


class ReadFileRequest(BaseModel):
    paths: list[str]  # multiple file paths


class WriteFileRequest(BaseModel):
    path: str
    content: str


class WriteFileResult(BaseModel):
    success: bool


class AppendFileRequest(BaseModel):
    path: str
    content: str


class AppendFileResult(BaseModel):
    success: bool


class EditCodeRequest(BaseModel):
    patch: str


class ListFilesRequest(BaseModel):
    directory: str = "."
    extensions: list[str] = ["c", "h", "rs"]


class ListFilesResult(BaseModel):
    files: list[str]


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


class SymbolStatusRequest(BaseModel):
    symbol_names: list[str]


class SymbolStatus(BaseModel):
    symbol_name: str
    ffi_path: str | None
    rust_src_path: str | None
    rust_fuzz_path: str | None
    c_header_path: str | None
    c_source_path: str | None


class SymbolStatusResult(BaseModel):
    symbols: list[SymbolStatus]


def _update_lib_rs(ctx: ToolContext, path: Path):
    if "fuzz" in str(path):
        return

    lib_rs_path = ctx.project_root / "rust" / "src" / "lib.rs"

    # don't add lib.rs to lib.rs
    if path.stem == "lib":
        return

    # Create lib.rs if it doesn't exist
    if not lib_rs_path.exists():
        lib_rs_path.write_text("")

    lib_content = lib_rs_path.read_text()
    if path.stem not in lib_content:
        with open(lib_rs_path, "a") as f:
            f.write(f"\npub mod {path.stem};\n")


def _update_fuzz_cargo_toml(ctx: ToolContext, path: Path):
    if "fuzz_targets" not in str(path):
        return

    cargo_toml_path = ctx.project_root / "rust" / "fuzz" / "Cargo.toml"

    # Check if Cargo.toml exists, if not, skip updating it
    if not cargo_toml_path.exists():
        return

    cargo_content = cargo_toml_path.read_text()
    # Check if there's already a [[bin]] section with this exact name
    bin_pattern = f'name = "{path.stem}"'
    if bin_pattern not in cargo_content:
        with open(cargo_toml_path, "a") as f:
            f.write(
                f"""
[[bin]]
name = "{path.stem}"
path = "fuzz_targets/{path.stem}.rs"
test = false
doc = false
"""
            )


TOOL_HANDLER = ToolHandler()


@TOOL_HANDLER.register
def read_files(args: ReadFileRequest, *, ctx: ToolContext) -> ReadFileResult:
    """Read the contents of multiple files.
    read_files({ "paths": ["rust/src/foo.rs", "src/bar.c"] })
    """
    files = {}
    for path in args.paths:
        file_path = ctx.project_root / path
        if not file_path.exists():
            raise ValueError(f"File {path} does not exist")

        ctx.read_files.add(path)
        files[path] = file_path.read_text()

    return ReadFileResult(files=files)


@TOOL_HANDLER.register(mutating=True)
def replace_file(args: WriteFileRequest, *, ctx: ToolContext) -> WriteFileResult:
    """Write content to a file, replacing the existing content.

    The file path must be relative to the project root, e.g. "rust/src/foo.rs"
    The lib.rs imports and Cargo.toml will be updated to include the new file.
    """
    file_path = ctx.project_root / args.path
    # must be in the rust/src or rust/fuzz/
    if "rust/src" not in str(file_path) and "rust/fuzz" not in str(file_path):
        raise ValueError(
            f"File {args.path} must be in the rust/src or rust/fuzz directory"
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

    _update_lib_rs(ctx, file_path)
    _update_fuzz_cargo_toml(ctx, file_path)
    return WriteFileResult(success=True)


@TOOL_HANDLER.register(mutating=True)
def append_to_file(args: AppendFileRequest, *, ctx: ToolContext) -> AppendFileResult:
    """Append content to a file.

    The file path must be relative to the project root, e.g. "rust/src/foo.rs"

    The lib.rs imports and Cargo.toml will be updated to include the new file.
    """
    file_path = ctx.project_root / args.path
    # must be in the rust/src or rust/fuzz/
    if "rust/src" not in str(file_path) and "rust/fuzz" not in str(file_path):
        raise ValueError(
            f"File {args.path} must be in the rust/src or rust/fuzz directory"
        )

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "a") as f:
        f.write(args.content)

    _update_lib_rs(ctx, file_path)
    _update_fuzz_cargo_toml(ctx, file_path)
    return AppendFileResult(success=True)


class FuzzTestError(Exception):
    path: Path
    stderr: str

    def __init__(self, path: Path, stderr: str):
        self.path = path
        self.stderr = stderr

    def __str__(self):
        return f"Fuzz test failed: {self.path} {self.stderr}"


@TOOL_HANDLER.register
def run_fuzz_test(args: RunFuzzTestRequest, *, ctx: ToolContext) -> FuzzTestResult:
    """Run a fuzz test target with the specified timeout."""
    ctx.console.print(
        f"[yellow]Running fuzz test {args.target} -max_total_time={args.timeout} -runs={args.runs}...[/yellow]",
        end="",
    )
    fuzz_cmd = [
        "cargo",
        "fuzz",
        "run",
        args.target,
        "--",
        f"-max_total_time={args.timeout}",
    ]
    if args.runs != -1:
        fuzz_cmd.append(f"-runs={args.runs}")

    result = subprocess.run(
        fuzz_cmd,
        cwd=ctx.project_root / "rust",
        capture_output=True,
        text=True,
    )
    ctx.console.print("[green]done[/green]")

    # give the LLM a hint about the source of the fuzz test.
    source_path = (
        ctx.project_root / "rust" / "fuzz" / "fuzz_targets" / f"{args.target}.rs"
    )

    if result.returncode != 0:
        raise FuzzTestError(source_path, result.stderr)

    return FuzzTestResult(success=True)


class EditCodeResult(BaseModel):
    success: bool
    messages: list[str]


# use instructions from codex for patching


@TOOL_HANDLER.register(mutating=True)
def edit_code(args: EditCodeRequest, *, ctx: ToolContext) -> EditCodeResult:
    """Apply diff-fenced patches to source files.

    Patches use the aider diff-fenced format:

    path/to/file
    <<<<<<< SEARCH
    old content to search for
    =======
    new content to replace with
    >>>>>>> REPLACE

    Multiple search/replace blocks can be included in a single patch.
    Patches are applied in the order specified.
    Patches may be partially applied.
    Prefer to use multiple search/replace blocks over a single large patch.

    Example patch:
    ```
    rust/src/foo.rs
    <<<<<<< SEARCH
    fn old_function() {
        println!("old");
    }
    =======
    fn new_function() {
        println!("new");
    }
    >>>>>>> REPLACE

    rust/src/bar.rs
    <<<<<<< SEARCH
    let x = 1;
    =======
    let x = 2;
    >>>>>>> REPLACE
    ```
    """
    patcher = DiffFencedPatcher()
    result = EditCodeResult(success=True, messages=[])

    try:
        patch_matches = patcher.parse_patch(args.patch)
    except Exception as e:
        result.success = False
        result.messages.append(f"Failed to parse patch: {e}")
        return result

    for match in patch_matches:
        try:
            file_path = ctx.project_root / match.file_path
            ctx.console.print(f"[cyan]Applying patch to {file_path}[/cyan]")

            if "rust/src" not in str(file_path) and "rust/fuzz" not in str(file_path):
                raise ValueError(
                    f"File {match.file_path} must be in the rust/src or rust/fuzz directory"
                )

            if not file_path.exists():
                if match.search_text == "":
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(match.replace_text)
                else:
                    raise ValueError(f"File {match.file_path} does not exist")
            else:
                current_content = file_path.read_text()
                new_content = patcher.find_and_replace(
                    current_content, match.search_text, match.replace_text
                )
                file_path.write_text(new_content)

            _update_lib_rs(ctx, file_path)
            _update_fuzz_cargo_toml(ctx, file_path)
        except Exception as e:
            result.success = False
            result.messages.append(f"Patch failed to apply. \n<<<\n{e}\n>>>\n")

    if result.messages:
        result.success = False
        result.messages.append(
            "Some patches failed to apply. All other patches were applied successfully."
        )

    return result


@TOOL_HANDLER.register
def list_files(args: ListFilesRequest, *, ctx: ToolContext) -> ListFilesResult:
    """List files in the specified directory relative to project root."""
    search_dir = ctx.project_root / args.directory

    if not search_dir.exists():
        return ListFilesResult(files=[])

    files = []
    for ext in args.extensions:
        pattern = f"**/*.{ext}"
        matches = glob.glob(str(search_dir / pattern), recursive=True)
        # Convert to relative paths from the project root
        for match in matches:
            rel_path = Path(match).relative_to(ctx.project_root)
            files.append(str(rel_path))

    return ListFilesResult(files=sorted(files))


@TOOL_HANDLER.register
def search_files(args: SearchRequest, *, ctx: ToolContext) -> SearchResult:
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
        search_dir = ctx.project_root / search_spec.directory

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
                            path=str(file_path.relative_to(ctx.project_root)),
                            line=line_num,
                            context=context_text,
                        )
                    )
    return SearchResult(results=search_results)


@TOOL_HANDLER.register
def symbol_status(args: SymbolStatusRequest, *, ctx: ToolContext) -> SymbolStatusResult:
    """Lookup information for a symbol (e.g. as with an LSP).

    Returns:

    * FFI file
    * Rust source file
    * Rust fuzz test file
    * C header file
    * C source file

    If a file is not available, it is set to None.
    """
    # Create a new SourceMap for each symbol request, as we may have changed
    # the repo since the last request.
    source_map = SourceMap(ctx.project_root)
    source_map.parse_project()  # Parse to populate the symbols

    symbols = []
    for symbol_name in args.symbol_names:
        locations = source_map.lookup_symbol(symbol_name)
        symbols.append(
            SymbolStatus(
                symbol_name=symbol_name,
                ffi_path=locations.ffi_path,
                rust_src_path=locations.rust_src_path,
                rust_fuzz_path=locations.rust_fuzz_path,
                c_header_path=locations.c_header_path,
                c_source_path=locations.c_source_path,
            )
        )

    return SymbolStatusResult(symbols=symbols)
