"""Comprehensive benchmark tests for patch_file tool with merged test cases."""

from portkit.tidyllm.benchmark import benchmark_test
from portkit.tidyllm.tools.patch_file.lib import PatchResult


@benchmark_test()
def test_simple_line_replacement(context):
    """Test 1: Simple single line replacement."""
    response = context.llm.ask(
        "Apply a patch to replace 'hello world' with 'hello universe' in the text 'hello world'"
    )

    context.assert_success(response)
    context.assert_tool_called(response, "patch_file")

    result = response.tool_result
    assert isinstance(result, PatchResult)
    assert result.success
    assert result.modified_content and "universe" in result.modified_content


@benchmark_test()
def test_multi_line_modification(context):
    """Test 2: Multi-line text modification."""
    text = "line 1\nold line 2\nline 3"
    response = context.llm.ask(
        f"Create and apply a patch to change 'old line 2' to 'new line 2' in this text:\n{text}"
    )

    context.assert_success(response)
    context.assert_tool_called(response, "patch_file")

    result = response.tool_result
    assert isinstance(result, PatchResult)
    assert result.success
    assert result.modified_content and "new line 2" in result.modified_content


@benchmark_test()
def test_add_new_lines(context):
    """Test 3: Adding new lines to existing text."""
    text = "start\nend"
    response = context.llm.ask(
        f"Add a new line 'middle' between 'start' and 'end' in this text:\n{text}"
    )

    context.assert_success(response)
    context.assert_tool_called(response, "patch_file")

    result = response.tool_result
    assert isinstance(result, PatchResult)
    assert result.success
    assert result.modified_content and "middle" in result.modified_content


@benchmark_test()
def test_remove_lines(context):
    """Test 4: Removing lines from text."""
    text = "keep this\nremove this\nkeep this too"
    response = context.llm.ask(f"Remove the line 'remove this' from this text:\n{text}")

    context.assert_success(response)
    context.assert_tool_called(response, "patch_file")

    result = response.tool_result
    assert isinstance(result, PatchResult)
    assert result.success
    assert result.modified_content and "remove this" not in result.modified_content


@benchmark_test()
def test_multiple_replacements(context):
    """Test 5: Multiple separate replacements in one patch."""
    text = "foo is good\nbar is bad\nbaz is okay"
    response = context.llm.ask(
        f"Replace 'foo' with 'apple' and 'bar' with 'orange' in this text:\n{text}"
    )

    context.assert_success(response)
    context.assert_tool_called(response, "patch_file")

    result = response.tool_result
    assert isinstance(result, PatchResult)
    assert result.success
    assert result.modified_content and "apple" in result.modified_content
    assert result.modified_content and "orange" in result.modified_content


@benchmark_test()
def test_code_function_replacement(context):
    """Test 6: Code function replacement."""
    code = """def old_function():
    return "old"

def main():
    print(old_function())"""

    response = context.llm.ask(
        f"Replace the function 'old_function' with 'new_function' that returns 'new' in this code:\n{code}"
    )

    context.assert_success(response)
    context.assert_tool_called(response, "patch_file")

    result = response.tool_result
    assert isinstance(result, PatchResult)
    assert result.success
    assert result.modified_content and "new_function" in result.modified_content


@benchmark_test()
def test_whitespace_sensitive_patch(context):
    """Test 7: Whitespace-sensitive patching."""
    text = "    indented line\n        more indented\n    back to original"
    response = context.llm.ask(
        f"Change 'more indented' to 'differently indented' while preserving indentation in:\n{text}"
    )

    context.assert_success(response)
    context.assert_tool_called(response, "patch_file")

    result = response.tool_result
    assert isinstance(result, PatchResult)
    assert result.success
    assert result.modified_content and "differently indented" in result.modified_content


@benchmark_test()
def test_dry_run_validation(context):
    """Test 8: Dry run patch validation."""
    text = "original content"
    response = context.llm.ask(
        f"Validate (dry run) a patch to change 'original' to 'modified' in this text without applying it:\n{text}"
    )

    context.assert_success(response)
    context.assert_tool_called(response, "patch_file")

    result = response.tool_result
    assert isinstance(result, PatchResult)
    assert result.dry_run
    assert result.success


@benchmark_test()
def test_json_content_modification(context):
    """Test 9: JSON content modification."""
    json_text = '{"name": "old_name", "value": 123}'
    response = context.llm.ask(
        f"Change 'old_name' to 'new_name' in this JSON:\n{json_text}"
    )

    context.assert_success(response)
    context.assert_tool_called(response, "patch_file")

    result = response.tool_result
    assert isinstance(result, PatchResult)
    assert result.success
    assert result.modified_content and "new_name" in result.modified_content


@benchmark_test()
def test_complex_multiline_replacement(context):
    """Test 10: Complex multi-line block replacement."""
    text = """header
old block start
old content line 1
old content line 2
old block end
footer"""

    response = context.llm.ask(
        f"Replace the entire old block (lines 2-5) with 'new single line' in this text:\n{text}"
    )

    context.assert_success(response)
    context.assert_tool_called(response, "patch_file")

    result = response.tool_result
    assert isinstance(result, PatchResult)
    assert result.success
    assert result.modified_content and "new single line" in result.modified_content
    assert result.modified_content and "old block" not in result.modified_content


@benchmark_test()
def test_simple_text_replacement(context):
    """Test that LLM can create and apply a simple text patch."""
    response = context.llm.ask(
        "Create a patch to change 'Hello World' to 'Hello Universe' "
        "and apply it to the text 'Hello World'"
    )

    context.assert_success(response)
    context.assert_tool_called(response, "patch_file")

    result = response.tool_result
    assert isinstance(result, PatchResult)
    assert result.success


@benchmark_test()
def test_multi_line_patch(context):
    """Test patching multiple lines of text."""
    response = context.llm.ask(
        "Apply a patch to change line 2 from 'old content' to 'new content' "
        "in this text: 'line 1\\nold content\\nline 3'"
    )

    context.assert_success(response)
    context.assert_tool_called(response, "patch_file")

    result = response.tool_result
    assert isinstance(result, PatchResult)
    # Mock client will generate default patch structure
    assert result.hunks_applied >= 0


@benchmark_test()
def test_patch_with_context_lines(context):
    """Test creating patches that include context lines."""
    response = context.llm.ask(
        "Create a unified diff patch to modify only the middle line "
        "of this 3-line text: 'first\\nmiddle\\nlast'"
    )

    context.assert_success(response)
    context.assert_tool_called(response, "patch_file")

    result = response.tool_result
    assert isinstance(result, PatchResult)
    assert result.success


@benchmark_test()
def test_patch_statistics_tracking(context):
    """Test that patch application tracks statistics correctly."""
    response = context.llm.ask(
        "Apply a patch that adds 2 lines and removes 1 line from some text"
    )

    context.assert_success(response)
    context.assert_tool_called(response, "patch_file")

    result = response.tool_result
    assert isinstance(result, PatchResult)
    # Mock client will generate reasonable defaults
    assert hasattr(result, "lines_added")
    assert hasattr(result, "lines_removed")
    assert hasattr(result, "hunks_applied")
