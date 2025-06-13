#!/usr/bin/env python3

import asyncio
import glob
import json
import os
import subprocess
import sys
import tempfile
import traceback
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, cast

import litellm
from pydantic import BaseModel, Field

from portkit.c_traversal import CTraversal, Symbol
from portkit.checkpoint import SourceCheckpoint

MAX_ATTEMPTS = 10

COMMON_PROMPT = """You are an expert C to Rust translator.

You are in charge of porting a C library to Rust.
You produce idiomatic Rust code which behaves _identically_ to the C code.
Do not include license headers etc in the Rust code.
You always explain your tool calls and reasoning.
You may issue multiple tool calls per step.
Your progress will be evaluated after each step.

The project structure is as follows:

- C source is in src/
- Rust project is in rust/
- Rust source is in rust/src/
- Rust fuzz tests are written to rust/fuzz/fuzz_targets/

General guidelines:

- Assume all ifdefs are set to defined when reading C code.
- Always use the same symbol names for Rust and C code. Don't switch to snake case.
- Only port one symbol at a time.
"""

IMPLEMENT_PROMPT = f"""
{COMMON_PROMPT}
Your goal is to create a Rust implementation that:
- Exactly matches the C implementation's behavior
- Uses idiomatic Rust while maintaining exact behavioral compatibility

When you receive compilation errors or test failures, analyze them and fix the implementation accordingly.
"""

STUB_GENERATOR_PROMPT = f"""
{COMMON_PROMPT}

Your task is to:
- Create a Rust stub (unimplemented function or identical struct) 
- Create FFI bindings for the C version of the symbol

This will be used to generate a fuzz test which compares the Rust and C implementations.
The FFI must be complete and correct.

- For functions: Create stub with correct signature but `unimplemented!()` body
- For structs: Create identical layout with proper field types and padding
- For typedefs: Create equivalent Rust type alias

Always create a FFI binding for the C version of the symbol. e.g. a function or struct.
All dependent symbols have already been created for you.
Use identical function and argument names as the C function.
"""

CREATE_FUZZ_TEST_PROMPT = f"""
{COMMON_PROMPT}
Generate a cargo-fuzz fuzz test which exercises a given symbol.
Compare the output of the C and Rust implementations.

1. Uses libfuzzer_sys to generate random inputs
2. Calls both the C implementation (via FFI) and Rust implementation
3. Compare outputs and assert they are identical

Example fuzz test:
#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_int;

fuzz_target!(|data: &[u8]| {{
    let n = (data[0] as usize % 286) + 2; // Symbol count between 2 and 287 (DEFLATE uses up to 286)
    let maxbits = (data[1] % 15) as c_int + 1; // Bit length between 1 and 15
    
    let c_result = unsafe {{
        zopfli::ffi::SomeZopfliFunction(
            frequencies.as_ptr(),
            n as c_int,
            maxbits,
            c_bitlengths.as_mut_ptr(),
        )
    }};
    
    // Call Rust implementation
    let rust_result = zopfli::ffi::SomeZopfliFunction(
        &frequencies,
        n as usize,
        maxbits as i32,
        &mut rust_bitlengths,
    );
    
    // Compare results
    assert_eq!(c_result, rust_result as c_int, 
        "Return values differ: C={{}}, Rust={{}}", c_result, rust_result);
    
    if c_result == 0 && rust_result == 0 {{
        for i in 0..n {{
            assert_eq!(c_bitlengths[i], rust_bitlengths[i],
                "Bit lengths differ at index {{}}: C={{}}, Rust={{}}, freq={{}}",
                i, c_bitlengths[i], rust_bitlengths[i], frequencies[i]);
        }}
    }}
}});

The test should handle edge cases gracefully and provide clear assertion messages.
"""


DEFAULT_FUZZ_TIMEOUT = 60
MODEL = "gemini/gemini-2.5-flash-preview-05-20"


class TaskStatusType(str, Enum):
    DONE = "DONE"
    INCOMPLETE = "INCOMPLETE"


