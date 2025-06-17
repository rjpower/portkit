import asyncio
import json
import traceback
from enum import Enum
from pathlib import Path
from typing import Any

import click
from pydantic import BaseModel, Field

from portkit.checkpoint import SourceCheckpoint
from portkit.claude import port_symbol_claude
from portkit.codex import call_with_codex_retry
from portkit.console import Console
from portkit.interrupt import InterruptHandler
from portkit.sourcemap import (
    SourceMap,
    Symbol,
    SymbolInfo,
)
from portkit.tinyagent import (
    TOOL_HANDLER,
    RunFuzzTestRequest,
    TaskStatus,
    call_with_retry,
    compile_rust_project,
    run_fuzz_test,
)


class EditorType(str, Enum):
    LITELLM = "litellm"
    CODEX = "codex"
    CLAUDE = "claude"


def load_prompt(name: str) -> str:
    """Load a prompt from the prompts directory."""
    prompt_path = Path(__file__).parent / "prompts" / f"{name}.md"
    return prompt_path.read_text()


UNIFIED_IMPLEMENTATION_PROMPT = f"""
<instructions>
{load_prompt("unified_implementation")}
</instructions>

<fuzzing>
{load_prompt("example_fuzz_test")}
</fuzzing>
"""


class BuilderContext(BaseModel):
    console: Console
    project_root: Path
    source_map: SourceMap
    editor_type: EditorType = EditorType.LITELLM
    read_files: set[str] = Field(default_factory=set)
    has_mutations: bool = False
    processed_symbols: set[str] = Field(default_factory=set)
    failed_symbols: set[str] = Field(default_factory=set)
    interrupt_handler: InterruptHandler = Field(default_factory=InterruptHandler)

    running_cost: float = 0.0

    model_config = {"arbitrary_types_allowed": True}

    def reset_read_files(self) -> None:
        """Reset the set of read files for a new LLM interaction."""
        self.read_files.clear()
        self.has_mutations = False

    def reset_mutations(self) -> None:
        """Reset the set of mutations for a new LLM interaction."""
        self.has_mutations = False

    @property
    def rust_ffi_path(self) -> Path:
        return self.project_root / "rust/src/ffi.rs"

    @property
    def rust_src_root(self) -> Path:
        return self.project_root / "rust/src"

    def rust_src_for_symbol(self, symbol: Symbol) -> Path:
        if symbol.source_path:
            return self.rust_src_root / f"{symbol.source_path.stem}.rs"
        elif symbol.header_path:
            return self.rust_src_root / f"{symbol.header_path.stem}.rs"
        else:
            return self.rust_src_root / f"{symbol.name}.rs"

    def rust_fuzz_for_symbol(self, symbol: Symbol) -> Path:
        return self.project_root / "rust/fuzz/fuzz_targets" / f"fuzz_{symbol.name}.rs"


def has_implementation(symbol_kind: str) -> bool:
    return symbol_kind not in ["struct", "typedef", "enum", "union"]


def should_skip_symbol(symbol: Symbol, failed_symbols: set[str]) -> bool:
    """Check if symbol should be skipped due to failed dependencies."""
    return bool(symbol.all_dependencies & failed_symbols)


