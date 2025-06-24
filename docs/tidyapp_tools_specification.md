# TidyApp/Tools Specification

## Overview

TidyApp/Tools is a tool library and registration system for working with LLM tool calls. It provides type-safe function registration, automatic JSON schema generation, context injection, and CLI generation for testing.

## Implementation (Dependency Order)

### 1. Core Models (`tidyapp/tools/models.py`)

```python
from pydantic import BaseModel
from typing import Any, Union

class ToolError(BaseModel):
    """Error response from a tool."""
    error: str
    details: dict[str, Any] | None = None

# Tool results can be errors or any JSON-serializable success value
ToolResult = Union[ToolError, Any]
```

### 2. Prompt Loading (`tidyapp/tools/prompt.py`)

```python
import re
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=128)
def read_prompt(path: str) -> str:
    """
    Read a PROMPT.md file and process {{include:}} directives.
    
    Example:
        # Main prompt
        {{include: ./sub_prompt.md}}
    """
    base_path = Path(path).parent
    content = Path(path).read_text()
    
    # Process includes recursively
    def process_includes(text: str, current_path: Path) -> str:
        pattern = r'\{\{include:\s*([^}]+)\}\}'
        
        def replace_include(match):
            include_path = current_path / match.group(1).strip()
            if not include_path.exists():
                raise FileNotFoundError(f"Include file not found: {include_path}")
            
            included_content = include_path.read_text()
            # Recursively process includes in the included file
            return process_includes(included_content, include_path.parent)
        
        return re.sub(pattern, replace_include, text)
    
    return process_includes(content, base_path)
```

### 3. Schema Extraction (`tidyapp/tools/schema.py`)

Reference https://raw.githubusercontent.com/pydantic/pydantic-ai/a25eb963a54e07afeab5ca2ea143437225100638/pydantic_ai_slim/pydantic_ai/_function_schema.py for some ideas on how to implement:

<code>
"""Used to build pydantic validators and JSON schemas from functions.

This module has to use numerous internal Pydantic APIs and is therefore brittle to changes in Pydantic.
"""

from __future__ import annotations as _annotations

from collections.abc import Awaitable
from dataclasses import dataclass, field
from inspect import Parameter, signature
from typing import TYPE_CHECKING, Any, Callable, Union, cast

from pydantic import ConfigDict
from pydantic._internal import _decorators, _generate_schema, _typing_extra
from pydantic._internal._config import ConfigWrapper
from pydantic.fields import FieldInfo
from pydantic.json_schema import GenerateJsonSchema
from pydantic.plugin._schema_validator import create_schema_validator
from pydantic_core import SchemaValidator, core_schema
from typing_extensions import Concatenate, ParamSpec, TypeIs, TypeVar, get_origin

from pydantic_ai.tools import RunContext

from ._griffe import doc_descriptions
from ._utils import check_object_json_schema, is_async_callable, is_model_like, run_in_executor

if TYPE_CHECKING:
    from .tools import DocstringFormat, ObjectJsonSchema


__all__ = ('function_schema',)


@dataclass
class FunctionSchema:
    """Internal information about a function schema."""

    function: Callable[..., Any]
    description: str
    validator: SchemaValidator
    json_schema: ObjectJsonSchema
    # if not None, the function takes a single by that name (besides potentially `info`)
    takes_ctx: bool
    is_async: bool
    single_arg_name: str | None = None
    positional_fields: list[str] = field(default_factory=list)
    var_positional_field: str | None = None

    async def call(self, args_dict: dict[str, Any], ctx: RunContext[Any]) -> Any:
        args, kwargs = self._call_args(args_dict, ctx)
        if self.is_async:
            function = cast(Callable[[Any], Awaitable[str]], self.function)
            return await function(*args, **kwargs)
        else:
            function = cast(Callable[[Any], str], self.function)
            return await run_in_executor(function, *args, **kwargs)

    def _call_args(
        self,
        args_dict: dict[str, Any],
        ctx: RunContext[Any],
    ) -> tuple[list[Any], dict[str, Any]]:
        if self.single_arg_name:
            args_dict = {self.single_arg_name: args_dict}

        args = [ctx] if self.takes_ctx else []
        for positional_field in self.positional_fields:
            args.append(args_dict.pop(positional_field))  # pragma: no cover
        if self.var_positional_field:
            args.extend(args_dict.pop(self.var_positional_field))

        return args, args_dict


