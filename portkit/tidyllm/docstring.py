"""Docstring parsing using griffe for enhanced parameter extraction."""

import logging
from collections.abc import Callable
from typing import Any

from griffe import Docstring

logger = logging.getLogger(__name__)


def extract_function_docs(func: Callable) -> dict[str, Any]:
    """Extract function documentation including parameters using griffe.

    Args:
        func: Function to extract documentation from

    Returns:
        Dictionary containing description, returns, and parameter docs
    """
    if not func.__doc__:
        return {"description": "", "returns": "", "parameters": {}}

    # Parse docstring directly using griffe
    docstring = Docstring(func.__doc__, lineno=1)
    parsed = docstring.parse("google")

    docs: dict[str, Any] = {
        "description": "",
        "returns": "",
        "parameters": {},
    }

    # Extract from parsed sections
    for section in parsed:
        if section.kind.value == "text":
            # This is the description/summary section
            if hasattr(section, "value") and section.value:
                docs["description"] = section.value

        elif section.kind.value == "returns":
            if hasattr(section, "value") and section.value:
                for ret in section.value:
                    if hasattr(ret, "description"):
                        docs["returns"] = ret.description
                        break

        elif section.kind.value == "parameters":
            if hasattr(section, "value") and section.value:
                for param in section.value:
                    if hasattr(param, "name") and hasattr(param, "description"):
                        docs["parameters"][param.name] = param.description

    return docs


def enhance_schema_with_docs(schema: dict[str, Any], func: Callable) -> dict[str, Any]:
    """Enhance existing schema with griffe-extracted documentation.

    Args:
        schema: Existing tool schema to enhance
        func: Function to extract docs from

    Returns:
        Enhanced schema with better documentation
    """
    # Extract function docs (includes parameters)
    func_docs = extract_function_docs(func)

    # Enhance function description if not already set
    if func_docs["description"] and not schema.get("function", {}).get("description"):
        schema.setdefault("function", {})["description"] = func_docs["description"]

    # Enhance parameter descriptions
    if "function" in schema and "parameters" in schema["function"]:
        parameters = schema["function"]["parameters"]
        if "properties" in parameters:
            for param_name, param_schema in parameters["properties"].items():
                if param_name in func_docs["parameters"] and "description" not in param_schema:
                    param_schema["description"] = func_docs["parameters"][param_name]

    return schema
