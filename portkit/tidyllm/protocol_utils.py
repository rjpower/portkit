"""Utilities for extracting field information from Protocol classes."""

from pathlib import Path
from typing import Any, get_type_hints


def get_protocol_fields(protocol_type: type) -> dict[str, type]:
    """Extract field names and types from a Protocol class.

    Returns:
        Dictionary mapping field names to their types
    """
    if not hasattr(protocol_type, "__annotations__"):
        return {}

    # Get type hints for the protocol
    try:
        type_hints = get_type_hints(protocol_type)
    except (NameError, AttributeError):
        # Fallback to __annotations__ if get_type_hints fails
        type_hints = getattr(protocol_type, "__annotations__", {})

    # Filter out methods and properties - only include simple attributes
    fields = {}
    for name, type_hint in type_hints.items():
        if not name.startswith("_"):  # Skip private attributes
            fields[name] = type_hint

    return fields


def get_cli_type_for_annotation(annotation: type) -> tuple[str, bool]:
    """Get the appropriate CLI type and whether it's a flag for a type annotation.

    Returns:
        Tuple of (click_type, is_flag)
    """
    # Handle common types
    if annotation is bool:
        return ("bool", True)
    elif annotation is int:
        return ("int", False)
    elif annotation is float:
        return ("float", False)
    elif annotation is str:
        return ("str", False)
    elif annotation is Path or annotation == Path:
        return ("path", False)
    elif hasattr(annotation, "__origin__"):
        # Handle generic types like list[str], set[str], etc.
        origin = getattr(annotation, "__origin__", None)
        if origin is list or origin is set:
            return ("str", False)  # Will be split by comma

    # Default to string for unknown types
    return ("str", False)


def create_context_from_cli_args(protocol_type: type, cli_args: dict[str, Any]) -> Any:
    """Create a context which matches `protocol_type` from CLI arguments.

    Args:
        protocol_type: The Protocol class defining the context interface
        cli_args: Dictionary of CLI arguments with ctx_ prefix stripped

    Returns:
        Mock context object with the specified attributes
    """

    class CliProtocol:
        pass

    context = CliProtocol()

    # Get expected fields from the protocol
    fields = get_protocol_fields(protocol_type)

    # Set attributes based on CLI args, with type conversion
    for field_name, field_type in fields.items():
        cli_value = cli_args.get(field_name)
        if cli_value is not None:
            # Convert CLI string values to appropriate types
            if field_type is bool:
                # Boolean flags are already handled by Click
                setattr(context, field_name, cli_value)
            elif field_type is int:
                setattr(context, field_name, int(cli_value))
            elif field_type is float:
                setattr(context, field_name, float(cli_value))
            elif field_type is Path or field_type == Path:
                setattr(context, field_name, Path(cli_value))
            elif hasattr(field_type, "__origin__"):
                # Handle generic types like set[str]
                origin = getattr(field_type, "__origin__", None)
                if origin is set:
                    # Split comma-separated values into a set
                    setattr(context, field_name, set(cli_value.split(",")))
                elif origin is list:
                    # Split comma-separated values into a list
                    setattr(context, field_name, cli_value.split(","))
                else:
                    setattr(context, field_name, cli_value)
            else:
                setattr(context, field_name, cli_value)
        else:
            # Set default values for missing fields
            if field_type is bool:
                setattr(context, field_name, False)
            elif field_type is str:
                setattr(context, field_name, "")
            elif field_type is Path or field_type == Path:
                setattr(context, field_name, Path("."))
            elif hasattr(field_type, "__origin__"):
                origin = getattr(field_type, "__origin__", None)
                if origin is set:
                    setattr(context, field_name, set())
                elif origin is list:
                    setattr(context, field_name, [])
                else:
                    setattr(context, field_name, None)
            else:
                setattr(context, field_name, None)

    return context
