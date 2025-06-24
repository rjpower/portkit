"""Tests for prompt loading system."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from portkit.tidyllm.prompt import read_prompt


class TestPromptLoading:
    """Test prompt loading functionality."""

    def test_read_simple_prompt(self):
        """Test reading a simple prompt file."""
        with TemporaryDirectory() as tmpdir:
            prompt_file = Path(tmpdir) / "PROMPT.md"
            prompt_file.write_text("# Simple Prompt\n\nThis is a test prompt.")

            content = read_prompt(str(prompt_file))
            assert content == "# Simple Prompt\n\nThis is a test prompt."

    def test_read_prompt_with_include(self):
        """Test reading prompt with include directive."""
        with TemporaryDirectory() as tmpdir:
            # Create included file
            include_file = Path(tmpdir) / "include.md"
            include_file.write_text("## Included Content\n\nThis is included.")

            # Create main prompt with include
            prompt_file = Path(tmpdir) / "PROMPT.md"
            prompt_file.write_text("# Main Prompt\n\n{{include: ./include.md}}\n\n## End")

            content = read_prompt(str(prompt_file))
            expected = "# Main Prompt\n\n<file name=\"include.md\">\n## Included Content\n\nThis is included.\n</file>\n\n## End"
            assert content == expected

    def test_read_prompt_with_nested_includes(self):
        """Test reading prompt with nested includes."""
        with TemporaryDirectory() as tmpdir:
            # Create deeply nested include
            deep_file = Path(tmpdir) / "deep.md"
            deep_file.write_text("Deep content")

            # Create middle include that includes deep
            middle_file = Path(tmpdir) / "middle.md"
            middle_file.write_text("Middle: {{include: ./deep.md}}")

            # Create main prompt
            prompt_file = Path(tmpdir) / "PROMPT.md"
            prompt_file.write_text("Start {{include: ./middle.md}} End")

            content = read_prompt(str(prompt_file))
            assert content == "Start <file name=\"middle.md\">\nMiddle: <file name=\"deep.md\">\nDeep content\n</file>\n</file> End"

    def test_read_prompt_with_multiple_includes(self):
        """Test reading prompt with multiple include directives."""
        with TemporaryDirectory() as tmpdir:
            # Create multiple include files
            file1 = Path(tmpdir) / "part1.md"
            file1.write_text("Part 1")

            file2 = Path(tmpdir) / "part2.md"
            file2.write_text("Part 2")

            # Create main prompt with multiple includes
            prompt_file = Path(tmpdir) / "PROMPT.md"
            prompt_file.write_text("{{include: ./part1.md}}\n\n{{include: ./part2.md}}")

            content = read_prompt(str(prompt_file))
            assert content == "<file name=\"part1.md\">\nPart 1\n</file>\n\n<file name=\"part2.md\">\nPart 2\n</file>"

    def test_read_prompt_include_with_spaces(self):
        """Test include directive with spaces in filename."""
        with TemporaryDirectory() as tmpdir:
            # Create file with spaces in name
            include_file = Path(tmpdir) / "file with spaces.md"
            include_file.write_text("Spaced content")

            # Create main prompt
            prompt_file = Path(tmpdir) / "PROMPT.md"
            prompt_file.write_text("{{include: ./file with spaces.md}}")

            content = read_prompt(str(prompt_file))
            assert content == "<file name=\"file with spaces.md\">\nSpaced content\n</file>"

    def test_read_prompt_include_not_found(self):
        """Test error when included file doesn't exist."""
        with TemporaryDirectory() as tmpdir:
            prompt_file = Path(tmpdir) / "PROMPT.md"
            prompt_file.write_text("{{include: ./missing.md}}")

            with pytest.raises(FileNotFoundError, match="Include file not found"):
                read_prompt(str(prompt_file))

    def test_read_prompt_include_subdirectory(self):
        """Test include from subdirectory."""
        with TemporaryDirectory() as tmpdir:
            # Create subdirectory and file
            subdir = Path(tmpdir) / "prompts"
            subdir.mkdir()
            sub_file = subdir / "sub.md"
            sub_file.write_text("Sub content")

            # Create main prompt
            prompt_file = Path(tmpdir) / "PROMPT.md"
            prompt_file.write_text("{{include: ./prompts/sub.md}}")

            content = read_prompt(str(prompt_file))
            assert content == "<file name=\"sub.md\">\nSub content\n</file>"

    def test_read_prompt_relative_paths(self):
        """Test includes work with relative paths from included files."""
        with TemporaryDirectory() as tmpdir:
            # Create directory structure
            subdir = Path(tmpdir) / "sub"
            subdir.mkdir()

            # Create files
            base_file = Path(tmpdir) / "base.md"
            sub_file = subdir / "sub.md"
            nested_file = subdir / "nested.md"

            # Set up content with relative includes
            nested_file.write_text("Nested content")
            sub_file.write_text("Sub: {{include: ./nested.md}}")
            base_file.write_text("Base: {{include: ./sub/sub.md}}")

            content = read_prompt(str(base_file))
            assert content == "Base: <file name=\"sub.md\">\nSub: <file name=\"nested.md\">\nNested content\n</file>\n</file>"