def is_symbol_ported(symbol: Symbol, ctx: BuilderContext, initial: bool = True) -> TaskStatus:
    """Check if symbol implementation is complete and return status."""
    result = TaskStatus()

    # Check current locations
    locations = ctx.source_map.lookup_symbol(symbol.name)

    # Check FFI binding
    if not locations.ffi_path:
        result.error(f"FFI binding for '{symbol.name}' not found")
    else:
        ffi_content = ctx.source_map.find_ffi_binding_definition(
            ctx.project_root / locations.ffi_path, symbol.name
        )
        if not ffi_content:
            result.error(
                f"FFI binding for '{symbol.name}' not found in {locations.ffi_path}"
            )
        else:
            result.diagnostic(
                f"FFI binding for '{symbol.name}' found in {locations.ffi_path}"
            )

    if has_implementation(symbol.kind):
        # Check Rust implementation
        if not locations.rust_src_path:
            result.error(f"Rust implementation for '{symbol.name}' not found")
        else:
            rust_content = ctx.source_map.find_rust_symbol_definition(
                ctx.project_root / locations.rust_src_path, symbol.name
            )
            if not rust_content or "unimplemented!()" in rust_content:
                result.error(
                    f"Implementation for '{symbol.name}' not found or is still a stub in {locations.rust_src_path}"
                )
            else:
                result.diagnostic(
                    f"Implementation for '{symbol.name}' found in {locations.rust_src_path}"
                )

        # Check fuzz test
        if not locations.rust_fuzz_path:
            result.error(f"Fuzz test for '{symbol.name}' not found")
        else:
            fuzz_path = ctx.project_root / locations.rust_fuzz_path
            if not fuzz_path.exists():
                result.error(
                    f"Fuzz test file for '{symbol.name}' does not exist: {locations.rust_fuzz_path}"
                )
            else:
                fuzz_content = fuzz_path.read_text()
                if (
                    symbol.name not in fuzz_content
                    or "fuzz_target!" not in fuzz_content
                ):
                    result.error(
                        f"Fuzz test for '{symbol.name}' not properly defined in {locations.rust_fuzz_path}"
                    )
                else:
                    result.diagnostic(
                        f"Fuzz test for '{symbol.name}' found in {locations.rust_fuzz_path}"
                    )

    if result.is_done():
        if initial:
            return result

        if has_implementation(symbol.kind):
            fuzz_target = f"fuzz_{symbol.name}"
            runs = 100 if initial else -1
            try:
                run_fuzz_test(
                    RunFuzzTestRequest(target=fuzz_target, runs=runs), ctx=ctx
                )
            except Exception as e:
                result.error(f"Fuzz test failed: {str(e)}")

        compile_rust_project(ctx.project_root / "rust", ctx=ctx)

    return result


def generate_unified_prompt(
    symbol: Symbol,
    *,
    ctx: BuilderContext,
) -> str:
    rust_ffi_path = ctx.rust_ffi_path
    rust_src_path = ctx.rust_src_for_symbol(symbol)
    rust_fuzz_path = ctx.rust_fuzz_for_symbol(symbol)

    # Convert absolute paths to relative paths from project root
    rust_src_rel = (
        rust_src_path.relative_to(ctx.project_root)
        if rust_src_path.is_absolute()
        else rust_src_path
    )
    rust_ffi_rel = (
        rust_ffi_path.relative_to(ctx.project_root)
        if rust_ffi_path.is_absolute()
        else rust_ffi_path
    )
    rust_fuzz_rel = (
        rust_fuzz_path.relative_to(ctx.project_root)
        if rust_fuzz_path.is_absolute()
        else rust_fuzz_path
    )

    # Get symbol source code using SourceMap
    c_definition = ctx.source_map.get_symbol_source_code(symbol.name)

    # Check if FFI binding exists
    locations = ctx.source_map.lookup_symbol(symbol.name)
    ffi_binding_content = ""
    if locations.ffi_path:
        ffi_binding_content = ctx.source_map.find_ffi_binding_definition(
            ctx.project_root / locations.ffi_path, symbol.name
        )

    # Check if Rust implementation exists
    rust_src_content = ""
    if locations.rust_src_path:
        rust_src_content = ctx.source_map.find_rust_symbol_definition(
            ctx.project_root / locations.rust_src_path, symbol.name
        )

    # Check if fuzz test exists
    fuzz_test_content = ""
    if locations.rust_fuzz_path:
        fuzz_path = ctx.project_root / locations.rust_fuzz_path
        if fuzz_path.exists():
            fuzz_test_content = fuzz_path.read_text()

    sorted_symbols = sorted(ctx.processed_symbols)
    processed_symbols_text = f"""
<processed_symbols>
The following symbols have already been successfully ported:
{', '.join(sorted_symbols)}
</processed_symbols>
"""

    rust_src_text = ""
    if rust_src_content:
        rust_src_text = f"""
{rust_src_rel} currently contains the following Rust symbol definition:
<rust_symbol_definition>
{rust_src_content}
</rust_symbol_definition>
"""

    rust_ffi_text = ""
    if rust_ffi_path and ffi_binding_content:
        rust_ffi_text = f"""
{rust_ffi_rel} currently contains the following FFI binding:
<ffi_binding>
{ffi_binding_content}
</ffi_binding>
"""

    rust_fuzz_text = ""
    if rust_fuzz_path and fuzz_test_content:
        rust_fuzz_text = f"""
{rust_fuzz_rel} currently contains the following Rust fuzz test:
<fuzz_test>
{fuzz_test_content}
</fuzz_test>
"""

    # Get C declaration if available
    c_declaration = ""
    if locations.c_header_path:
        c_symbol = ctx.source_map.get_symbol(symbol.name)
        if c_symbol.declaration_file:
            header_path = ctx.project_root / c_symbol.declaration_file
            c_declaration = ctx.source_map.find_c_symbol_definition(
                header_path, symbol.name
            )

    return f"""
<port>
Port this symbol: {symbol.name}
Kind: {symbol.kind}
C Header: {symbol.header_path}
C Source: {symbol.source_path}

{processed_symbols_text}
<c_declaration>
{c_declaration}
</c_declaration>

<c_definition>
{c_definition}
</c_definition>

{rust_src_text}{rust_ffi_text}{rust_fuzz_text}
"""