class TaskStatus(BaseModel):
    """Tracks the status of a completion task with structured error reporting."""

    status: TaskStatusType = TaskStatusType.DONE
    errors: list[str] = Field(default_factory=list)

    def error(self, msg: str) -> None:
        """Add an error message and mark status as INCOMPLETE."""
        self.status = TaskStatusType.INCOMPLETE
        self.errors.append(msg)

    def is_done(self) -> bool:
        """Check if task completed successfully."""
        return self.status == TaskStatusType.DONE

    def get_feedback(self) -> str:
        """Get formatted feedback for LLM."""
        if self.status == TaskStatusType.DONE:
            return "Progress: task completed successfully."
        else:
            errors_text = "\n".join(f"- {error}" for error in self.errors)
            return f"Progress: Task is not yet complete. The following issues were encountered:\n{errors_text}"


class BuilderContext(BaseModel):
    project_root: Path
    read_files: set[str] = Field(default_factory=set)

    def reset_read_files(self) -> None:
        """Reset the set of read files for a new LLM interaction."""
        self.read_files.clear()


class ToolHandler:
    """Handle tool registration and dispatch with argument validation."""

    def __init__(self):
        self._tools: dict[str, tuple[Callable, type[BaseModel]]] = {}
        self._context: BuilderContext | None = None

    def set_context(self, context: BuilderContext):
        """Set the builder context for tool execution."""
        self._context = context

    def register(self, function: Callable):
        """Register a tool with its function and argument model."""
        name = function.__name__
        import inspect

        sig = inspect.signature(function)
        result_model = sig.return_annotation
        # must be empty or a BaseModel
        if result_model != inspect.Parameter.empty and not issubclass(
            result_model, BaseModel
        ):
            raise ValueError(f"Return type {result_model} is not a BaseModel")

        arg_model = sig.parameters["args"].annotation
        if not issubclass(arg_model, BaseModel):
            raise ValueError(f"Argument type {arg_model} is not a BaseModel")

        print(f"Registering tool: {name} with model: {arg_model}")
        self._tools[name] = (function, arg_model)
        return function

    def get_tools_spec(self) -> list[dict[str, Any]]:
        """Get litellm function specs for all registered tools."""
        specs = []
        for tool_name, (function, arg_model) in self._tools.items():
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

            function, arg_model = self._tools[tool_name]
            args = arg_model.model_validate_json(args_json)
            print(f"Calling {tool_name} with args: {args}")
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


class CompileError(Exception):
    stderr: str

    def __init__(self, stderr: str):
        self.stderr = stderr
        super().__init__("Compilation failed")

    def __str__(self):
        return f"Compilation failed: {self.stderr}"