def function_schema(  # noqa: C901
    function: Callable[..., Any],
    schema_generator: type[GenerateJsonSchema],
    takes_ctx: bool | None = None,
    docstring_format: DocstringFormat = 'auto',
    require_parameter_descriptions: bool = False,
) -> FunctionSchema:
    """Build a Pydantic validator and JSON schema from a tool function.

    Args:
        function: The function to build a validator and JSON schema for.
        takes_ctx: Whether the function takes a `RunContext` first argument.
        docstring_format: The docstring format to use.
        require_parameter_descriptions: Whether to require descriptions for all tool function parameters.
        schema_generator: The JSON schema generator class to use.

    Returns:
        A `FunctionSchema` instance.
    """
    if takes_ctx is None:
        takes_ctx = _takes_ctx(function)

    config = ConfigDict(title=function.__name__, use_attribute_docstrings=True)
    config_wrapper = ConfigWrapper(config)
    gen_schema = _generate_schema.GenerateSchema(config_wrapper)

    sig = signature(function)

    type_hints = _typing_extra.get_function_type_hints(function)

    var_kwargs_schema: core_schema.CoreSchema | None = None
    fields: dict[str, core_schema.TypedDictField] = {}
    positional_fields: list[str] = []
    var_positional_field: str | None = None
    errors: list[str] = []
    decorators = _decorators.DecoratorInfos()

    description, field_descriptions = doc_descriptions(function, sig, docstring_format=docstring_format)

    if require_parameter_descriptions:
        if takes_ctx:
            parameters_without_ctx = set(
                name for name in sig.parameters if not _is_call_ctx(sig.parameters[name].annotation)
            )
            missing_params = parameters_without_ctx - set(field_descriptions)
        else:
            missing_params = set(sig.parameters) - set(field_descriptions)

        if missing_params:
            errors.append(f'Missing parameter descriptions for {", ".join(missing_params)}')

    for index, (name, p) in enumerate(sig.parameters.items()):
        if p.annotation is sig.empty:
            if takes_ctx and index == 0:
                # should be the `context` argument, skip
                continue
            # TODO warn?
            annotation = Any
        else:
            annotation = type_hints[name]

            if index == 0 and takes_ctx:
                if not _is_call_ctx(annotation):
                    errors.append('First parameter of tools that take context must be annotated with RunContext[...]')
                continue
            elif not takes_ctx and _is_call_ctx(annotation):
                errors.append('RunContext annotations can only be used with tools that take context')
                continue
            elif index != 0 and _is_call_ctx(annotation):
                errors.append('RunContext annotations can only be used as the first argument')
                continue

        field_name = p.name
        if p.kind == Parameter.VAR_KEYWORD:
            var_kwargs_schema = gen_schema.generate_schema(annotation)
        else:
            if p.kind == Parameter.VAR_POSITIONAL:
                annotation = list[annotation]

            # FieldInfo.from_annotation expects a type, `annotation` is Any
            annotation = cast(type[Any], annotation)
            field_info = FieldInfo.from_annotation(annotation)
            if field_info.description is None:
                field_info.description = field_descriptions.get(field_name)

            fields[field_name] = td_schema = gen_schema._generate_td_field_schema(  # pyright: ignore[reportPrivateUsage]
                field_name,
                field_info,
                decorators,
                required=p.default is Parameter.empty,
            )
            # noinspection PyTypeChecker
            td_schema.setdefault('metadata', {})['is_model_like'] = is_model_like(annotation)

            if p.kind == Parameter.POSITIONAL_ONLY:
                positional_fields.append(field_name)
            elif p.kind == Parameter.VAR_POSITIONAL:
                var_positional_field = field_name

    if errors:
        from .exceptions import UserError

        error_details = '\n  '.join(errors)
        raise UserError(f'Error generating schema for {function.__qualname__}:\n  {error_details}')

    core_config = config_wrapper.core_config(None)
    # noinspection PyTypedDict
    core_config['extra_fields_behavior'] = 'allow' if var_kwargs_schema else 'forbid'

    schema, single_arg_name = _build_schema(fields, var_kwargs_schema, gen_schema, core_config)
    schema = gen_schema.clean_schema(schema)
    # noinspection PyUnresolvedReferences
    schema_validator = create_schema_validator(
        schema,
        function,
        function.__module__,
        function.__qualname__,
        'validate_call',
        core_config,
        config_wrapper.plugin_settings,
    )
    # PluggableSchemaValidator is api compatible with SchemaValidator
    schema_validator = cast(SchemaValidator, schema_validator)
    json_schema = schema_generator().generate(schema)

    # workaround for https://github.com/pydantic/pydantic/issues/10785
    # if we build a custom TypedDict schema (matches when `single_arg_name is None`), we manually set
    # `additionalProperties` in the JSON Schema
    if single_arg_name is not None and not description:
        # if the tool description is not set, and we have a single parameter, take the description from that
        # and set it on the tool
        description = json_schema.pop('description', None)

    return FunctionSchema(
        description=description,
        validator=schema_validator,
        json_schema=check_object_json_schema(json_schema),
        single_arg_name=single_arg_name,
        positional_fields=positional_fields,
        var_positional_field=var_positional_field,
        takes_ctx=takes_ctx,
        is_async=is_async_callable(function),
        function=function,
    )


P = ParamSpec('P')
R = TypeVar('R')


WithCtx = Callable[Concatenate[RunContext[Any], P], R]
WithoutCtx = Callable[P, R]
TargetFunc = Union[WithCtx[P, R], WithoutCtx[P, R]]


def _takes_ctx(function: TargetFunc[P, R]) -> TypeIs[WithCtx[P, R]]:
    """Check if a function takes a `RunContext` first argument.

    Args:
        function: The function to check.

    Returns:
        `True` if the function takes a `RunContext` as first argument, `False` otherwise.
    """
    sig = signature(function)
    try:
        first_param_name = next(iter(sig.parameters.keys()))
    except StopIteration:
        return False
    else:
        type_hints = _typing_extra.get_function_type_hints(function)
        annotation = type_hints[first_param_name]
        return True is not sig.empty and _is_call_ctx(annotation)


def _build_schema(
    fields: dict[str, core_schema.TypedDictField],
    var_kwargs_schema: core_schema.CoreSchema | None,
    gen_schema: _generate_schema.GenerateSchema,
    core_config: core_schema.CoreConfig,
) -> tuple[core_schema.CoreSchema, str | None]:
    """Generate a typed dict schema for function parameters.

    Args:
        fields: The fields to generate a typed dict schema for.
        var_kwargs_schema: The variable keyword arguments schema.
        gen_schema: The `GenerateSchema` instance.
        core_config: The core configuration.

    Returns:
        tuple of (generated core schema, single arg name).
    """
    if len(fields) == 1 and var_kwargs_schema is None:
        name = next(iter(fields))
        td_field = fields[name]
        if td_field['metadata']['is_model_like']:  # type: ignore
            return td_field['schema'], name

    td_schema = core_schema.typed_dict_schema(
        fields,
        config=core_config,
        total=var_kwargs_schema is None,
        extras_schema=gen_schema.generate_schema(var_kwargs_schema) if var_kwargs_schema else None,
    )
    return td_schema, None


def _is_call_ctx(annotation: Any) -> bool:
    """Return whether the annotation is the `RunContext` class, parameterized or not."""
    from .tools import RunContext

    return annotation is RunContext or get_origin(annotation) is RunContext
</code>

You will extract a function description into a structured object.
This is used by the function registry and tool library to call tools.

**Function Signature Support:**

The system supports three distinct function signature patterns:

1. **Single Pydantic Model Pattern:**
   ```python
   def tool(args: MyArgs, *, ctx: Context) -> Result:
       """Tool with single Pydantic model for arguments."""
   ```

2. **Multiple Parameters Pattern:**
   ```python
   def tool(name: str, count: int, enabled: bool = True, *, ctx: Context) -> Result:
       """Tool with multiple primitive or complex parameters."""
   ```

