"""CLI generation from function signatures."""

import json
from collections.abc import Callable
from typing import Any

import click
from pydantic import BaseModel

from portkit.tidyllm.protocol_utils import (
    create_context_from_cli_args,
    get_cli_type_for_annotation,
    get_protocol_fields,
)
from portkit.tidyllm.schema import FunctionDescription


class CliOption:
    """Represents a CLI option configuration."""

    def __init__(
        self,
        name: str,
        param_name: str,
        type_annotation: type,
        help_text: str,
        is_flag: bool = False,
        multiple: bool = False,
    ):
        self.name = name
        self.param_name = param_name
        self.type_annotation = type_annotation
        self.help_text = help_text
        self.is_flag = is_flag
        self.multiple = multiple


def create_click_option(option: CliOption):
    """Create a Click option decorator from a CliOption configuration."""
    if option.is_flag:
        return click.option(option.name, option.param_name, is_flag=True, help=option.help_text)
    elif option.multiple:
        return click.option(
            option.name,
            option.param_name,
            multiple=True,
            help=f"{option.help_text} (can be specified multiple times)",
        )
    else:
        # Map type annotations to Click types
        click_type = str  # Default
        cli_type, _ = get_cli_type_for_annotation(option.type_annotation)
        if cli_type == "int":
            click_type = int
        elif cli_type == "float":
            click_type = float
        elif cli_type == "path":
            click_type = click.Path(exists=False)

        return click.option(option.name, option.param_name, type=click_type, help=option.help_text)


def collect_function_options(func_desc: FunctionDescription) -> list[CliOption]:
    """Collect CLI options from function arguments."""
    options = []

    for field_name, field_info in func_desc.args_model.model_fields.items():
        option_name = f"--{field_name.replace('_', '-')}"
        param_name = field_name.replace("-", "_")
        help_text = field_info.description or f"Value for {field_name}"
        field_annotation = field_info.annotation

        # Determine option type
        is_flag = field_annotation is bool
        is_list = hasattr(field_annotation, "__origin__") and field_annotation.__origin__ is list

        options.append(
            CliOption(
                name=option_name,
                param_name=param_name,
                type_annotation=field_annotation,
                help_text=help_text,
                is_flag=is_flag,
                multiple=is_list,
            )
        )

    return options


def collect_context_options(func_desc: FunctionDescription) -> list[CliOption]:
    """Collect CLI options from context protocol fields."""
    options = []

    if func_desc.takes_ctx and func_desc.context_type:
        ctx_fields = get_protocol_fields(func_desc.context_type)
        for field_name, field_type in ctx_fields.items():
            option_name = f"--ctx-{field_name.replace('_', '-')}"
            param_name = f"ctx_{field_name}"
            help_text = f"Context field: {field_name} ({field_type.__name__ if hasattr(field_type, '__name__') else str(field_type)})"

            _, is_flag = get_cli_type_for_annotation(field_type)

            options.append(
                CliOption(
                    name=option_name,
                    param_name=param_name,
                    type_annotation=field_type,
                    help_text=help_text,
                    is_flag=is_flag,
                    multiple=False,
                )
            )

    return options


def parse_cli_arguments(
    kwargs: dict[str, Any], func_options: list[CliOption], ctx_options: list[CliOption]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse CLI arguments into function args and context args."""
    args_dict = {}
    ctx_args = {}

    # Parse function arguments
    for option in func_options:
        value = kwargs.get(option.param_name)
        if value is not None:
            if option.multiple and isinstance(value, tuple):
                # Convert tuple from click multiple option to list
                args_dict[option.param_name] = list(value)
            else:
                args_dict[option.param_name] = value

    # Parse context arguments
    for option in ctx_options:
        value = kwargs.get(option.param_name)
        if value is not None:
            # Remove 'ctx_' prefix for context field name
            ctx_field_name = option.param_name[4:]
            ctx_args[ctx_field_name] = value

    return args_dict, ctx_args


def generate_cli(func: Callable) -> click.Command:
    """Generate a Click CLI for a registered tool using FunctionDescription."""
    func_desc = FunctionDescription(func)
    return _generate_cli_from_description(func_desc)


def cli_main(func: Callable):
    generate_cli(func)()


def _generate_cli_from_description(func_desc: FunctionDescription) -> click.Command:
    """Generate CLI from a FunctionDescription."""

    # Collect all CLI options
    func_options = collect_function_options(func_desc)
    ctx_options = collect_context_options(func_desc)
    all_options = func_options + ctx_options

    @click.command(name=func_desc.name)
    @click.option("--json", "json_input", help="JSON input for all arguments")
    def cli(json_input: str | None, **kwargs):
        """Auto-generated CLI for tool."""
        if json_input:
            # Parse JSON input
            try:
                args_dict = json.loads(json_input)
                ctx_args = {}  # JSON mode doesn't support context args
            except json.JSONDecodeError as e:
                click.echo(json.dumps({"error": f"Invalid JSON: {str(e)}"}))
                return
        else:
            # Parse CLI arguments using helper function
            args_dict, ctx_args = parse_cli_arguments(kwargs, func_options, ctx_options)

        # Create context from CLI arguments if needed
        context = None
        if func_desc.takes_ctx:
            context = create_context_from_cli_args(func_desc.context_type, ctx_args)

        # Execute tool using FunctionDescription
        try:
            result = func_desc.call_with_json_args(args_dict, context)

            # Output as JSON
            if isinstance(result, BaseModel):
                output = result.model_dump()
            else:
                output = result

            click.echo(json.dumps(output))

        except Exception as e:
            click.echo(json.dumps({"error": str(e)}))

    # Add all CLI options using helper function
    for option in all_options:
        cli_option = create_click_option(option)
        cli = cli_option(cli)

    return cli
