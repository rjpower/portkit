#!/usr/bin/env python3
"""Aider-style diff-fenced patch tool for applying code changes."""

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import NamedTuple, Protocol

from pydantic import BaseModel, Field

from portkit.config import ProjectConfig
from portkit.tidyllm import register
from portkit.tidyllm.prompt import module_dir, read_prompt


class PatchContext(Protocol):
    config: ProjectConfig
    read_files: set[str]


from portkit.tools.common import update_fuzz_cargo_toml, update_lib_rs


# Data Models
class PatchArgs(BaseModel):
    """Arguments for applying aider-style diff-fenced patches."""

    patches: list[str] = Field(
        description="List of aider-style diff-fenced patches in format: 'file_path\\n<<<<<<< SEARCH\\nold_content\\n=======\\nnew_content\\n>>>>>>> REPLACE'",
        examples=[
            'src/main.rs\n<<<<<<< SEARCH\nfn old_function() {\n    println!("old");\n}\n=======\nfn new_function() {\n    println!("new");\n}\n>>>>>>> REPLACE',
            "lib.rs\n<<<<<<< SEARCH\n\n=======\npub mod new_module;\n>>>>>>> REPLACE",
        ],
    )


class PatchResult(BaseModel):
    """Result of applying aider-style diff-fenced patches."""

    success: bool = Field(description="Whether all patches were applied successfully")
    files_modified: list[str] = Field(description="List of files that were modified")
    patches_applied: int = Field(description="Number of patches successfully applied")
    total_patches: int = Field(description="Total number of patches attempted")
    messages: list[str] = Field(description="Status messages and any errors")


# Core Implementation
class PatchOperation(NamedTuple):
    """A single patch operation extracted from aider diff-fenced format."""

    file_path: str
    search_text: str
    replace_text: str