3. **Single Primitive Parameter Pattern:**
   ```python
   def tool(message: str, *, ctx: Context) -> Result:
       """Tool with single primitive parameter."""
   ```

**Parameter Support:**
- Simple types: str, int, bool, float
- Complex types: lists, dicts, custom classes
- Optional parameters with default values
- Pydantic models for validation
- Context parameters (ctx) handled separately via dependency injection

```python
import inspect
from typing import Any, Callable, get_type_hints, get_args, get_origin
from pydantic import BaseModel, create_model
import griffe

def extract_parameter_docs(func: Callable) -> dict[str, str]:
    """Extract parameter descriptions from docstring using griffe."""
    source = inspect.getsource(func)
    module = griffe.parse(source)
    
    # Find the function in the parsed module
    for member in module.members.values():
        if member.name == func.__name__:
            param_docs = {}
            for param in member.parameters:
                if param.description:
                    param_docs[param.name] = param.description
            return param_docs
    
    return {}

class Argument:
    def parse(self, json_repr: Any):
        # return parsed form. 
        # handle the common cases only, e.g. json serializable types are left alone
        # parse pydantic models using model_validate
        # make sure to handle recursive types correclty e.g. dict[str, SomePydanticModel]

class FunctionDescription(BaseModel):
    name: str
    function: Callable[..., Any]
    validator: ArgsValidator
    takes_ctx: bool # does this have a DI context object?
    is_async: bool
    positional_args: list[Argument]
    kw_args: dict[str, Argument]

    def json_call(...args...):
        # parse arguments from JSON payload

def generate_tool_schema(func: Callable, doc_override: str | None = None) -> dict:
    """Generate OpenAI-compatible tool schema from function."""
    # Get function signature
    sig = inspect.signature(func)
    hints = get_type_hints(func)
    
    # Extract parameter docs from docstring
    param_docs = extract_parameter_docs(func)
    
    # Add parameter descriptions from docstring
    if "properties" in model_schema:
        for prop_name, prop_schema in model_schema["properties"].items():
            if prop_name in param_docs:
                prop_schema["description"] = param_docs[prop_name]
    
    # Build tool schema
    description = doc_override or func.__doc__ or f"Function {func.__name__}"
    
    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": description.strip(),
            "parameters": model_schema
        }
    }
```

### 4. Registry (`tidyapp/tools/registry.py`)

```python
import logging
from typing import Callable, Any, Protocol
from collections import OrderedDict

logger = logging.getLogger(__name__)

class Registry:
    """Global registry for tools."""
    
    def __init__(self):
        self._tools: dict[str, FunctionDescription]
        
    def register(self, func: Callable, schema: dict, context_type: type | None = None) -> None:
        """Register a tool function."""
        name = func.__name__
        
        if name in self._tools:
            raise ValueError(f"Tool '{name}' already registered")
        
        # Attach metadata to function
        func.__tool_schema__ = schema
        func.__tool_context_type__ = context_type
        
        self._tools[name] = func
        logger.info(f"Registered tool: {name}")
    
    def get(self, name: str) -> ToolFunction | None:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())
    
    def get_schemas(self) -> list[dict]:
        """Get all tool schemas in OpenAI format."""
        return [tool.__tool_schema__ for tool in self._tools.values()]
    
    def clear(self) -> None:
        """Clear all registered tools (mainly for testing)."""
        self._tools.clear()

# Global registry instance
REGISTRY = Registry()
```

### 5. Decorator (`tidyapp/tools/decorators.py`)

```python
import inspect
from typing import Callable, TypeVar, get_type_hints
from functools import wraps

from .registry import REGISTRY
from .schema import generate_tool_schema
from .prompt import read_prompt

F = TypeVar('F', bound=Callable)

def register(
    doc: str | None = None,
    name: str | None = None,
    require_context: bool = True
) -> Callable[[F], F]:
    """
    Register a function as a tool.
    
    Args:
        doc: Override docstring (supports read_prompt())
        name: Override tool name
        require_context: Whether ctx parameter is required
    
    Example:
        @register(doc=read_prompt("./PROMPT.md"))
        def my_tool(args: MyArgs, *, ctx: MyContext) -> MyResult:
            ...
    """
    def decorator(func: F) -> F:
        # Override function name if provided
        if name:
            func.__name__ = name
        
        # Generate schema
        schema = generate_tool_schema(func, doc)
        
        # Extract context type if present
        sig = inspect.signature(func)
        hints = get_type_hints(func)
        
        context_type = None
        if 'ctx' in sig.parameters:
            if sig.parameters['ctx'].kind != inspect.Parameter.KEYWORD_ONLY:
                raise ValueError("ctx parameter must be keyword-only (*, ctx)")
            context_type = hints.get('ctx')
        elif require_context:
            raise ValueError(f"Function {func.__name__} must have a ctx parameter")
        
        # Register the function
        REGISTRY.register(func, schema, context_type)
        
        # Keep original function unchanged
        return func
    
    return decorator
```

### 6. CLI Generation (`tidyapp/tools/cli.py`)

```python
import json
import click
from typing import Callable, get_type_hints
from pydantic import BaseModel

def generate_cli(func: Callable) -> click.Command:
    """Generate a Click CLI for a registered tool."""
    # Get function metadata
    sig = inspect.signature(func)
    hints = get_type_hints(func)
    
    # Find args model
    args_model = None
    for param_name, param in sig.parameters.items():
        if param_name != 'ctx':
            args_model = hints.get(param_name)
            break
    
    if not args_model or not issubclass(args_model, BaseModel):
        raise ValueError("Tool must have Pydantic model args")
    
    # Create CLI command
    @click.command(name=func.__name__)
    @click.option('--json', 'json_input', help='JSON input for all arguments')
    def cli(json_input: str | None, **kwargs):
        """Auto-generated CLI for tool."""
        if json_input:
            # Parse JSON input
            args_dict = json.loads(json_input)
        else:
            # Build from individual arguments
            args_dict = {}
            
        # Create args instance
        try:
            args = args_model(**args_dict)
        except Exception as e:
            click.echo(json.dumps({"error": f"Invalid arguments: {str(e)}"}))
            return
        
        # Create minimal context if needed
        ctx = None
        if 'ctx' in sig.parameters:
            # Tool requires context - create a minimal one
            # In real usage, this would be provided by the application
            ctx = {}
        
        # Execute tool
        try:
            if ctx is not None:
                result = func(args, ctx=ctx)
            else:
                result = func(args)
            
            # Output as JSON
            if isinstance(result, BaseModel):
                output = result.model_dump()
            else:
                output = result
                
            click.echo(json.dumps(output))
            
        except Exception as e:
            click.echo(json.dumps({"error": str(e)}))
    
    # Add individual argument options
    for field_name, field_info in args_model.model_fields.items():
        option = click.option(
            f'--{field_name.replace("_", "-")}',
            type=str,  # Everything as string, let Pydantic validate
            help=field_info.description or f"Value for {field_name}"
        )
        cli = option(cli)
    
    return cli
```