def compile_rust_project(project_dir: Path) -> None:
    print(f"Compiling rust project {project_dir}...", end="")
    result = subprocess.run(
        ["cargo", "fuzz", "build"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    print("done")
    if result.returncode != 0:
        raise CompileError(result.stderr)


class RunFuzzTestRequest(BaseModel):
    target: str
    timeout: int = DEFAULT_FUZZ_TIMEOUT


class FuzzTestResult(BaseModel):
    success: bool


class ReadFileResult(BaseModel):
    source: str


class ReadFileRequest(BaseModel):
    path: str


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
    path: str
    patch: str

class EditCodeResult(BaseModel):
    success: bool


class ListFilesRequest(BaseModel):
    directory: str = "."
    extensions: list[str] = ["c", "h", "rs"]


class ListFilesResult(BaseModel):
    files: list[str]


class SearchRequest(BaseModel):
    pattern: str
    directory: str = "."
    context_lines: int = 3


class SearchResult(BaseModel):
    match_output: str


handler = ToolHandler()

def _update_lib_rs(ctx: BuilderContext, path: Path):
    if "fuzz" in str(path):
        return

    lib_rs_path = ctx.project_root / "rust" / "src" / "lib.rs"
    if path.stem not in lib_rs_path.read_text():
        with open(lib_rs_path, "a") as f:
            f.write(f"\npub mod {path.stem};\n")


def _update_fuzz_cargo_toml(ctx: BuilderContext, path: Path):
    if "fuzz_targets" not in str(path):
        return

    cargo_toml_path = ctx.project_root / "rust" / "fuzz" / "Cargo.toml"
    if path.stem not in cargo_toml_path.read_text():
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


@handler.register
def read_file(args: ReadFileRequest, *, ctx: BuilderContext) -> ReadFileResult:
    """Read a file

    The file path must be relative to the project root, e.g. "rust/src/foo.rs"
    """
    file_path = ctx.project_root / args.path
    if not file_path.exists():
        raise ValueError(f"File {args.path} does not exist")

    ctx.read_files.add(args.path)
    return ReadFileResult(source=file_path.read_text())


@handler.register
def write_file(args: WriteFileRequest, *, ctx: BuilderContext) -> WriteFileResult:
    """Write content to a file.

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


@handler.register
def append_to_file(args: AppendFileRequest, *, ctx: BuilderContext) -> AppendFileResult:
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


def run_rust_fuzz_test(
    args: RunFuzzTestRequest, *, ctx: BuilderContext
) -> FuzzTestResult:
    """Run a fuzz test target with the specified timeout."""
    result = subprocess.run(
        [
            "cargo",
            "fuzz",
            "run",
            args.target,
            "--",
            f"-max_total_time={args.timeout}",
        ],
        cwd=ctx.project_root / "rust",
        capture_output=True,
        text=True,
    )

    # give the LLM a hint about the source of the fuzz test.
    source_path = (
        ctx.project_root / "rust" / "fuzz" / "fuzz_targets" / f"{args.target}.rs"
    )

    if result.returncode != 0:
        raise FuzzTestError(source_path, result.stderr)

    return FuzzTestResult(success=True)


@handler.register
def edit_code(args: EditCodeRequest, *, ctx: BuilderContext) -> EditCodeResult:
    """Apply a patch to a source file.

        The patch must be in unified diff format:

    --- src/rust/file.rs
    +++ src/rust/file.rs
    @@ -1,1 +1,3 @@
    -old line
    +new line 1
    +new line 2
    """
    file_path = ctx.project_root / args.path

    if not file_path.exists():
        raise ValueError(f"File {args.path} does not exist")

    # must be in the rust/src or rust/fuzz/
    if "rust/src" not in str(file_path) and "rust/fuzz" not in str(file_path):
        raise ValueError(
            f"File {args.path} must be in the rust/src or rust/fuzz directory"
        )

    # Create a temporary patch file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".patch", delete=False
    ) as patch_file:
        patch_file.write(args.patch)
        patch_file_path = patch_file.name

    for level in [0, 1]:
        result = subprocess.run(
            [
                "patch",
                "--fuzz=3",
                "--force",
                "--ignore-whitespace",
                f"-p{level}",
                str(file_path),
            ],
            input=args.patch,
            text=True,
            capture_output=True,
            cwd=ctx.project_root,
        )
        if result.returncode == 0:
            return EditCodeResult(success=True)

    os.unlink(patch_file_path)
    raise ValueError(f"Patch application failed: {result.stderr}")


@handler.register
def list_files(args: ListFilesRequest, *, ctx: BuilderContext) -> ListFilesResult:
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


@handler.register
def search_files(args: SearchRequest, *, ctx: BuilderContext) -> SearchResult:
    """Search for a pattern in files using grep with context lines."""
    search_dir = ctx.project_root / args.directory

    if not search_dir.exists():
        raise ValueError(f"Directory {args.directory} does not exist")

    # Use subprocess to run grep for better performance
    result = subprocess.run(
        [
            "grep",
            "-rn",
            f"-C{args.context_lines}",
            "--include=*.c",
            "--include=*.h",
            "--include=*.rs",
            args.pattern,
            str(search_dir),
        ],
        capture_output=True,
        text=True,
    )
    return SearchResult(match_output=result.stdout)


async def stream_completion_with_tools(
    messages: list[dict[str, Any]],
    tools: ToolHandler,
) -> list[dict[str, Any]]:
    """Stream completion with function calling support."""

    # Log the completion request
    timestamp = datetime.now().isoformat().replace(":", "_")
    logs_dir = Path("logs/litellm")
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_data = {
        "timestamp": datetime.now().isoformat(),
        "model": MODEL,
        "messages": messages,
        "tools": tools.get_tools_spec(),
        "stream": True,
    }

    log_file = logs_dir / f"{timestamp}.json"
    with open(log_file, "w") as f:
        json.dump(log_data, f, indent=2)

    print(f"Logged completion request to {log_file}")

    response = await litellm.acompletion(
        model=MODEL,
        messages=messages,
        tools=tools.get_tools_spec(),
        tool_choice="auto",
        stream=True,
        stream_options={"include_usage": True},
    )

    content_parts = []
    tool_calls = []
    usage_data = None

    async for chunk in cast(litellm.CustomStreamWrapper, response):
        if chunk.choices[0].delta.content is not None:
            content = chunk.choices[0].delta.content
            content_parts.append(content)
            sys.stdout.write(content)
            sys.stdout.flush()
        if chunk.choices[0].delta.tool_calls:
            for tool_call in chunk.choices[0].delta.tool_calls:
                tool_calls.append(tool_call)
        if hasattr(chunk, "usage") and chunk.usage is not None:
            usage_data = chunk.usage

    # Log token usage and cost information
    if usage_data:
        prompt_tokens = getattr(usage_data, 'prompt_tokens', 0)
        completion_tokens = getattr(usage_data, 'completion_tokens', 0)
        total_tokens = getattr(usage_data, "total_tokens", 0)
        cost = litellm.completion_cost(completion_response=chunk)
        print(
            f"Token usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens} Cost: ${cost:.4f}"
        )

    assistant_message = {"role": "assistant", "content": "".join(content_parts)}
    if tool_calls:
        assistant_message["tool_calls"] = [
            tool_call.model_dump() for tool_call in tool_calls
        ]

    messages.append(assistant_message)

    if tool_calls:
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            args_json = tool_call.function.arguments

            result_message = tools.run(tool_name, args_json, tool_call.id)
            messages.append(result_message)

    return messages

async def stream_completion_with_retry(
    messages: list[dict[str, Any]],
    tools: ToolHandler,
    completion_fn: Callable[[], TaskStatus],
    max_attempts: int = MAX_ATTEMPTS,
) -> list[dict[str, Any]]:
    """Stream completion with retry."""

    if tools._context:
        tools._context.reset_read_files()

    # check if we already have a good result
    try:
        status = completion_fn()
    except Exception as e:
        status = TaskStatus()
        status.error(str(e))

    if status.is_done():
        return messages

    for attempt in range(max_attempts):
        print(f"Attempt {attempt + 1} of {max_attempts}")
        # Add feedback from previous attempt
        if attempt > 0 and not status.is_done():
            messages.append({"role": "user", "content": status.get_feedback()})

        messages = await stream_completion_with_tools(messages, tools)

        try:
            status = completion_fn()
        except Exception as e:
            status = TaskStatus()
            status.error(str(e))

        if status.is_done():
            return messages
        else:
            print(f"Attempt {attempt + 1} failed: {status.get_feedback()}")

    return messages


async def generate_stub_impl(
    symbol_name: str,
    symbol_kind: str,
    c_header_path: str,
    rust_src_path: str,
    rust_ffi_path: str,
    *,
    ctx: BuilderContext,
):
    """Generate stub implementation for a C symbol using LLM."""

    stub_prompt = f"""
I need you to create STUB implementations for the following C symbol:

Symbol: {symbol_name}
Kind: {symbol_kind}
C Header: {c_header_path}
Rust Source: {rust_src_path}
Rust FFI: {rust_ffi_path}
Create a stub _only_ for {symbol_name}.
Do not attempt to create stubs for any other symbols.
Do not output a license, comments or any other text other than the stub.

The rust module must be written to {rust_src_path}
The FFI bindings must be written to {rust_ffi_path}.
"""

    messages = [
        {"role": "system", "content": STUB_GENERATOR_PROMPT},
        {
            "role": "user",
            "content": stub_prompt,
        },
    ]

    # check rust project compiles and we have ffi and src files
    def _completion_fn() -> TaskStatus:
        result = TaskStatus()
        rust_src = ctx.project_root / rust_src_path
        rust_ffi = ctx.project_root / rust_ffi_path

        # Check if rust source file exists
        if not rust_src.exists():
            result.error(f"Rust source file {rust_src_path} does not exist")
            return result
        elif symbol_name not in rust_src.read_text():
            result.error(f"Symbol '{symbol_name}' not found in {rust_src_path}")
            return result

        # Check if rust FFI file exists
        if not rust_ffi.exists():
            result.error(f"Rust FFI file {rust_ffi_path} does not exist")
            return result
        elif symbol_name not in rust_ffi.read_text():
            result.error(f"Symbol '{symbol_name}' not found in {rust_ffi_path}")
            return result

        # Check if project compiles
        compile_rust_project(ctx.project_root / "rust")

        return result

    messages = await stream_completion_with_retry(messages, handler, _completion_fn)
    return messages


async def generate_fuzz_test(
    symbol_name: str,
    symbol_kind: str,
    c_header_path: str,
    c_source_path: str,
    rust_src_path: str,
    rust_ffi_path: str,
    rust_fuzz_path: str,
    *,
    ctx: BuilderContext,
):
    """Generate fuzz test for a C symbol using LLM."""

    fuzz_prompt = f"""
I need you to create a fuzz test for the following C symbol:

Symbol: {symbol_name}
Kind: {symbol_kind}
C Header: {c_header_path}
C Source: {c_source_path}

The symbol has a Rust implementation in {rust_src_path}.
The FFI bindings are in {rust_ffi_path}.

Use `write_rust_fuzz_test` tool to write the fuzz test.
Write the fuzz test to this exact path: {rust_fuzz_path}

DO NOT ATTEMPT TO IMPLEMENT THE FUNCTION.
"""

    messages = [
        {"role": "system", "content": CREATE_FUZZ_TEST_PROMPT},
        {
            "role": "user",
            "content": fuzz_prompt,
        },
    ]

    # Check fuzz test compiles and target is created
    def _completion_fn() -> TaskStatus:
        result = TaskStatus()
        fuzz_test_path = ctx.project_root / rust_fuzz_path

        if not fuzz_test_path.exists():
            result.error(f"Fuzz test file {rust_fuzz_path} does not exist")
        elif symbol_name not in fuzz_test_path.read_text():
            result.error(
                f"Symbol '{symbol_name}' not found in fuzz test {rust_fuzz_path}"
            )

        compile_rust_project(ctx.project_root / "rust")
        return result

    messages = await stream_completion_with_retry(messages, handler, _completion_fn)
    return messages

async def generate_full_impl(
    symbol_name: str,
    symbol_kind: str,
    c_header_path: str,
    c_source_path: str,
    rust_src_path: str,
    *,
    ctx: BuilderContext,
):
    """Generate full implementation for a C symbol using LLM."""

    impl_prompt = f"""
I need you to write the implementation for the following C symbol in Rust.
Do not attempt to implement any other symbols.

Symbol: {symbol_name}
Kind: {symbol_kind}  
C Header: {c_header_path}
C Source: {c_source_path}
Rust Source: {rust_src_path}

There is an existing stub implementation in {rust_src_path}.
Replace the existing stub implementation with a complete Rust implementation that:
- Exactly matches the C implementation's behavior
- Passes all fuzz tests that compare outputs with the C version
- Uses idiomatic Rust while maintaining exact behavioral compatibility

All C dependencies for the symbol have already been implemented in Rust, and you can
call them as needed.

The implementation should be written to: {rust_src_path}
"""

    messages = [
        {"role": "system", "content": IMPLEMENT_PROMPT},
        {
            "role": "user",
            "content": impl_prompt,
        },
    ]

    # Check implementation compiles and passes fuzz tests
    def _completion_fn() -> TaskStatus:
        result = TaskStatus()
        rust_src = ctx.project_root / rust_src_path
        fuzz_target = f"fuzz_{symbol_name}"

        # Check if rust source file exists
        if not rust_src.exists():
            result.error(f"Rust source file {rust_src_path} does not exist")
            return result
        else:
            rust_content = rust_src.read_text()
            if symbol_name not in rust_content:
                result.error(f"Symbol '{symbol_name}' not found in {rust_src_path}")

        compile_rust_project(ctx.project_root / "rust")
        run_rust_fuzz_test(RunFuzzTestRequest(target=fuzz_target, timeout=10), ctx=ctx)
        return result

    messages = await stream_completion_with_retry(messages, handler, _completion_fn)
    return messages


def write_logs(symbol_name: str, log_type: str, messages: list[dict[str, Any]]) -> None:
    """Write conversation messages to a log file."""
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    log_path = logs_dir / f"{symbol_name}_{log_type}.txt"
    with open(log_path, "w") as f:
        for msg in messages:
            if isinstance(msg, dict):
                f.write(json.dumps(msg, indent=2))
            else:
                f.write(msg.model_dump_json(indent=2))
            f.write("\n")


async def port_symbol(symbol: Symbol, *, ctx: BuilderContext) -> None:
    """Process a single symbol"""
    print(
        f"Processing {symbol.kind} {symbol.name} from {symbol.file_path}:{symbol.line_number}"
    )
    print(f"Dependencies: {symbol.dependencies if symbol.dependencies else 'none'}")
    c_header = Path("src") / symbol.file_path
    c_source = Path("src") / symbol.file_path.replace(".h", ".c")
    rust_src_path = Path("rust/src") / f"{c_header.stem}.rs"
    rust_ffi_path = Path("rust/src") / "ffi.rs"
    rust_fuzz_path = Path("rust/fuzz/fuzz_targets") / f"fuzz_{symbol.name}.rs"

    print(f"\nGenerating stub for {symbol.name}...")
    with SourceCheckpoint(source_dir=ctx.project_root / "rust"):
        stub_messages = await generate_stub_impl(
            symbol.name,
            symbol.kind,
            c_header_path=str(c_header),
            rust_src_path=str(rust_src_path),
            rust_ffi_path=str(rust_ffi_path),
            ctx=ctx,
        )
        compile_rust_project(ctx.project_root / "rust")
    write_logs(symbol.name, "stub", stub_messages)
    print(f"Stub generation completed for {symbol.name}")

    if symbol.kind != "struct":
        print(f"\nGenerating fuzz test for {symbol.name}...")
        with SourceCheckpoint(source_dir=ctx.project_root / "rust"):
            fuzz_messages = await generate_fuzz_test(
                symbol.name,
                symbol.kind,
                c_header_path=str(c_header),
                c_source_path=str(c_source),
                rust_src_path=str(rust_src_path),
                rust_ffi_path=str(rust_ffi_path),
                rust_fuzz_path=str(rust_fuzz_path),
                ctx=ctx,
            )
            compile_rust_project(ctx.project_root / "rust")
        write_logs(symbol.name, "fuzz", fuzz_messages)
        print(f"Fuzz test generation completed for {symbol.name}")

        print(f"\nGenerating full implementation for {symbol.name}...")
        with SourceCheckpoint(source_dir=ctx.project_root / "rust"):
            impl_messages = await generate_full_impl(
                symbol.name,
                symbol.kind,
                c_header_path=str(c_header),
                c_source_path=str(c_source),
                rust_src_path=str(rust_src_path),
                ctx=ctx,
            )
            compile_rust_project(ctx.project_root / "rust")
        write_logs(symbol.name, "impl", impl_messages)
        print(f"Full implementation completed for {symbol.name}")
    print(f"\nSuccessfully processed {symbol.name}")


async def run_traversal_pipeline(
    source_dir: str, *, ctx: BuilderContext
) -> dict[str, Any]:
    """Run the complete traversal pipeline on a C source directory."""
    print(f"Starting traversal pipeline on {source_dir}")

    traversal = CTraversal()
    symbols = traversal.parse_project(source_dir)

    print(f"Found {len(symbols)} symbols to process:")
    for i, symbol in enumerate(symbols, 1):
        cycle_marker = "*" if symbol.cycle else " "
        deps_str = (
            ", ".join(sorted(symbol.dependencies)) if symbol.dependencies else "none"
        )
        print(
            f"{cycle_marker} {i:3d}. {symbol.kind:<8} {symbol.name:<25} deps: {deps_str}"
        )

    results = {
        "total": len(symbols),
        "successful": 0,
        "failed": 0,
        "failed_symbols": [],
    }

    for i, symbol in enumerate(symbols, 1):
        print(f"\n{'─'*80}")
        print(f"Progress: {i}/{len(symbols)} ({i/len(symbols)*100:.1f}%)")

        try:
            await port_symbol(symbol, ctx=ctx)
            results["successful"] += 1
        except Exception:
            traceback.print_exc()
            results["failed"] += 1
            results["failed_symbols"].append(symbol.name)

    print(f"\n{'='*80}")
    print("Pipeline completed!")
    print(f"   Total symbols: {results['total']}")
    print(f"   Successful: {results['successful']}")
    print(f"   Failed: {results['failed']}")

    if results["failed_symbols"]:
        print(f"   Failed symbols: {', '.join(results['failed_symbols'])}")

    return results


async def main():
    ctx = BuilderContext(
        project_root=Path(__file__).parent.parent / "zopfli",
    )
    handler.set_context(ctx)

    source_dir = str(ctx.project_root / "src" / "zopfli")
    results = await run_traversal_pipeline(source_dir, ctx=ctx)

    if results["failed"] > 0:
        print(f"\nPipeline completed with {results['failed']} failures")
        exit(1)
    else:
        print("\nPipeline completed successfully!")
        exit(0)


if __name__ == "__main__":
    asyncio.run(main())