class AiderDiffPatcher:
    """Handles aider-style diff-fenced patch operations with flexible matching."""

    def parse_patches(self, patches: list[str]) -> list[PatchOperation]:
        """Parse list of aider diff-fenced patches into PatchOperation objects.

        Args:
            patches: List of patch strings, each containing file path and diff blocks

        Returns:
            List of PatchOperation objects

        Raises:
            ValueError: If patch format is invalid
        """
        operations = []

        for patch_text in patches:
            operations.extend(self._parse_single_patch(patch_text))

        return operations

    def _parse_single_patch(self, patch_text: str) -> list[PatchOperation]:
        """Parse a single patch text into operations."""
        lines = patch_text.strip().split("\n")
        operations: list[PatchOperation] = []
        current_file: str | None = None
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            if line == "<<<<<<< SEARCH":
                if current_file is None:
                    raise ValueError("Found patch block without file path")

                # Parse the diff block
                search_lines, replace_lines, i = self._parse_diff_block(lines, i)

                operations.append(
                    PatchOperation(
                        file_path=current_file,
                        search_text="\n".join(search_lines),
                        replace_text="\n".join(replace_lines),
                    )
                )

            elif line and not line.startswith(">>>>>>>"):
                # This is likely a file path
                current_file = line

            i += 1

        if not operations:
            raise ValueError(
                "Invalid aider diff-fenced format. Expected format:\n"
                "path/to/file\n"
                "<<<<<<< SEARCH\n"
                "old content\n"
                "=======\n"
                "new content\n"
                ">>>>>>> REPLACE"
            )

        return operations

    def _parse_diff_block(
        self, lines: list[str], start_idx: int
    ) -> tuple[list[str], list[str], int]:
        """Parse a single diff block starting from <<<<<<< SEARCH."""
        search_lines = []
        replace_lines = []
        i = start_idx + 1  # Skip <<<<<<< SEARCH

        # Collect search lines until =======
        while i < len(lines) and lines[i] != "=======":
            search_lines.append(lines[i])
            i += 1

        if i >= len(lines):
            raise ValueError("Invalid patch format: missing =======")

        i += 1  # Skip =======

        # Collect replace lines until >>>>>>> REPLACE
        while i < len(lines) and lines[i] != ">>>>>>> REPLACE":
            replace_lines.append(lines[i])
            i += 1

        if i >= len(lines):
            raise ValueError("Invalid patch format: missing >>>>>>> REPLACE")

        return search_lines, replace_lines, i

    def normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace for flexible matching while preserving structure."""
        lines = text.split("\n")
        normalized_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped:
                # Normalize internal whitespace while preserving basic structure
                normalized = re.sub(r"\s+", " ", stripped)
                normalized_lines.append(normalized)
            else:
                normalized_lines.append("")

        return "\n".join(normalized_lines)

    def find_best_fuzzy_match(
        self, content: str, search_text: str, threshold: float = 0.85
    ) -> str | None:
        """Find the best fuzzy match for search_text in content."""
        content_lines = content.split("\n")
        search_lines = search_text.split("\n")

        best_score = 0.0
        best_match = None

        # Try different window sizes around the search text length
        for window_size in [
            len(search_lines),
            len(search_lines) + 1,
            len(search_lines) - 1,
        ]:
            if window_size <= 0:
                continue

            for i in range(len(content_lines) - window_size + 1):
                content_slice = "\n".join(content_lines[i : i + window_size])
                score = SequenceMatcher(None, search_text, content_slice).ratio()

                if score > best_score and score >= threshold:
                    best_score = score
                    best_match = content_slice

        return best_match

    def apply_patch_operation(self, content: str, operation: PatchOperation) -> str:
        """Apply a single patch operation to content.

        Args:
            content: The current file content
            operation: The patch operation to apply

        Returns:
            Modified content

        Raises:
            ValueError: If search text cannot be found
        """
        search_text = operation.search_text
        replace_text = operation.replace_text

        # Handle empty search text (for file creation or appending)
        if search_text == "":
            if content == "":
                return replace_text
            else:
                raise ValueError("Empty search text is only allowed for empty files")

        # Try exact match first
        if search_text in content:
            return content.replace(search_text, replace_text, 1)  # Replace only first occurrence

        # Try normalized whitespace matching
        normalized_content = self.normalize_whitespace(content)
        normalized_search = self.normalize_whitespace(search_text)

        if normalized_search in normalized_content:
            # Find the original position and replace
            return self._replace_with_normalized_match(content, search_text, replace_text)

        # Try fuzzy matching as last resort
        best_match = self.find_best_fuzzy_match(content, search_text)
        if best_match:
            print(
                f"Warning: Using fuzzy match (similarity: {SequenceMatcher(None, search_text, best_match).ratio():.2f})"
            )
            return content.replace(best_match, replace_text, 1)

        # Provide detailed error information
        self._raise_detailed_error(content, search_text)
        return content  # This will never be reached, but satisfies type checker

    def _replace_with_normalized_match(
        self, content: str, search_text: str, replace_text: str
    ) -> str:
        """Replace text using normalized matching to find the exact position."""
        content_lines = content.split("\n")
        search_lines = search_text.split("\n")
        normalized_search = self.normalize_whitespace(search_text)

        # Find the sequence of lines that match when normalized
        for i in range(len(content_lines) - len(search_lines) + 1):
            content_slice = "\n".join(content_lines[i : i + len(search_lines)])
            if self.normalize_whitespace(content_slice) == normalized_search:
                # Replace this slice
                before = "\n".join(content_lines[:i])
                after = "\n".join(content_lines[i + len(search_lines) :])

                if before and after:
                    return before + "\n" + replace_text + "\n" + after
                elif before:
                    return before + "\n" + replace_text
                elif after:
                    return replace_text + "\n" + after
                else:
                    return replace_text

        raise ValueError("Search text not found in file after normalization")

    def _raise_detailed_error(self, content: str, search_text: str) -> None:
        """Raise a detailed error with helpful context."""
        content_preview = content[:200] + "..." if len(content) > 200 else content
        search_preview = search_text[:100] + "..." if len(search_text) > 100 else search_text

        # Try to suggest the closest match
        best_match = self.find_best_fuzzy_match(content, search_text, threshold=0.3)
        suggestion = ""
        if best_match:
            similarity = SequenceMatcher(None, search_text, best_match).ratio()
            suggestion = (
                f"\nClosest match found (similarity: {similarity:.2f}):\n{best_match[:100]}"
            )

        raise ValueError(
            f"Search text not found in file.\n"
            f"Search text (first 100 chars):\n{search_preview}\n"
            f"File content (first 200 chars):\n{content_preview}\n"
            f"Normalized search:\n{self.normalize_whitespace(search_text)[:100]}\n"
            f"Normalized content:\n{self.normalize_whitespace(content)[:200]}{suggestion}"
        )

    def apply_patches(self, patches: list[str], project_root: Path) -> tuple[list[Path], list[str]]:
        """Apply multiple aider diff-fenced patches.

        Args:
            patches: List of patch strings
            project_root: Root directory for resolving relative paths

        Returns:
            Tuple of (modified_files, error_messages)
        """
        operations = self.parse_patches(patches)
        modified_files = set()
        errors = []

        for operation in operations:
            try:
                # Resolve file path
                if operation.file_path.startswith("/"):
                    file_path = Path(operation.file_path)
                else:
                    file_path = project_root / operation.file_path

                # Handle file creation
                if not file_path.exists():
                    if operation.search_text == "":
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        file_path.write_text(operation.replace_text)
                        modified_files.add(file_path)
                        continue
                    else:
                        raise ValueError(f"File {operation.file_path} does not exist")

                # Read, modify, and write file
                current_content = file_path.read_text()
                new_content = self.apply_patch_operation(current_content, operation)
                file_path.write_text(new_content)
                modified_files.add(file_path)

            except Exception as e:
                errors.append(f"Failed to apply patch to {operation.file_path}: {e}")

        return list(modified_files), errors


# Tool Registration
@register(doc=read_prompt(module_dir(__file__) / "prompt.md"))
def edit_code(args: PatchArgs, *, ctx: PatchContext) -> PatchResult:
    """Apply aider-style diff-fenced patches to source files."""
    patcher = AiderDiffPatcher()
    result = PatchResult(
        success=True,
        files_modified=[],
        patches_applied=0,
        total_patches=len(args.patches),
        messages=[],
    )

    try:
        modified_files, errors = patcher.apply_patches(args.patches, ctx.config.project_root)

        # Validate file paths are in allowed directories
        for file_path in modified_files:
            rust_src_path = str(ctx.config.rust_src_path())
            rust_fuzz_path = str(ctx.config.rust_fuzz_root_path())

            if rust_src_path not in str(file_path) and rust_fuzz_path not in str(file_path):
                raise ValueError(
                    f"File {file_path} must be in the {ctx.config.rust_src_dir} "
                    f"or {ctx.config.fuzz_dir} directory"
                )

            # Update Rust project files
            update_lib_rs(ctx, file_path)
            update_fuzz_cargo_toml(ctx, file_path)

            ctx.console.print(f"[green]✓[/green] Applied patch to {file_path}")

        result.files_modified = [str(f) for f in modified_files]
        result.patches_applied = len(modified_files)
        result.messages.extend(errors)

        if errors:
            result.success = False
            result.messages.append(
                f"Applied {len(modified_files)} patches successfully, {len(errors)} failed"
            )
        else:
            result.messages.append(f"Successfully applied all {len(modified_files)} patches")

    except Exception as e:
        result.success = False
        result.messages.append(f"Fatal error: {e}")

    return result