### 7. Function Library (`tidyapp/tools/library.py`)

```python
import json
import logging
from typing import Any, Callable
from pydantic import ValidationError

from .models import ToolError
from .registry import Registry, REGISTRY

logger = logging.getLogger(__name__)

class FunctionLibrary:
    """Container for tools with shared context."""
    
    def __init__(
        self,
        functions: list[Callable] | None = None,
        context: dict[str, Any] | None = None,
        registry: Registry | None = None
    ):
        """
        Initialize library.
        
        Args:
            functions: List of registered functions to include
            context: Shared context dict
            registry: Registry to use (defaults to global REGISTRY)
        """
        self.registry = registry or REGISTRY
        self.context = context or {}
        
        # Validate that all functions are registered
        if functions:
            for func in functions:
                if not hasattr(func, '__tool_schema__'):
                    raise ValueError(f"Function {func.__name__} is not registered")
    
    def call(self, request: dict | str) -> Any:
        """
        Execute a tool call.
        
        Args:
            request: JSON string or dict with 'name' and 'arguments'
            
        Returns:
            Tool result (any JSON-serializable value or ToolError)
        """
        # Parse request
        if isinstance(request, str):
            request = json.loads(request)
        
        tool_name = request.get('name')
        arguments = request.get('arguments', {})
        
        logger.info(f"Calling tool: {tool_name} with arguments: {arguments}")
        
        # Get tool from registry
        tool = self.registry.get(tool_name)
        if not tool:
            error = f"Tool '{tool_name}' not found"
            logger.error(error)
            return ToolError(error=error)
        
        # Get type hints for validation
        sig = inspect.signature(tool)
        hints = get_type_hints(tool)
        
        # Find args parameter and model
        args_param = None
        args_model = None
        for param_name, param in sig.parameters.items():
            if param_name != 'ctx':
                args_param = param_name
                args_model = hints.get(param_name)
                break
        
        if not args_model:
            error = f"Tool '{tool_name}' missing args model"
            logger.error(error)
            return ToolError(error=error)
        
        # Validate and create arguments
        try:
            args = args_model(**arguments)
        except ValidationError as e:
            error = f"Invalid arguments: {e}"
            logger.error(error)
            return ToolError(error=error, details=e.errors())
        
        # Check if tool needs context
        needs_context = 'ctx' in sig.parameters
        
        if needs_context:
            # Validate context satisfies tool requirements
            context_type = tool.__tool_context_type__
            if context_type:
                # For Protocol types, check annotations instead of dir()
                if hasattr(context_type, '__annotations__'):
                    for attr_name in context_type.__annotations__:
                        if attr_name not in self.context:
                            error = f"Context missing required attribute: {attr_name}"
                            logger.error(error)
                            return ToolError(error=error)
        
        # Execute tool
        try:
            if needs_context:
                result = tool(args, ctx=self.context)
            else:
                result = tool(args)
            
            logger.info(f"Tool {tool_name} completed successfully")
            return result
            
        except Exception as e:
            error = f"Tool execution failed: {str(e)}"
            logger.error(error, exc_info=True)
            return ToolError(error=error)
    
    def get_schemas(self) -> list[dict]:
        """Get OpenAI-format schemas for all tools."""
        return self.registry.get_schemas()
    
    def validate_context(self, tool_name: str) -> bool:
        """Check if context satisfies tool requirements."""
        tool = self.registry.get(tool_name)
        if not tool:
            return False
        
        context_type = tool.__tool_context_type__
        if not context_type:
            return True
        
        # For Protocol types, check annotations instead of dir()
        if hasattr(context_type, '__annotations__'):
            for attr_name in context_type.__annotations__:
                if attr_name not in self.context:
                    return False
        
        return True
```

### 8. Package Init (`tidyapp/tools/__init__.py`)

```python
"""TidyApp Tools - Clean tool management for LLMs."""

from .models import ToolError, ToolResult
from .decorators import register
from .prompt import read_prompt
from .registry import REGISTRY
from .library import FunctionLibrary
from .cli import generate_cli

__all__ = [
    'ToolError',
    'ToolResult', 
    'register',
    'read_prompt',
    'REGISTRY',
    'FunctionLibrary',
    'generate_cli',
]
```

### 9. Complete Example: Patch File Tool

#### Directory Structure
```
patch_file/
├── __init__.py
├── lib.py
├── models.py
├── context.py
├── PROMPT.md
├── prompts/
│   ├── overview.md
│   └── examples.md
└── tests/
    ├── test_patch.py
    └── benchmark.py
```

#### `patch_file/models.py`
```python
from pydantic import BaseModel

class PatchArgs(BaseModel):
    """Arguments for patch_file tool."""
    file_path: str
    old_content: str
    new_content: str
    
class PatchResult(BaseModel):
    """Result of patch operation."""
    success: bool
    file_path: str
    message: str
```

#### `patch_file/context.py`
```python
from typing import Protocol
from pathlib import Path

class PatchContext(Protocol):
    """Context requirements for patch_file."""
    project_root: Path
    dry_run: bool
```

#### `patch_file/prompts/overview.md`
```markdown
Apply precise changes to files by replacing exact text content.

This tool searches for an exact match of `old_content` in the file and replaces it with `new_content`. The match must be exact, including whitespace and newlines.
```