async def generate_implementation(
    symbol: Symbol,
    *,
    ctx: BuilderContext,
):
    """Generate FFI bindings, implementation, and fuzz test in a single LLM call."""
    unified_prompt = generate_unified_prompt(
        symbol=symbol,
        ctx=ctx,
    )

    repo_map_text = f"""
<repo_map>
Repository structure and key symbols:

{ctx.source_map.generate_repo_map()}
</repo_map>
"""

    messages = [
        {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": UNIFIED_IMPLEMENTATION_PROMPT,
                    # "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": repo_map_text,
                    # "cache_control": {"type": "ephemeral"},
                },
            ],
        },
        {
            "role": "user",
            "content": unified_prompt,
        },
    ]

    completion_fn = lambda initial: is_symbol_ported(symbol, ctx, initial)

    if ctx.editor_type == EditorType.CODEX:
        return await call_with_codex_retry(
            messages, completion_fn, ctx.project_root, ctx=ctx
        )
    elif ctx.editor_type == EditorType.CLAUDE:
        # Use Claude Code directly instead of LLM API
        c_source = ctx.source_map.get_symbol_source_code(symbol.name)
        await port_symbol_claude(
            symbol, c_source, project_root=ctx.project_root, source_map=ctx.source_map
        )
        return completion_fn(False)  # Check final status
    else:
        return await call_with_retry(messages, TOOL_HANDLER, completion_fn, ctx=ctx)


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
    """Process a single symbol using unified implementation approach."""
    status = is_symbol_ported(symbol, ctx)
    if status.is_done():
        ctx.console.print(f"[green]Symbol {symbol.name} already ported[/green]")
        return
    
    ctx.console.print(f"[bold blue]Processing {symbol}[/bold blue]")
    # save a checkpoint and restore if compilation fails after the LLM is done.
    checkpoint = SourceCheckpoint(source_dir=ctx.project_root / "rust")
    checkpoint.save()
    try:
        await generate_implementation(
            symbol=symbol,
            ctx=ctx,
        )
    finally:
        try:
            compile_rust_project(ctx.project_root / "rust", ctx=ctx)
        except Exception:
            ctx.console.print("[red]Compilation failed, restoring checkpoint[/red]")
            checkpoint.restore()
            raise
        checkpoint.cleanup()

