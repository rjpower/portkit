"""Tests for CLI generation."""

import json
from typing import Protocol
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from pydantic import BaseModel

from portkit.tidyllm.cli import generate_cli


class SimpleArgs(BaseModel):
    """Simple test arguments."""

    name: str
    count: int = 5
    flag: bool = False


class ComplexArgs(BaseModel):
    """Complex test arguments."""

    items: list[str]
    config: dict[str, str] = {}
    optional_value: int | None = None


class CLITestContext(Protocol):
    """Test context for CLI tests."""

    project_root: str


def simple_tool(args: SimpleArgs) -> dict:
    """A simple test tool."""
    return {"message": f"Hello {args.name}", "count": args.count, "flag": args.flag}


def context_tool(args: SimpleArgs, *, ctx: CLITestContext) -> dict:
    """Tool that requires context."""
    return {"message": f"Hello {args.name} from {ctx.project_root}"}


def complex_tool(args: ComplexArgs) -> dict:
    """Tool with complex arguments."""
    return {"items": args.items, "config": args.config}


class TestCLIGeneration:
    """Test CLI generation functionality."""

    def test_generate_cli_basic(self):
        """Test generating CLI for simple tool."""
        cli_command = generate_cli(simple_tool)

        assert cli_command.name == "simple_tool"
        assert cli_command.help is not None
        # Check that CLI was created successfully
        assert callable(cli_command)

    def test_cli_execution_with_individual_args(self):
        """Test executing CLI with individual arguments."""
        cli_command = generate_cli(simple_tool)
        runner = CliRunner()

        result = runner.invoke(cli_command, ["--name", "test", "--count", "10", "--flag"])

        if result.exit_code != 0:
            print(f"CLI Error: {result.output}")
            print(f"Exception: {result.exception}")
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["message"] == "Hello test"
        assert output["count"] == 10
        assert output["flag"] is True

    def test_cli_execution_with_defaults(self):
        """Test CLI execution using default values."""
        cli_command = generate_cli(simple_tool)
        runner = CliRunner()

        result = runner.invoke(cli_command, ["--name", "test"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["message"] == "Hello test"
        assert output["count"] == 5  # default value
        assert output["flag"] is False  # default value

    def test_cli_execution_with_json_input(self):
        """Test CLI execution with JSON input."""
        cli_command = generate_cli(simple_tool)
        runner = CliRunner()

        json_input = json.dumps({"name": "json_test", "count": 15, "flag": True})

        result = runner.invoke(cli_command, ["--json", json_input])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["message"] == "Hello json_test"
        assert output["count"] == 15
        assert output["flag"] is True

    def test_cli_json_overrides_individual_args(self):
        """Test that JSON input takes precedence over individual args."""
        cli_command = generate_cli(simple_tool)
        runner = CliRunner()

        json_input = json.dumps({"name": "json_name", "count": 20})

        result = runner.invoke(
            cli_command,
            ["--json", json_input, "--name", "ignored_name", "--count", "999"],
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["message"] == "Hello json_name"
        assert output["count"] == 20

    def test_cli_invalid_json_input(self):
        """Test CLI with invalid JSON input."""
        cli_command = generate_cli(simple_tool)
        runner = CliRunner()

        result = runner.invoke(cli_command, ["--json", "invalid json"])

        assert result.exit_code == 0  # Should handle gracefully
        output = json.loads(result.output)
        assert "error" in output

    def test_cli_missing_required_arguments(self):
        """Test CLI with missing required arguments."""
        cli_command = generate_cli(simple_tool)
        runner = CliRunner()

        result = runner.invoke(cli_command, ["--count", "10"])  # Missing required 'name'

        assert result.exit_code == 0  # Should handle gracefully
        output = json.loads(result.output)
        assert "error" in output
        # Pydantic validation error format includes "validation error"
        assert "validation error" in output["error"]

    def test_cli_with_context_tool(self):
        """Test CLI generation for tool that requires context."""
        cli_command = generate_cli(context_tool)
        runner = CliRunner()

        result = runner.invoke(cli_command, ["--name", "context_test"])

        if result.exit_code != 0:
            print(f"CLI Error: {result.output}")
            print(f"Exception: {result.exception}")
        assert result.exit_code == 0
        output = json.loads(result.output)
        # Should create minimal context and access project_root
        assert "Hello context_test from" in output["message"]

    def test_cli_complex_arguments(self):
        """Test CLI with complex argument types."""
        cli_command = generate_cli(complex_tool)
        runner = CliRunner()

        json_input = json.dumps(
            {
                "items": ["item1", "item2", "item3"],
                "config": {"key1": "value1", "key2": "value2"},
                "optional_value": 42,
            }
        )

        result = runner.invoke(cli_command, ["--json", json_input])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["items"] == ["item1", "item2", "item3"]
        assert output["config"] == {"key1": "value1", "key2": "value2"}

    def test_cli_tool_execution_error(self):
        """Test CLI when tool execution fails."""

        def failing_tool(args: SimpleArgs) -> dict:
            """Tool that always fails."""
            raise RuntimeError("Tool execution failed")

        cli_command = generate_cli(failing_tool)
        runner = CliRunner()

        result = runner.invoke(cli_command, ["--name", "test"])

        assert result.exit_code == 0  # Should handle gracefully
        output = json.loads(result.output)
        assert "error" in output
        assert "Tool execution failed" in output["error"]

    def test_cli_no_pydantic_args_model(self):
        """Test CLI generation for tool with non-Pydantic multiple args."""

        def multi_arg_tool(name: str, count: int = 5) -> dict:
            """Tool with non-Pydantic args."""
            return {"name": name, "count": count}

        # Should succeed now since we support multiple parameters
        cli_command = generate_cli(multi_arg_tool)
        assert cli_command is not None
        assert cli_command.name == "multi_arg_tool"

    def test_cli_option_name_transformation(self):
        """Test that underscores in field names become dashes in CLI options."""

        class ArgsWithUnderscore(BaseModel):
            field_with_underscore: str
            another_field: int = 10

        def underscore_tool(args: ArgsWithUnderscore) -> dict:
            """Tool with underscore fields."""
            return {"field": args.field_with_underscore, "another": args.another_field}

        cli_command = generate_cli(underscore_tool)
        runner = CliRunner()

        result = runner.invoke(
            cli_command,
            ["--field-with-underscore", "test_value", "--another-field", "20"],
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["field"] == "test_value"
        assert output["another"] == 20

    def test_cli_help_includes_descriptions(self):
        """Test that CLI help includes field descriptions."""

        class DocumentedArgs(BaseModel):
            name: str  # Should get description from field info
            count: int = 5

        # Add field descriptions
        DocumentedArgs.model_fields["name"].description = "The name parameter"
        DocumentedArgs.model_fields["count"].description = "Number of items"

        def documented_tool(args: DocumentedArgs) -> dict:
            """Well documented tool."""
            return {"name": args.name, "count": args.count}

        cli_command = generate_cli(documented_tool)
        runner = CliRunner()

        result = runner.invoke(cli_command, ["--help"])

        assert result.exit_code == 0
        assert "The name parameter" in result.output
        assert "Number of items" in result.output

    def test_cli_basemodel_result_serialization(self):
        """Test that BaseModel results are properly serialized."""

        class ResultModel(BaseModel):
            status: str
            data: dict

        def model_result_tool(args: SimpleArgs) -> ResultModel:
            """Tool that returns BaseModel."""
            return ResultModel(status="success", data={"name": args.name, "count": args.count})

        cli_command = generate_cli(model_result_tool)
        runner = CliRunner()

        result = runner.invoke(cli_command, ["--name", "test"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["status"] == "success"
        assert output["data"]["name"] == "test"
        assert output["data"]["count"] == 5

    @patch("portkit.tidyllm.schema.inspect.signature")
    def test_cli_generation_signature_inspection(self, mock_signature):
        """Test that CLI generation properly inspects function signature."""
        # Mock the signature inspection in the schema module
        mock_sig = MagicMock()
        mock_sig.parameters = {
            "args": MagicMock(annotation=SimpleArgs),
            "ctx": MagicMock(annotation=CLITestContext),
        }
        mock_signature.return_value = mock_sig

        cli_command = generate_cli(simple_tool)

        # Verify signature was inspected (now happens in FunctionDescription)
        assert mock_signature.called
        assert cli_command is not None
