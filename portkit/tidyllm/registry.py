"""Global registry for tools."""

import inspect
import logging
import warnings
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, ParamSpec, Protocol, TypeVar, cast, overload

from portkit.tidyllm.schema import (
    FunctionDescription,
    generate_tool_schema,
)

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T", covariant=True)


class CallableWithSchema(Protocol[P, T]):
    """Generic callable with schema that preserves function signature."""

    __tool_schema__: dict
    __name__: str

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T: ...


class Registry:
    """Global registry for tools."""

    def __init__(self):
        self._tools: dict[str, FunctionDescription] = OrderedDict()

    def register(
        self,
        func: Callable,
        doc_override: str | None = None,
    ) -> None:
        """Register a tool function and generate its schema automatically.

        Args:
            func: Function to register
            doc_override: Optional documentation override
        """
        name = func.__name__

        if name in self._tools:
            # warnings.warn(
            #     f"Tool '{name}' already registered, previous definition: {self._tools[name].function.__code__.co_filename}. "
            #     f"Skipping duplicate registration from: {func.__code__.co_filename}",
            #     UserWarning,
            #     stacklevel=2,
            # )
            return

        # Create FunctionDescription once at registration time
        func_desc = FunctionDescription(func)

        # Generate schema at registration time using our improved schema generation
        schema = generate_tool_schema(func, doc_override)

        # Attach metadata to function and description
        func.__tool_schema__ = schema  # type: ignore
        func_desc.schema = schema

        self._tools[name] = func_desc
        logger.info(f"Registered tool: {name}")

    @property
    def functions(self) -> list[FunctionDescription]:
        """Get all registered tool descriptions."""
        return list(self._tools.values())

    def get(self, name: str) -> FunctionDescription | None:
        """Get a tool description by name."""
        return self._tools.get(name)

    def get_function(self, name: str) -> CallableWithSchema[..., Any]:
        """Get the raw function by name with preserved typing."""
        func_desc = self._tools.get(name)
        if func_desc is None:
            raise KeyError(f"Tool '{name}' not found")
        return cast(CallableWithSchema[..., Any], func_desc.function)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_schemas(self) -> list[dict]:
        """Get all tool schemas in OpenAI format."""
        return [func_desc.schema for func_desc in self._tools.values() if func_desc.schema]


# Global registry instance
REGISTRY = Registry()


@overload
def register(
    func_or_doc: Callable[P, T], *, doc: str | None = None, name: str | None = None
) -> CallableWithSchema[P, T]: ...


@overload
def register(
    func_or_doc: str | None = None, *, doc: str | None = None, name: str | None = None
) -> Callable[[Callable[P, T]], CallableWithSchema[P, T]]: ...


def register(
    func_or_doc: Callable[P, T] | str | None = None,
    *,
    doc: str | None = None,
    name: str | None = None,
) -> CallableWithSchema[P, T] | Callable[[Callable[P, T]], CallableWithSchema[P, T]]:
    """
    Register a function as a tool.

    Can be used with or without parentheses:
        @register
        def my_tool(...): ...

        @register()
        def my_tool(...): ...

        @register(doc="custom doc")
        def my_tool(...): ...

    Args:
        func_or_doc: Function (when used without parentheses) or doc override
        doc: Override docstring (supports read_prompt())
        name: Override tool name
    """

    def _register_func(
        func: Callable[P, T], doc_override: str | None = None
    ) -> CallableWithSchema[P, T]:
        # Override function name if provided
        if name:
            func.__name__ = name

        # Validate context parameter if present
        sig = inspect.signature(func)
        if "ctx" in sig.parameters:
            ctx_param = sig.parameters["ctx"]
            if ctx_param.kind != inspect.Parameter.KEYWORD_ONLY:
                raise ValueError("ctx parameter must be keyword-only (*, ctx)")

        # Register the function - registry will generate schema automatically
        REGISTRY.register(func, doc_override)

        # Return the function cast as CallableWithSchema to indicate it has __tool_schema__
        return cast(CallableWithSchema[P, T], func)

    # If first argument is a callable, this is direct usage (@register)
    if callable(func_or_doc):
        return _register_func(func_or_doc, doc)

    # Otherwise, this is parameterized usage (@register() or @register(doc="..."))
    def decorator(func: Callable[P, T]) -> CallableWithSchema[P, T]:
        # Use func_or_doc as doc if it's a string, otherwise use doc parameter
        doc_override = func_or_doc if isinstance(func_or_doc, str) else doc
        return _register_func(func, doc_override)

    return decorator