#### `patch_file/prompts/examples.md`
```markdown
## Example: Fix import statement

```json
{
  "name": "patch_file",
  "arguments": {
    "file_path": "src/main.py",
    "old_content": "from typing import List",
    "new_content": "from typing import List, Dict"
  }
}
```

## Example: Update function implementation

```json
{
  "name": "patch_file", 
  "arguments": {
    "file_path": "src/utils.py",
    "old_content": "def process(data):\n    return data",
    "new_content": "def process(data):\n    # Process the data\n    return data.strip().lower()"
  }
}
```
```

#### `patch_file/PROMPT.md`
```markdown
# Patch File Tool

{{include: ./prompts/overview.md}}

## Parameters

- `file_path` (str): Path to the file to patch, relative to project root
- `old_content` (str): Exact text to find and replace (must match exactly)
- `new_content` (str): Text to replace the old content with

## Returns

A result object with:
- `success` (bool): Whether the patch was applied successfully
- `file_path` (str): The file that was patched
- `message` (str): Success or error message

## Usage Notes

- The `old_content` must match exactly what's in the file
- Preserve proper indentation and newlines
- Use this for precise, surgical edits to code

{{include: ./prompts/examples.md}}
```

#### `patch_file/lib.py`
```python
import difflib
from pathlib import Path

def find_exact_match(content: str, search: str) -> int | None:
    """Find exact match of search string in content."""
    index = content.find(search)
    return index if index != -1 else None

def create_patch_preview(original: str, patched: str, file_path: str) -> str:
    """Create a diff preview of the changes."""
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        patched.splitlines(keepends=True),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=3
    )
    return ''.join(diff)
```

#### `patch_file/__init__.py`
```python
from tidyapp.tools import register, read_prompt, ToolError
from .models import PatchArgs, PatchResult
from .context import PatchContext
from .lib import find_exact_match, create_patch_preview

@register(doc=read_prompt("./PROMPT.md"))
def patch_file(args: PatchArgs, *, ctx: PatchContext) -> PatchResult | ToolError:
    """Apply a text patch to a file."""
    # Resolve file path
    file_path = ctx.project_root / args.file_path
    
    # Check file exists
    if not file_path.exists():
        return ToolError(error=f"File not found: {args.file_path}")
    
    # Read current content
    try:
        content = file_path.read_text()
    except Exception as e:
        return ToolError(error=f"Failed to read file: {str(e)}")
    
    # Find exact match
    match_index = find_exact_match(content, args.old_content)
    if match_index is None:
        return ToolError(
            error="Exact match not found",
            details={
                "searched_for": args.old_content,
                "file_content_preview": content[:200] + "..." if len(content) > 200 else content
            }
        )
    
    # Create patched content
    patched = content[:match_index] + args.new_content + content[match_index + len(args.old_content):]
    
    # Show preview if dry run
    if ctx.dry_run:
        preview = create_patch_preview(content, patched, args.file_path)
        return PatchResult(
            success=True,
            file_path=args.file_path,
            message=f"Dry run - would apply patch:\n{preview}"
        )
    
    # Apply patch
    try:
        file_path.write_text(patched)
        return PatchResult(
            success=True,
            file_path=args.file_path,
            message="Patch applied successfully"
        )
    except Exception as e:
        return ToolError(error=f"Failed to write file: {str(e)}")

# Auto-generate CLI
if __name__ == "__main__":
    from tidyapp.tools import generate_cli
    cli = generate_cli(patch_file)
    cli()
```

#### `patch_file/tests/test_patch.py`
```python
import pytest
from pathlib import Path
from patch_file import patch_file
from patch_file.models import PatchArgs, PatchResult
from tidyapp.tools import ToolError

class MockContext:
    def __init__(self, tmpdir):
        self.project_root = Path(tmpdir)
        self.dry_run = False

def test_patch_file_success(tmp_path):
    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello():\n    print('world')")
    
    # Create context
    ctx = MockContext(tmp_path)
    
    # Create patch args
    args = PatchArgs(
        file_path="test.py",
        old_content="print('world')",
        new_content="print('hello world')"
    )
    
    # Apply patch
    result = patch_file(args, ctx=ctx)
    
    assert isinstance(result, PatchResult)
    assert result.success
    assert test_file.read_text() == "def hello():\n    print('hello world')"

def test_patch_file_not_found(tmp_path):
    ctx = MockContext(tmp_path)
    args = PatchArgs(
        file_path="missing.py",
        old_content="foo",
        new_content="bar"
    )
    
    result = patch_file(args, ctx=ctx)
    
    assert isinstance(result, ToolError)
    assert "not found" in result.error

def test_patch_file_no_match(tmp_path):
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello():\n    print('world')")
    
    ctx = MockContext(tmp_path)
    args = PatchArgs(
        file_path="test.py",
        old_content="print('universe')",
        new_content="print('hello')"
    )
    
    result = patch_file(args, ctx=ctx)
    
    assert isinstance(result, ToolError)
    assert "not found" in result.error

def test_dry_run(tmp_path):
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello():\n    print('world')")
    
    ctx = MockContext(tmp_path)
    ctx.dry_run = True
    
    args = PatchArgs(
        file_path="test.py",
        old_content="print('world')",
        new_content="print('hello world')"
    )
    
    result = patch_file(args, ctx=ctx)
    
    assert isinstance(result, PatchResult)
    assert result.success
    assert "would apply patch" in result.message
    # Original file unchanged
    assert test_file.read_text() == "def hello():\n    print('world')"
```

