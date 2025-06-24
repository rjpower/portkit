"""Tests for patch_file tool."""

import os
import tempfile

import pytest

from portkit.tidyllm import REGISTRY
from portkit.tidyllm.tools.patch_file import patch_file
from portkit.tidyllm.tools.patch_file.lib import (
    PatchArgs,
    PatchResult,
    apply_patch,
    parse_unified_diff,
)


class TestPatchFileLib:
    """Test core patch file functionality."""

    def test_parse_simple_diff(self):
        """Test parsing a simple unified diff."""
        patch_content = """--- a/test.txt
+++ b/test.txt
@@ -1,2 +1,2 @@
-old line
+new line
 unchanged line"""

        hunks = parse_unified_diff(patch_content)
        assert len(hunks) == 1

        hunk = hunks[0]
        assert hunk["old_start"] == 1
        assert hunk["old_count"] == 2
        assert hunk["new_start"] == 1
        assert hunk["new_count"] == 2
        assert len(hunk["changes"]) == 3

        changes = hunk["changes"]
        assert changes[0] == ("remove", "old line")
        assert changes[1] == ("add", "new line")
        assert changes[2] == ("context", "unchanged line")

    def test_inline_patch_success(self):
        """Test successful inline text patching."""
        patch_content = """@@ -1,2 +1,2 @@
-old line
+new line
 unchanged line"""

        target_text = "old line\nunchanged line"

        args = PatchArgs(patch_content=patch_content, target_text=target_text)

        result = apply_patch(args)

        assert isinstance(result, PatchResult)
        assert result.success
        assert result.modified_content == "new line\nunchanged line"
        assert result.lines_added == 1
        assert result.lines_removed == 1
        assert result.hunks_applied == 1
        assert not result.dry_run

    def test_dry_run_patch(self):
        """Test dry run patch validation."""
        patch_content = """@@ -1 +1 @@
-hello
+world"""

        args = PatchArgs(patch_content=patch_content, target_text="hello", dry_run=True)

        result = apply_patch(args)

        assert result.success
        assert result.modified_content == "world"
        assert result.dry_run
        assert "DRY RUN" in result.patch_summary

    def test_multiple_hunks(self):
        """Test patch with multiple hunks."""
        patch_content = """@@ -1 +1 @@
-line 1
+modified line 1
@@ -3 +3 @@
-line 3
+modified line 3"""

        target_text = "line 1\nline 2\nline 3"

        args = PatchArgs(patch_content=patch_content, target_text=target_text)

        result = apply_patch(args)

        assert result.success
        assert result.modified_content == "modified line 1\nline 2\nmodified line 3"
        assert result.hunks_applied == 2
        assert result.lines_added == 2
        assert result.lines_removed == 2

    def test_patch_mismatch_failure(self):
        """Test patch failure when content doesn't match."""
        patch_content = """@@ -1 +1 @@
-expected line
+new line"""

        # Target doesn't match what patch expects
        target_text = "different line"

        args = PatchArgs(patch_content=patch_content, target_text=target_text)

        with pytest.raises(ValueError, match="Failed to apply hunk"):
            apply_patch(args)

    def test_empty_patch_failure(self):
        """Test failure with empty patch content."""
        args = PatchArgs(patch_content="", target_text="some text")

        with pytest.raises(ValueError, match="Patch content cannot be empty"):
            apply_patch(args)

    def test_missing_targets_failure(self):
        """Test failure when neither target_text nor target_file provided."""
        args = PatchArgs(patch_content="@@ -1 +1 @@\n-a\n+b")

        with pytest.raises(
            ValueError, match="Either target_text or target_file must be provided"
        ):
            apply_patch(args)

    def test_both_targets_failure(self):
        """Test failure when both target_text and target_file provided."""
        args = PatchArgs(
            patch_content="@@ -1 +1 @@\n-a\n+b", target_text="a", target_file="file.txt"
        )

        with pytest.raises(
            ValueError, match="Cannot specify both target_text and target_file"
        ):
            apply_patch(args)


class TestPatchFileTool:
    """Test patch_file tool registration and execution."""

    def test_tool_registered(self):
        """Test that patch_file tool is properly registered."""
        tool = REGISTRY.get("patch_file")
        assert tool is not None
        assert tool.name == "patch_file"

        # Check tool has schema attached
        assert hasattr(patch_file, "__tool_schema__")
        schema = patch_file.__tool_schema__
        assert schema["function"]["name"] == "patch_file"
        assert "patch_content" in schema["function"]["parameters"]["properties"]

    def test_tool_execution_success(self):
        """Test successful tool execution."""
        patch_content = """@@ -1 +1 @@
-hello
+hi"""

        args = PatchArgs(patch_content=patch_content, target_text="hello")

        result = patch_file(args)

        assert isinstance(result, PatchResult)
        assert result.success
        assert result.modified_content == "hi"

    def test_tool_execution_error(self):
        """Test tool execution with error."""
        args = PatchArgs(patch_content="invalid patch content", target_text="some text")

        with pytest.raises(ValueError, match="No valid hunks found in patch content"):
            patch_file(args)

    def test_schema_generation(self):
        """Test that schema is generated correctly."""
        schema = patch_file.__tool_schema__

        # Check basic structure
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "patch_file"

        # Check parameters
        params = schema["function"]["parameters"]["properties"]

        # Check required parameter
        assert "patch_content" in params
        assert params["patch_content"]["type"] == "string"

        # Check optional parameters
        assert "target_text" in params
        assert "target_file" in params
        assert "dry_run" in params

        # Check required parameters
        required = schema["function"]["parameters"]["required"]
        assert "patch_content" in required


class TestPatchFileIntegration:
    """Test patch_file integration with FunctionLibrary and file operations."""

    def test_library_execution(self):
        """Test patch_file execution through FunctionLibrary."""
        from portkit.tidyllm import FunctionLibrary

        library = FunctionLibrary(functions=[patch_file])

        result = library.call(
            {
                "name": "patch_file",
                "arguments": {
                    "patch_content": "@@ -1 +1 @@\n-old\n+new",
                    "target_text": "old",
                },
            }
        )

        assert isinstance(result, PatchResult)
        assert result.success
        assert result.modified_content == "new"

    def test_file_based_patching(self):
        """Test patching actual files."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp:
            tmp.write("original content\nline 2")
            tmp_path = tmp.name

        try:
            patch_content = """@@ -1 +1 @@
-original content
+modified content"""

            args = PatchArgs(patch_content=patch_content, target_file=tmp_path)

            result = apply_patch(args)

            assert result.success
            assert result.modified_file == tmp_path

            # Verify file was modified
            with open(tmp_path) as f:
                content = f.read()
                assert content == "modified content\nline 2"

        finally:
            os.unlink(tmp_path)

    def test_nonexistent_file_error(self):
        """Test error handling for nonexistent files."""
        args = PatchArgs(
            patch_content="@@ -1 +1 @@\n-a\n+b", target_file="/nonexistent/file.txt"
        )

        with pytest.raises(ValueError, match="Target file does not exist"):
            apply_patch(args)
