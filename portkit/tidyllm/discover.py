"""Auto-discovery system for TidyLLM tools."""

import importlib
import importlib.util
import logging
from pathlib import Path

from portkit.tidyllm.registry import REGISTRY
from portkit.tidyllm.schema import FunctionDescription

logger = logging.getLogger(__name__)


def discover_tools_in_directory(
    directory: Path,
    pattern: str = "*.py",
    recursive: bool = True,
    exclude_patterns: list[str] | None = None
) -> list[FunctionDescription]:
    """
    Auto-discover tools in a directory by importing Python modules.
    
    Args:
        directory: Directory to search for tools
        pattern: File pattern to match (default: "*.py")
        recursive: Whether to search recursively
        exclude_patterns: Patterns to exclude (e.g., ["test_*", "*_test.py"])
        
    Returns:
        List of discovered FunctionDescription objects from the specified directory
        
    Example:
        # Discover all tools in a directory
        tools = discover_tools_in_directory(
            Path("my_tools"),
            exclude_patterns=["test_*", "__pycache__"]
        )
    """
    import inspect

    if exclude_patterns is None:
        exclude_patterns=["test_*.py", "__pycache__", "*.pyc", "tests/", "__main__.py"]

    # Find Python files to discover
    if recursive:
        python_files = directory.rglob(pattern)
    else:
        python_files = directory.glob(pattern)

    # Convert to absolute paths for comparison
    discovered_file_paths = set()
    for py_file in python_files:
        # Skip files matching exclude patterns
        if any(py_file.match(exclude_pattern) for exclude_pattern in exclude_patterns):
            logger.debug(f"Skipping excluded file: {py_file}")
            continue

        if py_file.name == "__main__.py":
            continue

        discovered_file_paths.add(py_file.resolve())

        try:
            module_name = _get_module_name_from_path(py_file, directory)
            logger.debug(f"Attempting to import module: {module_name} from {py_file}")

            # Import the module to trigger tool registration
            _import_module_from_path(py_file, module_name)

        except Exception as e:
            # Don't warn about tools already being registered - that's expected
            if "already registered" not in str(e):
                logger.warning(f"Failed to import {py_file}: {e}")
            continue

    # Now find all tools in the registry that originated from discovered files
    discovered_tools = []
    for tool_name in REGISTRY.list_tools():
        tool_desc = REGISTRY.get(tool_name)
        if tool_desc and tool_desc.function:
            try:
                # Get the source file of the function
                source_file = Path(inspect.getfile(tool_desc.function)).resolve()
                if source_file in discovered_file_paths:
                    discovered_tools.append(tool_desc)
                    logger.debug(f"Found tool '{tool_name}' from {source_file}")
            except (OSError, TypeError):
                # Some functions might not have source files (built-ins, etc.)
                continue

    logger.info(f"Auto-discovery completed. Found {len(discovered_tools)} tools from {len(discovered_file_paths)} files")
    return discovered_tools


def discover_tools_in_package(
    package_name: str,
    recursive: bool = True
) -> list[FunctionDescription]:
    """
    Auto-discover tools in a Python package.
    
    Args:
        package_name: Name of the package to search (e.g., "portkit.tinyagent.tools")
        recursive: Whether to search subpackages
        
    Returns:
        List of discovered FunctionDescription objects
        
    Example:
        # Discover all tools in the portkit.tinyagent.tools package
        tools = discover_tools_in_package("portkit.tinyagent.tools")
    """
    try:
        package = importlib.import_module(package_name)
        if not hasattr(package, "__path__") or not package.__path__:
            logger.warning(f"{package_name} is not a package or has no __path__")
            return []
            
        package_path = Path(list(package.__path__)[0])
        return discover_tools_in_directory(package_path, recursive=recursive)
        
    except ImportError as e:
        logger.error(f"Failed to import package {package_name}: {e}")
        return []


def _get_module_name_from_path(file_path: Path, base_path: Path) -> str:
    """Generate a module name from a file path relative to base path."""
    relative_path = file_path.relative_to(base_path)
    # Remove .py extension and convert path separators to dots
    module_parts = relative_path.with_suffix("").parts
    return ".".join(module_parts)


def _import_module_from_path(file_path: Path, module_name: str) -> None:
    """Import a module from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {module_name} from {file_path}")
        
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