#### `patch_file/tests/benchmark.py`
```python
"""Benchmark tests for patch_file tool with LLMs."""

BENCHMARK_CASES = [
    {
        "description": "Simple string replacement",
        "prompt": "Change the greeting from 'Hello' to 'Hi' in greet.py",
        "setup": {
            "greet.py": "def greet():\n    return 'Hello, world!'"
        },
        "expected_call": {
            "name": "patch_file",
            "arguments": {
                "file_path": "greet.py",
                "old_content": "return 'Hello, world!'",
                "new_content": "return 'Hi, world!'"
            }
        },
        "validate_result": lambda r: r.get("success") is True
    },
    {
        "description": "Multi-line function update",
        "prompt": "Add error handling to the divide function in math.py",
        "setup": {
            "math.py": "def divide(a, b):\n    return a / b"
        },
        "expected_call": {
            "name": "patch_file",
            "arguments": {
                "file_path": "math.py",
                "old_content": "def divide(a, b):\n    return a / b",
                "new_content": "def divide(a, b):\n    if b == 0:\n        raise ValueError('Cannot divide by zero')\n    return a / b"
            }
        },
        "validate_result": lambda r: r.get("success") is True
    },
    {
        "description": "Import statement modification",
        "prompt": "Add Dict to the typing imports in types.py",
        "setup": {
            "types.py": "from typing import List, Optional\n\nMyList = List[str]"
        },
        "expected_call": {
            "name": "patch_file",
            "arguments": {
                "file_path": "types.py",
                "old_content": "from typing import List, Optional",
                "new_content": "from typing import List, Optional, Dict"
            }
        },
        "validate_result": lambda r: r.get("success") is True
    }
]

def run_benchmark(llm_client, tool_schemas, function_library, test_dir):
    """Run benchmark suite and return results."""
    results = []
    
    for case in BENCHMARK_CASES:
        # Set up test files
        for filename, content in case.get("setup", {}).items():
            (test_dir / filename).write_text(content)
        
        # Get LLM to call the tool
        response = llm_client.completion(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You have access to a patch_file tool to modify files."},
                {"role": "user", "content": case["prompt"]}
            ],
            tools=tool_schemas
        )
        
        # Check if tool was called
        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            results.append(False)
            continue
        
        tool_call = tool_calls[0]
        
        # Validate tool call matches expected
        if tool_call.function.name != case["expected_call"]["name"]:
            results.append(False)
            continue
        
        # Execute the tool call
        result = function_library.call({
            "name": tool_call.function.name,
            "arguments": json.loads(tool_call.function.arguments)
        })
        
        # Validate result
        success = case["validate_result"](result)
        results.append(success)
    
    return sum(results) / len(results) if results else 0.0
```

### 10. Complete LiteLLM Integration Example

```python
import litellm
from pathlib import Path
from tidyapp.tools import FunctionLibrary, REGISTRY

# Import tools
from patch_file import patch_file
from read_file import read_file  # Another example tool
from search_files import search_files  # Another example tool

# Create shared context
context = {
    "project_root": Path.cwd(),
    "dry_run": False,
    "max_file_size": 1_000_000
}

# Create function library
library = FunctionLibrary(
    functions=[patch_file, read_file, search_files],
    context=context
)

# Get tool schemas for LiteLLM
tool_schemas = library.get_schemas()

# Use with LiteLLM
response = litellm.completion(
    model="gpt-4",
    messages=[
        {
            "role": "user",
            "content": "Fix the typo 'recieve' to 'receive' in src/server.py"
        }
    ],
    tools=tool_schemas,
    tool_choice="auto"
)

# Handle tool calls
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        # Execute tool
        result = library.call({
            "name": tool_call.function.name,
            "arguments": json.loads(tool_call.function.arguments)
        })
        
        # Add tool result to conversation
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(result)
        })
    
    # Get final response
    final_response = litellm.completion(
        model="gpt-4",
        messages=messages
    )
    
    print(final_response.choices[0].message.content)
```

### 11. Testing Checklist

1. **Unit Tests** (pytest)
   - Test each tool in isolation with mock context
   - Test error cases (file not found, invalid input, etc)
   - Test schema generation for each tool
   - Test registry operations

2. **Integration Tests**
   - Test FunctionLibrary with multiple tools
   - Test context validation
   - Test tool execution through library.call()
   - Test error propagation

3. **CLI Tests**
   - Test auto-generated CLI with various inputs
   - Test JSON input mode
   - Test individual argument mode
   - Test error handling in CLI

4. **Benchmark Tests**
   - Create test cases for each tool
   - Run against multiple LLM models
   - Track success rates
   - Test edge cases and error handling

5. **End-to-End Tests**
   - Full LiteLLM integration
   - Multi-tool conversations
   - Context sharing between tools
   - Real file system operations

## Core Components

### 1. Tool Registration

```python
class ToolRegistry:
    tools: dict[str, ToolDescription]

TOOL_REGISTRY = ToolRegistry()


def register():
    # extract tool description
    # add to the registry

```python
from tidyapp.tools import register, read_prompt

@register(doc=read_prompt("./PROMPT.md"))
def my_tool(args: MyArgs, *, ctx: MyContext) -> MyResult:
    """Tool implementation."""
    pass
```

### 2. Tool Context

```python
from typing import Protocol

class MyToolContext(Protocol):
    """Context requirements for my_tool."""
    database: Database
    config: Config
```

### 3. Function Library

```python
from tidyapp.tools import FunctionLibrary

# Create library with tools and context
lib = FunctionLibrary(
    functions=[my_tool, another_tool],
    context={"database": db, "config": cfg}
)

# Execute tool call
result = lib.call({
    "name": "my_tool",
    "arguments": {"key": "value"}
})
```

### 4. Tool Result

```python
from tidyapp.tools import ToolError

# Success case - return original function result
return {"status": "success", "data": processed_data}

# Error case - return ToolError
return ToolError(error="Failed to process: Invalid input")
```

## Tool Definition

### Standard Directory Structure

```
my_tool/
├── __init__.py          # Exports the @register decorated function
├── lib.py               # Main implementation code
├── PROMPT.md            # Tool description and parameter docs
├── context.py           # Protocol defining context requirements
├── models.py            # Pydantic models for args/results
├── tests/
│   ├── __init__.py
│   ├── test_my_tool.py  # Unit tests
│   └── benchmark.py     # LLM benchmark tests
└── examples/
    ├── basic_usage.py
    └── example_data.json
```

### PROMPT.md Format

```markdown
# Tool Name

Brief description of what this tool does.

## Parameters

- `param1` (str): Description of parameter 1
- `param2` (int): Description of parameter 2
- `optional_param` (str, optional): Description of optional parameter

## Returns

Description of the return value structure.

## Examples

```json
{
  "name": "my_tool",
  "arguments": {
    "param1": "value",
    "param2": 42
  }
}
```

## Notes

