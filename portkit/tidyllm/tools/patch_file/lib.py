"""Patch file tool with merged models for applying unified diff patches."""

import os
import re

from pydantic import BaseModel, Field


# Data Models
class PatchArgs(BaseModel):
    """Arguments for patch file operations."""

    patch_content: str = Field(
        description="Unified diff patch in format: @@ -old_start,old_count +new_start,new_count @@\\n context\\n-remove\\n+add",
        examples=[
            "@@ -1 +1 @@\n-old line\n+new line",
            "@@ -1,2 +1,2 @@\n-old line\n+new line\n unchanged",
            "--- a/file.txt\n+++ b/file.txt\n@@ -1,2 +1,2 @@\n-old line\n+new line\n unchanged",
        ],
    )
    target_text: str | None = Field(default=None, description="Text content to patch (for inline patches)")
    target_file: str | None = Field(default=None, description="File path to patch (for file patches)")
    dry_run: bool = Field(default=False, description="If True, validate patch without applying it")


class PatchResult(BaseModel):
    """Result of patch file operation."""

    success: bool = Field(description="Whether the patch was applied successfully")
    modified_content: str | None = Field(description="The patched content (for inline patches)")
    modified_file: str | None = Field(description="The patched file path (for file patches)")
    lines_added: int = Field(description="Number of lines added by the patch")
    lines_removed: int = Field(description="Number of lines removed by the patch")
    hunks_applied: int = Field(description="Number of patch hunks successfully applied")
    dry_run: bool = Field(description="Whether this was a dry run validation")
    patch_summary: str = Field(description="Human-readable summary of the patch")


# Core Implementation
def parse_unified_diff(patch_content: str) -> list[dict]:
    """Parse unified diff format into structured hunks.

    Args:
        patch_content: Raw unified diff content

    Returns:
        List of hunk dictionaries with line ranges and changes
    """
    hunks: list[dict] = []
    current_hunk: dict | None = None

    for line in patch_content.split("\n"):
        # Hunk header: @@ -start,count +start,count @@
        hunk_match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if hunk_match:
            old_start = int(hunk_match.group(1))
            old_count = int(hunk_match.group(2) or 1)
            new_start = int(hunk_match.group(3))
            new_count = int(hunk_match.group(4) or 1)

            current_hunk = {
                "old_start": old_start,
                "old_count": old_count,
                "new_start": new_start,
                "new_count": new_count,
                "changes": [],
            }
            hunks.append(current_hunk)
            continue

        # Skip file headers and other metadata
        if line.startswith("---") or line.startswith("+++") or line.startswith("diff"):
            continue

        # Process change lines within a hunk
        if current_hunk is not None:
            if line.startswith("-"):
                current_hunk["changes"].append(("remove", line[1:]))
            elif line.startswith("+"):
                current_hunk["changes"].append(("add", line[1:]))
            elif line.startswith(" "):
                current_hunk["changes"].append(("context", line[1:]))

    return hunks


def apply_hunk_to_lines(lines: list[str], hunk: dict) -> tuple[list[str], bool]:
    """Apply a single hunk to a list of lines.

    Args:
        lines: Original lines
        hunk: Hunk dictionary from parse_unified_diff

    Returns:
        Tuple of (modified_lines, success)
    """
    # Convert to 0-based indexing
    start_idx = hunk["old_start"] - 1

    # Extract the original section for validation
    original_section = lines[start_idx : start_idx + hunk["old_count"]]

    # Build expected original and new sections from hunk
    expected_original = []
    new_section = []

    for change_type, content in hunk["changes"]:
        if change_type in ("remove", "context"):
            expected_original.append(content)
        if change_type in ("add", "context"):
            new_section.append(content)

    # Validate that the original section matches expectations
    if len(original_section) != len(expected_original):
        return lines, False

    for orig_line, expected_line in zip(original_section, expected_original, strict=False):
        if orig_line.rstrip() != expected_line.rstrip():
            return lines, False

    # Apply the hunk
    result = lines[:start_idx] + new_section + lines[start_idx + hunk["old_count"] :]
    return result, True


def apply_patch(args: PatchArgs) -> PatchResult:
    """Apply the patch based on the provided arguments.

    Args:
        args: Patch arguments

    Returns:
        PatchResult with patch statistics and results

    Raises:
        ValueError: For invalid arguments or patch failures
    """
    # Validate arguments
    if not args.patch_content.strip():
        raise ValueError("Patch content cannot be empty")

    if not args.target_text and not args.target_file:
        raise ValueError("Either target_text or target_file must be provided")

    if args.target_text and args.target_file:
        raise ValueError("Cannot specify both target_text and target_file")

    # Get target content
    if args.target_file:
        if not os.path.exists(args.target_file):
            raise ValueError("Target file does not exist")
        with open(args.target_file, encoding="utf-8") as f:
            target_content = f.read()
    else:
        target_content = args.target_text

    # Parse the patch
    hunks = parse_unified_diff(args.patch_content)
    if not hunks:
        raise ValueError("No valid hunks found in patch content")

    # Apply hunks to content
    lines = target_content.split("\n")
    lines_added = 0
    lines_removed = 0
    hunks_applied = 0

    # Apply hunks in reverse order to maintain line numbering
    for hunk in reversed(hunks):
        modified_lines, success = apply_hunk_to_lines(lines, hunk)
        if not success:
            raise ValueError(f"Failed to apply hunk at line {hunk['old_start']}")

        lines = modified_lines
        hunks_applied += 1

        # Count changes in this hunk
        for change_type, _ in hunk["changes"]:
            if change_type == "add":
                lines_added += 1
            elif change_type == "remove":
                lines_removed += 1

    # Generate result
    modified_content = "\n".join(lines)

    # Create summary
    patch_summary = f"Applied {hunks_applied} hunk(s): +{lines_added} -{lines_removed} lines"

    # Handle dry run vs actual application
    if args.dry_run:
        return PatchResult(
            success=True,
            modified_content=modified_content if args.target_text else None,
            modified_file=args.target_file if args.target_file else None,
            lines_added=lines_added,
            lines_removed=lines_removed,
            hunks_applied=hunks_applied,
            dry_run=True,
            patch_summary=f"DRY RUN: {patch_summary}",
        )

    # Apply changes
    if args.target_file:
        with open(args.target_file, "w", encoding="utf-8") as f:
            f.write(modified_content)

        return PatchResult(
            success=True,
            modified_content=None,
            modified_file=args.target_file,
            lines_added=lines_added,
            lines_removed=lines_removed,
            hunks_applied=hunks_applied,
            dry_run=False,
            patch_summary=patch_summary,
        )
    else:
        return PatchResult(
            success=True,
            modified_content=modified_content,
            modified_file=None,
            lines_added=lines_added,
            lines_removed=lines_removed,
            hunks_applied=hunks_applied,
            dry_run=False,
            patch_summary=patch_summary,
        )
