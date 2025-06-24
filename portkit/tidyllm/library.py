"""Function library for tools with shared context."""

import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from portkit.tidyllm.models import ToolError
from portkit.tidyllm.registry import REGISTRY
from portkit.tidyllm.schema import FunctionDescription

logger = logging.getLogger(__name__)


class FunctionLibrary:
    """Container for tools with shared context."""

    def __init__(
        self,
        functions: list[Callable] | None = None,
        function_descriptions: list[FunctionDescription] | None = None,
        context: Any | None = None,
        registry=None,
    ):
        """
        Initialize library.

        Args:
            functions: List of functions with __tool_schema__ attribute
            function_descriptions: List of FunctionDescription objects to use
            context: Shared context dict
            registry: Registry to use (defaults to global REGISTRY)
        """
        self.context = context or {}
        self.registry = registry or REGISTRY

        # Create own function dictionary for faster lookups
        self._function_descriptions: dict[str, FunctionDescription] = {}

        if function_descriptions:
            # Use provided FunctionDescription objects directly
            for func_desc in function_descriptions:
                self._function_descriptions[func_desc.name] = func_desc
        elif functions:
            # Create FunctionDescriptions from functions with schemas
            for func in functions:
                if not hasattr(func, "__tool_schema__"):
                    raise ValueError(
                        f"Function {func.__name__} must have __tool_schema__ attribute"
                    )
                func_desc = FunctionDescription(func)
                func_desc.schema = func.__tool_schema__
                self._function_descriptions[func.__name__] = func_desc
        else:
            # Default: use all functions from the registry
            for func_desc in self.registry.functions:
                self._function_descriptions[func_desc.name] = func_desc

    def call(self, tool_name: str, arguments: dict) -> Any:
        """
        Execute a function call with JSON arguments.

        Args:
            tool_name: Name of the function to call
            arguments: JSON dictionary of arguments

        Returns:
            Result from the function call
        """
        logger.info(f"Calling tool: {tool_name} with arguments: {arguments}")

        # Get tool description from internal dictionary
        func_desc = self._function_descriptions.get(tool_name)
        if not func_desc:
            error = f"Tool '{tool_name}' not found"
            logger.error(error)
            return ToolError(error=error)

        # Use pre-created FunctionDescription for validation
        try:
            call_kwargs = func_desc.validate_and_parse_args(arguments)
        except ValidationError as e:
            error = f"Invalid arguments: {e}"
            logger.error(error)
            return ToolError(error=error, details={"validation_errors": e.errors()})
        except Exception as e:
            error = f"Invalid arguments: {str(e)}"
            logger.error(error)
            return ToolError(error=error)

        # Check if tool needs context
        needs_context = func_desc.takes_ctx

        if needs_context:
            # Validate context satisfies tool requirements
            context_type = func_desc.context_type
            if context_type:
                if hasattr(context_type, "__annotations__"):
                    for attr_name in context_type.__annotations__:
                        if not hasattr(self.context, attr_name):
                            error = f"Context missing required attribute: {attr_name}"
                            logger.error(error, stack_info=True)
                            return ToolError(error=error)

        try:
            if needs_context:
                # Convert dict context to object with attributes
                if isinstance(self.context, dict):

                    class ContextObject:
                        def __init__(self, data):
                            for key, value in data.items():
                                setattr(self, key, value)

                    context_obj = ContextObject(self.context)
                else:
                    context_obj = self.context

                result = func_desc.function(**call_kwargs, ctx=context_obj)
            else:
                result = func_desc.function(**call_kwargs)

            logger.info(f"Tool {tool_name} completed successfully")
            return result

        except Exception as e:
            error = f"Tool execution failed: {str(e)}"
            logger.exception(e, stack_info=True)
            return ToolError(error=error)

    @property
    def function_descriptions(self) -> list[FunctionDescription]:
        """Get all function descriptions."""
        return list(self._function_descriptions.values())

    def get_schemas(self) -> list[dict]:
        """Get OpenAI-format schemas for all tools."""
        return [
            func_desc.schema
            for func_desc in self._function_descriptions.values()
            if func_desc.schema
        ]

    def validate_context(self, tool_name: str) -> bool:
        """Check if context satisfies tool requirements."""
        func_desc = self._function_descriptions.get(tool_name)
        if not func_desc:
            return False

        context_type = func_desc.context_type
        if not context_type:
            return True

        # For Protocol types, check annotations instead of dir()
        if hasattr(context_type, "__annotations__"):
            for attr_name in context_type.__annotations__:
                if not hasattr(self.context, attr_name):
                    return False

        return True

    def call_with_tool_response(self, name: str, args: dict, id: str) -> dict:
        """Execute a tool call, returning a tool call message with the result or error."""
        try:
            result = self.call(name, args)
            if isinstance(result, BaseModel):
                result = result.model_dump()

            return {
                "role": "tool",
                "tool_call_id": id,
                "content": json.dumps(result),
            }
        except Exception as e:
            logger.exception(e, stack_info=True)
            return {
                "role": "tool",
                "tool_call_id": id,
                "content": json.dumps({"error": str(e), "type": type(e).__name__}),
            }