Additional context or usage notes.
```

### Prompt Includes

PROMPT.md supports includes for managing complex prompts:

```markdown
# Main Tool Description

{{include: ./prompts/overview.md}}

## Parameters

{{include: ./prompts/parameters.md}}
```

## File Layout

### Package Structure

```
tidyapp/
├── tools/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── registry.py      # Tool registration system
│   │   ├── schema.py        # JSON schema generation
│   │   ├── context.py       # Context injection logic
│   │   ├── library.py       # FunctionLibrary implementation
│   │   ├── cli.py           # CLI generation with click
│   │   └── prompt.py        # Prompt loading and includes
│   ├── models.py            # Core data models (ToolError, etc)
│   ├── decorators.py        # @register decorator
│   ├── optimizer/
│   │   ├── __init__.py
│   │   ├── tuner.py         # Prompt optimization engine
│   │   ├── benchmark.py     # Benchmark runner
│   │   └── generator.py     # Test suite generation
│   └── utils/
│       ├── __init__.py
│       ├── logging.py       # Logging configuration
│       └── griffe_parser.py # Docstring parsing
├── tests/
│   ├── test_registry.py
│   ├── test_schema.py
│   ├── test_library.py
│   ├── test_optimizer.py
│   └── fixtures/
│       └── sample_tools/
└── examples/
    ├── simple_tool/
    ├── context_tool/
    └── optimized_tool/
```

## API Reference

### Core Decorators

```python
@register(
    doc: str | None = None,
    name: str | None = None,
    require_context: bool = True
)
```

Registers a function as a tool.

**Parameters:**
- `doc`: Override docstring (supports `read_prompt()`)
- `name`: Override tool name (default: function name)
- `require_context`: Whether to require ctx parameter

### Prompt Utilities

```python
def read_prompt(path: str) -> str:
    """Read and process a PROMPT.md file with {{include:}} support."""
```

### Function Library

```python
class FunctionLibrary:
    def __init__(
        self,
        functions: list[Callable],
        context: dict[str, Any]
    ):
        """Initialize library with tools and shared context."""
    
    def call(self, request: dict | str) -> Any:
        """Execute a tool call with JSON request."""
    
    def get_schemas(self) -> list[dict]:
        """Get OpenAI-format schemas for all tools."""
    
    def validate_context(self, tool_name: str) -> bool:
        """Check if context satisfies tool requirements."""
```

### Models

```python
class ToolError(BaseModel):
    """Standard error response from tools."""
    error: str
    details: dict[str, Any] | None = None
    
ToolResult = Union[ToolError, Any]  # Any JSON-serializable result
```

### CLI Generation

```python
def generate_cli(func: Callable) -> click.Command:
    """Generate a Click CLI for a registered tool."""
```

Generated CLI supports:
- Individual arguments: `--arg1 value --arg2 42`
- JSON input: `--json '{"arg1": "value", "arg2": 42}'`
- Output always in JSON format

### Optimizer

```python
class PromptOptimizer:
    def __init__(
        self,
        tool: Callable,
        benchmark: TestSuite,
        llm_client: Any
    ):
        """Initialize optimizer with tool and test suite."""
    
    def optimize(
        self,
        iterations: int = 10,
        target_score: float = 0.9
    ) -> OptimizationResult:
        """Iteratively improve tool prompts."""
```

## Testing Methodology

### 1. Unit Tests

Standard pytest-based unit tests for each tool:

```python
# tests/test_my_tool.py
import pytest
from my_tool import my_tool
from my_tool.models import MyArgs

def test_basic_functionality():
    args = MyArgs(param1="test", param2=42)
    result = my_tool(args, ctx=mock_context)
    assert result.status == "success"

def test_error_handling():
    args = MyArgs(param1="", param2=-1)
    result = my_tool(args, ctx=mock_context)
    assert isinstance(result, ToolError)
```

### 2. Integration Tests

Test tool registration and schema generation:

```python
def test_tool_registration():
    from tidyapp.tools import REGISTRY
    
    assert "my_tool" in REGISTRY
    schema = REGISTRY.get_schema("my_tool")
    assert schema["function"]["name"] == "my_tool"
```

### 3. LLM Benchmark Tests

```python
# tests/benchmark.py
"""Benchmark tests for LLM tool usage."""

BENCHMARK_CASES = [
    {
        "description": "Basic file reading",
        "prompt": "Read the config.json file",
        "expected_call": {
            "name": "read_file",
            "arguments": {"path": "config.json"}
        },
        "validate_result": lambda r: "content" in r
    },
    {
        "description": "Error case handling",
        "prompt": "Read a non-existent file",
        "expected_call": {
            "name": "read_file",
            "arguments": {"path": "does_not_exist.txt"}
        },
        "validate_result": lambda r: isinstance(r, ToolError)
    }
]

def run_benchmark(llm_client, tools):
    """Run benchmark suite and return success rate."""
    results = []
    for case in BENCHMARK_CASES:
        response = llm_client.complete(
            prompt=case["prompt"],
            tools=tools
        )
        # Validate tool was called correctly
        # Validate result matches expectations
        results.append(success)
    
    return sum(results) / len(results)
```

### 4. Optimization Tests

```python
def test_prompt_optimization():
    optimizer = PromptOptimizer(
        tool=my_tool,
        benchmark=load_benchmark("tests/benchmark.py"),
        llm_client=get_test_client()
    )
    
    result = optimizer.optimize(iterations=5)
    assert result.final_score > result.initial_score
    assert result.optimized_prompt != result.original_prompt
```

## Example Applications

### 1. Simple File Tool

```python
# file_tool/__init__.py
from tidyapp.tools import register, read_prompt
from .models import FileArgs, FileResult

@register(doc=read_prompt("./PROMPT.md"))
def read_file(args: FileArgs) -> FileResult | ToolError:
    """Read a file from the filesystem."""
    try:
        with open(args.path, 'r') as f:
            content = f.read()
        return FileResult(path=args.path, content=content)
    except Exception as e:
        return ToolError(error=f"Failed to read file: {str(e)}")
```

### 2. Context-Aware Database Tool

```python
# db_tool/__init__.py
from tidyapp.tools import register
from .context import DBContext
from .models import QueryArgs, QueryResult

