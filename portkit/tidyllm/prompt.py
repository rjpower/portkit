"""Prompt loading with include directive support."""

import glob
import re
from pathlib import Path

import click


def module_dir(file_path: str) -> Path:
    """Get the directory containing a module file.

    Usage:
        @register(doc=read_prompt(module_dir(__file__) / "prompt.md"))
    """
    return Path(file_path).parent


def read_prompt(path: str | Path, source_paths: list[str | Path] | None = None) -> str:
    """
    Read a PROMPT.md file and process {{include:}} directives.

    Args:
        path: Path to the prompt file
        source_paths: Optional list of additional paths to search for include files

    Example:
        # Main prompt
        {{include: ./sub_prompt.md}}
    """
    base_path = Path(path).parent
    content = Path(path).read_text()

    # Add source paths to search directories
    search_paths = [base_path]
    if source_paths:
        search_paths.extend([Path(sp) for sp in source_paths])

    # Process includes recursively
    def process_includes(text: str, current_path: Path) -> str:
        pattern = r"\{\{include:\s*([^}]+)\}\}"

        def replace_include(match):
            include_path_str = match.group(1).strip()

            # Check if it's a glob pattern
            if '*' in include_path_str or '?' in include_path_str or '[' in include_path_str:
                # Handle glob patterns
                matched_files = []
                for search_path in search_paths:
                    glob_pattern = str(search_path / include_path_str)
                    matched_files.extend(glob.glob(glob_pattern))
                
                if not matched_files:
                    # Fallback to current_path for backward compatibility
                    glob_pattern = str(current_path / include_path_str)
                    matched_files.extend(glob.glob(glob_pattern))
                
                if not matched_files:
                    raise FileNotFoundError(
                        f"No files found matching glob pattern: {include_path_str} in any of the search paths"
                    )
                
                # Sort files for consistent ordering
                matched_files.sort()
                
                # Read and concatenate all matched files
                combined_content = []
                for file_path in matched_files:
                    file_path_obj = Path(file_path)
                    file_content = file_path_obj.read_text()
                    # Add filename guard
                    combined_content.append(f"<file name=\"{file_path_obj.name}\">\n{file_content}\n</file>")
                
                # Join all contents and recursively process includes
                full_content = "\n\n".join(combined_content)
                return process_includes(full_content, current_path)
            else:
                # Handle single file includes
                include_path = None
                for search_path in search_paths:
                    potential_path = search_path / include_path_str
                    if potential_path.exists():
                        include_path = potential_path
                        break

                if include_path is None:
                    # Fallback to current_path for backward compatibility
                    include_path = current_path / include_path_str
                    if not include_path.exists():
                        raise FileNotFoundError(
                            f"Include file not found: {include_path_str} in any of the search paths"
                        )

                included_content = include_path.read_text()
                # Add filename guard for single files too
                guarded_content = f"<file name=\"{include_path.name}\">\n{included_content}\n</file>"
                # Recursively process includes in the included file
                return process_includes(guarded_content, include_path.parent)

        return re.sub(pattern, replace_include, text)

    return process_includes(content, base_path)


@click.command()
@click.argument("prompt_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--source-paths",
    "-s",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Additional paths to search for include files",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file path (defaults to stdout)",
)
def resolve_prompt(
    prompt_file: Path, source_paths: tuple[Path, ...], output: Path | None
):
    """
    Resolve a prompt.md file by processing all {{include:}} directives.

    Example:
        python -m portkit.tidyllm.prompt prompt.md -s ./includes -o resolved_prompt.md
    """
    try:
        resolved_content = read_prompt(prompt_file, list(source_paths))

        if output:
            output.write_text(resolved_content)
            click.echo(f"Resolved prompt written to: {output}")
        else:
            click.echo(resolved_content)

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort() from e
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        raise click.Abort() from e


if __name__ == "__main__":
    resolve_prompt()