async def run_traversal_pipeline(
    source_dir: str, *, ctx: BuilderContext
) -> dict[str, Any]:
    """Run the complete traversal pipeline on a C source directory."""
    ctx.console.print(
        f"[bold green]Starting traversal pipeline on {source_dir}[/bold green]"
    )

    symbols = ctx.source_map.get_topological_order()

    ctx.console.print(f"[yellow]Found {len(symbols)} symbols to process:[/yellow]")
    for i, symbol in enumerate(symbols, 1):
        cycle_marker = "*" if symbol.is_cycle else " "
        ctx.console.print(f"{cycle_marker} {i:3d}. {symbol.kind:<8} {symbol.name:<25}")

    results = {
        "total": len(symbols),
        "successful": 0,
        "failed": 0,
        "failed_symbols": [],
    }

    for i, symbol in enumerate(symbols, 1):
        ctx.console.print(f"\n{'─'*80}")
        ctx.console.print(
            f"[bold cyan]Progress: {i}/{len(symbols)} ({i/len(symbols)*100:.1f}%)[/bold cyan]"
        )

        if should_skip_symbol(symbol, ctx.failed_symbols):
            failed_deps = symbol.all_dependencies & ctx.failed_symbols
            ctx.console.print(
                f"[yellow]Skipping {symbol.name} due to failed dependencies: {', '.join(sorted(failed_deps))}[/yellow]"
            )
            ctx.failed_symbols.add(symbol.name)
            results["failed"] += 1
            results["failed_symbols"].append(symbol.name)
            continue

        try:
            await port_symbol(symbol, ctx=ctx)
            ctx.processed_symbols.add(symbol.name)
            results["successful"] += 1
            ctx.console.print(f"[green]Successfully processed {symbol.name}[/green]")
        except Exception:
            ctx.console.print(f"[red]Failed to port symbol {symbol.name}[/red]")
            traceback.print_exc()
            ctx.failed_symbols.add(symbol.name)
            results["failed"] += 1
            results["failed_symbols"].append(symbol.name)

    ctx.console.print(f"\n{'='*80}")
    ctx.console.print("[bold green]Pipeline completed![/bold green]")
    ctx.console.print(f"[cyan]   Total symbols: {results['total']}[/cyan]")
    ctx.console.print(f"[green]   Successful: {results['successful']}[/green]")
    ctx.console.print(f"[red]   Failed: {results['failed']}[/red]")

    if results["failed_symbols"]:
        ctx.console.print(
            f"[red]   Failed symbols: {', '.join(results['failed_symbols'])}[/red]"
        )

    return results


async def main_litellm():
    project_root = Path(__file__).parent.parent / "zopfli-gemini-pro"
    ctx = BuilderContext(
        project_root=project_root,
        source_map=SourceMap(project_root),
        console=Console(),
    )
    TOOL_HANDLER.set_context(ctx)

    # Setup interrupt handler
    ctx.interrupt_handler.setup()

    try:
        compile_rust_project(ctx.project_root / "rust", ctx=ctx)
        source_dir = str(ctx.project_root / "src" / "zopfli")
        results = await run_traversal_pipeline(source_dir, ctx=ctx)
        if results["failed"] > 0:
            ctx.console.print(
                f"[red]\nPipeline completed with {results['failed']} failures[/red]"
            )
            exit(1)
        else:
            ctx.console.print("[green]\nPipeline completed successfully![/green]")
            exit(0)
    finally:
        # Cleanup interrupt handler
        ctx.interrupt_handler.cleanup()


async def main_with_editor(editor_type: EditorType):
    """Main function that runs with specified editor type."""
    project_root = Path(__file__).parent.parent / "zopfli-gemini-pro"
    ctx = BuilderContext(
        project_root=project_root,
        source_map=SourceMap(project_root),
        editor_type=editor_type,
        console=Console(),
    )
    TOOL_HANDLER.set_context(ctx)

    ctx.console.print(f"[bold green]Using editor: {editor_type.value}[/bold green]")

    # Setup interrupt handler
    ctx.interrupt_handler.setup()

    try:
        compile_rust_project(ctx.project_root / "rust", ctx=ctx)
        source_dir = str(ctx.project_root / "src" / "zopfli")
        results = await run_traversal_pipeline(source_dir, ctx=ctx)

        if results["failed"] > 0:
            ctx.console.print(
                f"[red]\nPipeline completed with {results['failed']} failures[/red]"
            )
            exit(1)
        else:
            ctx.console.print("[green]\nPipeline completed successfully![/green]")
            exit(0)
    finally:
        # Cleanup interrupt handler
        ctx.interrupt_handler.cleanup()


@click.command()
@click.option(
    "--editor",
    type=click.Choice([e.value for e in EditorType], case_sensitive=False),
    default=EditorType.LITELLM.value,
    help="Editor type to use for code generation",
)
def main(editor: str):
    """Port C code to Rust using AI-powered code generation."""
    editor_type = EditorType(editor.lower())
    asyncio.run(main_with_editor(editor_type))


if __name__ == "__main__":
    main()