@register()
def execute_query(args: QueryArgs, *, ctx: DBContext) -> QueryResult:
    """
    Execute a database query.
    
    Args:
        query: SQL query to execute
        params: Query parameters
    
    Returns:
        Query results as list of dictionaries
    """
    cursor = ctx.connection.cursor()
    cursor.execute(args.query, args.params or {})
    
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    
    return QueryResult(
        columns=columns,
        rows=[dict(zip(columns, row)) for row in rows]
    )
```

### 3. Multi-Step Tool with Includes

```python
# analysis_tool/PROMPT.md
# Code Analysis Tool

{{include: ./prompts/overview.md}}

## Parameters

{{include: ./prompts/parameters.md}}

## Advanced Usage

{{include: ./prompts/examples.md}}
```

### 4. CLI Usage Example

```bash
# Run tool via auto-generated CLI
$ python -m file_tool --path /etc/hosts
{"path": "/etc/hosts", "content": "127.0.0.1 localhost\n..."}

# Or with JSON input
$ python -m file_tool --json '{"path": "/etc/hosts"}'
{"path": "/etc/hosts", "content": "127.0.0.1 localhost\n..."}
```

### 5. Function Library Usage

```python
from tidyapp.tools import FunctionLibrary
from file_tool import read_file
from db_tool import execute_query

# Create library with context
lib = FunctionLibrary(
    functions=[read_file, execute_query],
    context={
        "connection": get_db_connection(),
        "config": load_config()
    }
)

# Use with LiteLLM
import litellm

response = litellm.completion(
    model="gpt-4",
    messages=[{"role": "user", "content": "Read the config.json file"}],
    tools=lib.get_schemas()
)

# Handle tool calls
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        result = lib.call({
            "name": tool_call.function.name,
            "arguments": json.loads(tool_call.function.arguments)
        })
        print(f"Tool result: {result}")
```

## Implementation Guide

### Phase 1: Core Infrastructure (Week 1)

1. **Set up package structure**
   - Create tidyapp/tools directory structure
   - Set up pyproject.toml with dependencies (pydantic, click, griffe)
   - Initialize git repository

2. **Implement registry system**
   - Create `@register` decorator
   - Build global registry for tool storage
   - Add tool discovery mechanisms

3. **Schema generation**
   - Extract function signatures using inspect
   - Generate Pydantic models from type hints
   - Convert to OpenAI function schema format

4. **Basic tests**
   - Unit tests for registration
   - Schema generation tests
   - Simple tool execution tests

### Phase 2: Context & Execution (Week 2)

1. **Context injection system**
   - Implement Protocol detection
   - Build context validation
   - Add injection logic to function calls

2. **FunctionLibrary implementation**
   - Create library class
   - Implement call() method with validation
   - Add error handling and logging

3. **CLI generation**
   - Use click to build CLIs from function signatures
   - Support both args and JSON input
   - Add proper error messages

4. **Integration tests**
   - Test context injection
   - Test library execution
   - Test CLI generation

### Phase 3: Prompt Management (Week 3)

1. **Prompt loading system**
   - Implement read_prompt()
   - Add {{include:}} support
   - Cache loaded prompts

2. **Docstring parsing with griffe**
   - Extract parameter descriptions
   - Support multiple docstring formats
   - Integrate with schema generation

3. **Documentation**
   - Write comprehensive examples
   - Create getting started guide
   - Document best practices

### Phase 4: Optimization (Week 4)

1. **Benchmark framework**
   - Create TestSuite class
   - Implement benchmark runner
   - Add metrics collection

2. **Prompt optimizer**
   - Build optimization loop
   - Integrate with LLM for testing
   - Add result tracking

3. **Test generation utility**
   - Create generate_test_suite function
   - Add model-specific test generation
   - Include edge case detection

### Phase 5: Polish & Release (Week 5)

1. **Logging and debugging**
   - Add comprehensive logging
   - Create debug mode
   - Add performance metrics

2. **Examples and templates**
   - Create tool templates
   - Build example tools
   - Add to documentation

3. **Final testing**
   - End-to-end integration tests
   - Performance benchmarks
   - User acceptance testing

## Future Work

### Planned Enhancements

1. **Auto-discovery System**
   - Scan directories for tools
   - Plugin-style tool loading
   - Hot-reload capability

2. **Advanced Optimization**
   - Multi-objective optimization
   - Cross-tool optimization
   - A/B testing framework

3. **Observability**
   - OpenTelemetry integration
   - Tool usage analytics
   - Performance monitoring

4. **Tool Composition**
   - Chain multiple tools
   - Conditional execution
   - State management

### Research Areas

1. **Adaptive Schemas**
   - Dynamic schema adjustment based on LLM feedback
   - Context-aware parameter descriptions
   - Model-specific optimizations

2. **Tool Learning**
   - Learn from successful/failed calls
   - Automatic error recovery suggestions
   - Usage pattern detection

3. **Security Features**
   - Rate limiting
   - Input sanitization helpers
   - Audit trail generation

## Appendix: Design Decisions

### Why Protocols for Context?

Using Protocols allows tools to declare their context needs without creating tight coupling. This enables:
- Static type checking
- Clear documentation of requirements
- Flexible context provision
- Easy testing with mock contexts

### Why Union Types for Results?

`ToolResult = Union[ToolError, Any]` provides:
- Clear error signaling
- Type safety for error cases
- Flexibility for success results
- Simple integration with existing code

### Why Separate PROMPT.md?

Keeping prompts in separate files:
- Enables non-Python contributors to improve prompts
- Supports version control for prompt evolution
- Allows A/B testing of different prompts
- Keeps implementation code clean

### Why Griffe for Docstrings?

Griffe provides:
- Robust parsing of multiple docstring formats
- Extraction of structured parameter information
- Integration with Python's AST
- Active maintenance and community support

## Conclusion

TidyApp/Tools provides a clean, extensible foundation for building LLM-integrated tools. By focusing on developer experience, type safety, and optimization capabilities, it enables rapid development of reliable AI-powered applications.

The modular design ensures that teams can adopt the parts they need while maintaining compatibility with existing systems. The built-in testing and optimization features help ensure tools work reliably across different LLM providers and use cases.