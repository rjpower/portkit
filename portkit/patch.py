#!/usr/bin/env python3

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import NamedTuple


class PatchMatch(NamedTuple):
    """A single patch operation."""
    file_path: str
    search_text: str
    replace_text: str


class DiffFencedPatcher:
    """Handles Aider-style diff-fenced patch operations with flexible whitespace matching."""

    def __init__(self):
        self.search_pattern = re.compile(r'^<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n?>>>>>>> REPLACE', re.MULTILINE | re.DOTALL)

    def parse_patch(self, patch_text: str) -> list[PatchMatch]:
        """Parse diff-fenced patch text into PatchMatch objects."""
        lines = patch_text.split('\n')
        result = []
        current_file = None
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Check if this line starts a search block
            if line == '<<<<<<< SEARCH':
                if current_file is None:
                    raise ValueError("Found patch block without file path")

                # Find the end of this patch block
                search_lines = []
                replace_lines = []
                i += 1

                # Collect search lines until =======
                while i < len(lines) and lines[i] != '=======':
                    search_lines.append(lines[i])
                    i += 1

                if i >= len(lines):
                    raise ValueError("Invalid patch format: missing =======")

                i += 1  # Skip =======

                # Collect replace lines until >>>>>>> REPLACE
                while i < len(lines) and lines[i] != '>>>>>>> REPLACE':
                    replace_lines.append(lines[i])
                    i += 1

                if i >= len(lines):
                    raise ValueError("Invalid patch format: missing >>>>>>> REPLACE")

                # Create the patch match
                search_text = '\n'.join(search_lines)
                replace_text = '\n'.join(replace_lines)

                result.append(PatchMatch(
                    file_path=current_file,
                    search_text=search_text,
                    replace_text=replace_text
                ))

            elif line and not line.startswith('>>>>>>>'):
                # This is likely a file path
                current_file = line

            i += 1

        if not result:
            raise ValueError(
                "Invalid diff-fenced format. Expected format:\n"
                "path/to/file\n"
                "<<<<<<< SEARCH\n"
                "old content\n"
                "=======\n"
                "new content\n"
                ">>>>>>> REPLACE"
            )

        return result

    def normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace for flexible matching while preserving line structure."""
        lines = text.split('\n')
        normalized_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped:
                # Normalize internal whitespace while preserving basic structure
                normalized = re.sub(r'\s+', ' ', stripped)
                normalized_lines.append(normalized)
            else:
                normalized_lines.append('')

        return '\n'.join(normalized_lines)

    def find_best_match(
        self, content: str, search_text: str, threshold: float = 0.95
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

    def find_and_replace(self, content: str, search_text: str, replace_text: str) -> str:
        """Find and replace text with flexible whitespace matching."""
        # Handle empty search text as a special case - only for empty files
        if search_text == "":
            if content == "":
                return replace_text
            else:
                raise ValueError("Empty search text is only allowed for empty files")

        # First try exact match
        if search_text in content:
            return content.replace(search_text, replace_text)

        # Try normalized whitespace matching
        normalized_content = self.normalize_whitespace(content)
        normalized_search = self.normalize_whitespace(search_text)

        if normalized_search not in normalized_content:
            # Try fuzzy matching as a last resort
            best_match = self.find_best_match(content, search_text)
            if best_match:
                print("Warning: Using fuzzy match for search text.")
                return content.replace(best_match, replace_text)

            # Provide more detailed error information
            content_preview = content[:200] + "..." if len(content) > 200 else content
            search_preview = (
                search_text[:100] + "..." if len(search_text) > 100 else search_text
            )

            # Try to suggest the closest match
            best_match_for_error = self.find_best_match(
                content, search_text, threshold=0.3
            )
            suggestion = ""
            if best_match_for_error:
                suggestion = f"\nClosest match found:\n{best_match_for_error[:100]}"

            raise ValueError(
                f"Search text not found in file.\n"
                f"Search text (first 100 chars):\n{search_preview}\n"
                f"File content (first 200 chars):\n{content_preview}\n"
                f"Normalized search:\n{normalized_search[:100]}\n"
                f"Normalized content:\n{normalized_content[:200]}{suggestion}"
            )

        # Find the original position in the non-normalized content
        content_lines = content.split('\n')
        search_lines = search_text.split('\n')

        # Try to find a sequence of lines that match when normalized
        for i in range(len(content_lines) - len(search_lines) + 1):
            content_slice = '\n'.join(content_lines[i:i + len(search_lines)])
            if self.normalize_whitespace(content_slice) == normalized_search:
                # Replace this slice
                before = '\n'.join(content_lines[:i])
                after = '\n'.join(content_lines[i + len(search_lines):])

                if before and after:
                    return before + '\n' + replace_text + '\n' + after
                elif before:
                    return before + '\n' + replace_text
                elif after:
                    return replace_text + '\n' + after
                else:
                    return replace_text

        raise ValueError(f"Search text not found in file. Search text:\n{search_text}")

    def apply_patch(self, patch_text: str, project_root: Path) -> list[Path]:
        """Apply a diff-fenced patch and return list of modified files."""
        patch_matches = self.parse_patch(patch_text)
        modified_files = set()

        for match in patch_matches:
            # Handle both absolute and relative paths
            if match.file_path.startswith('/'):
                file_path = Path(match.file_path)
            else:
                file_path = project_root / match.file_path

            if not file_path.exists():
                raise ValueError(f"File {match.file_path} does not exist")

            # Read current content
            current_content = file_path.read_text()

            # Apply the replacement
            new_content = self.find_and_replace(
                current_content, 
                match.search_text, 
                match.replace_text
            )

            # Write back to file
            file_path.write_text(new_content)
            modified_files.add(file_path)

        return list(modified_files)


def apply_diff_fenced_patch(patch_text: str, project_root: Path) -> list[Path]:
    """Convenience function to apply a diff-fenced patch."""
    patcher = DiffFencedPatcher()
    return patcher.apply_patch(patch_text, project_root)
