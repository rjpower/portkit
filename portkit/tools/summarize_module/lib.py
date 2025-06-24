"""C module summarization implementation using Gemini 2.5 Flash."""

import json
from pathlib import Path

from pydantic import BaseModel, Field

from portkit.tidyllm.llm import LiteLLMClient, LLMMessage, Role
from portkit.tidyllm.prompt import module_dir, read_prompt
from portkit.tidyllm.registry import register


class SummarizeModuleArgs(BaseModel):
    """Arguments for C module summarization."""

    paths: list[str] = Field(
        description="List of paths to C module files (.h, .c, .cc, .cpp) to analyze",
        examples=[
            ["/path/to/module.h"],
            ["/path/to/module.h", "/path/to/module.c"],
            ["/path/to/libxml2/include/libxml/xpath.h"],
            ["/path/to/header1.h", "/path/to/header2.h", "/path/to/impl.c"],
        ],
    )


class ModuleStructure(BaseModel):
    """Information about a key structure in the module."""

    name: str = Field(description="Structure name")
    purpose: str = Field(description="What the structure represents")
    key_fields: list[str] = Field(description="Important fields and their purposes")


class ModuleEnum(BaseModel):
    """Information about a key enumeration in the module."""

    name: str = Field(description="Enum name")
    purpose: str = Field(description="What the enum represents")
    key_values: list[str] = Field(description="Important enum values and their meanings")


class ModuleFunction(BaseModel):
    """Information about a key function in the module."""

    signature: str = Field(description="C function signature")
    description: str = Field(description="What the function does and its purpose")


class SummarizeModuleResult(BaseModel):
    """Result of C module summarization."""

    module_name: str = Field(description="Name/identifier of the analyzed module")

    overview: str = Field(description="High-level overview of module's purpose and functionality")

    key_structures: list[ModuleStructure] = Field(
        description="Important data structures and their purposes"
    )

    key_enums: list[ModuleEnum] = Field(description="Important enumerations and their purposes")

    public_functions: list[ModuleFunction] = Field(description="Key public API functions")

    api_boundaries: str = Field(
        description="Description of how this module interfaces with other modules"
    )

    dependencies: list[str] = Field(description="Other modules or libraries this module depends on")

    analyzed_files: list[str] = Field(description="List of files that were analyzed")


def collect_module_files(paths: list[str]) -> list[Path]:
    """Collect and validate C module files for analysis."""
    if not paths:
        raise ValueError("No file paths provided")

    files = []
    for path_str in paths:
        path = Path(path_str)

        if not path.exists():
            raise ValueError(f"File does not exist: {path_str}")

        if not path.is_file():
            raise ValueError(f"Path is not a file: {path_str}")

        # Check if it's a supported C/C++ file
        if path.suffix not in [".h", ".c", ".cc", ".cpp", ".hpp"]:
            raise ValueError(
                f"Unsupported file type: {path_str} (must be .h, .c, .cc, .cpp, or .hpp)"
            )

        files.append(path)

    return files


def read_file_content(file_path: Path) -> str:
    """Read file content with error handling."""
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Truncate very large files to avoid context limits
        max_chars = 50000  # Roughly 10-15k tokens
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n... [File truncated for analysis] ..."

        return content
    except Exception as e:
        return f"// Error reading file: {str(e)}"


def create_analysis_prompt(files_content: dict[str, str], module_name: str) -> str:
    """Create the detailed analysis prompt for the LLM."""

    files_section = ""
    for file_path, content in files_content.items():
        files_section += f"\n<<<< BEGIN {file_path} >>>>\n{content}\n<<<< END {file_path} >>>>\n"

    return f"""You are a senior C/C++ developer tasked with analyzing and summarizing a C module for documentation and API understanding purposes.

# Task
Analyze the provided C module files and create a comprehensive summary that would help other developers understand:
- The module's overall purpose and functionality
- Key data structures and their roles
- Important enumerations and their meanings  
- Public API functions and their purposes
- How this module interfaces with other parts of the system
- Dependencies on other modules/libraries

# Module: {module_name}

Please analyze these files:{files_section}

# Analysis Requirements

## 1. Module Overview
Provide a clear, concise description of what this module does. What is its primary responsibility? What problem does it solve?

## 2. Key Data Structures
Identify the 3-5 most important structures, including:
- Structure name and purpose
- Key fields and what they represent
- How the structure fits into the module's functionality

## 3. Important Enumerations  
List significant enums, including:
- Enum name and what it represents
- Key values and their meanings
- How the enum is used in the API

## 4. Public API Functions
Identify the main public functions (usually marked with XMLPUBFUN, extern, or similar), including:
- Complete C function signature as it appears in the header
- Description of what the function does and its purpose in the API

## 5. API Boundaries and Interfaces
Describe how this module connects to other parts of the system:
- What modules/libraries does it depend on?
- What interfaces does it provide to other modules?
- What are the main entry points for using this module?

## 6. Dependencies
List other modules, libraries, or headers this module depends on.

# Output Format
Respond with a valid JSON object (no markdown formatting) matching this exact structure:

{{
  "module_name": "string",
  "overview": "string", 
  "key_structures": [
    {{
      "name": "string",
      "purpose": "string", 
      "key_fields": ["field1: purpose", "field2: purpose"]
    }}
  ],
  "key_enums": [
    {{
      "name": "string",
      "purpose": "string",
      "key_values": ["VALUE1: meaning", "VALUE2: meaning"]
    }}
  ],
  "public_functions": [
    {{
      "signature": "return_type function_name(param_type param_name, ...)",
      "description": "What this function does and its purpose in the API"
    }}
  ],
  "api_boundaries": "string",
  "dependencies": ["module1", "module2"],
  "analyzed_files": {list(files_content.keys())}
}}

Focus on the most important and frequently used elements rather than exhaustively listing everything. The goal is to provide a clear understanding of the module's role and API for integration purposes.

IMPORTANT: Return only valid JSON - no markdown code blocks, no explanatory text, just the JSON object."""


@register(doc=read_prompt(module_dir(__file__) / "prompt.md"))
def summarize_module(args: SummarizeModuleArgs) -> SummarizeModuleResult:
    """Analyze and summarize a C module using LLM."""

    # Collect files to analyze
    files = collect_module_files(args.paths)

    # Read file contents
    files_content = {}
    for file_path in files:
        content = read_file_content(file_path)
        files_content[str(file_path.name)] = content

    # Determine module name from first file
    module_name = Path(args.paths[0]).stem if args.paths else "unknown"

    # Create analysis prompt
    prompt = create_analysis_prompt(files_content, module_name)

    # Use LiteLLM client with Gemini 2.5 Flash
    client = LiteLLMClient()

    messages = [LLMMessage(role=Role.USER, content=prompt)]

    # Call Gemini 2.5 Flash with structured JSON output
    response = client.completion(
        model="gemini/gemini-2.5-flash",
        messages=messages,
        tools=[],  # No tools needed for this analysis
        temperature=0.1,  # Low temperature for consistent analysis
        timeout_seconds=60,
        response_format={"type": "json_object"},
    )

    # Extract response content from the assistant message
    if not response.messages or len(response.messages) < 2:
        raise ValueError("Invalid response structure from LLM")
    
    content = response.messages[-1].content

    if not content:
        raise ValueError("Empty response from LLM")

    # Parse the JSON response directly
    result_data = json.loads(content)

    # Convert to our result model
    return SummarizeModuleResult(
        module_name=result_data.get("module_name", module_name),
        overview=result_data.get("overview", ""),
        key_structures=[
            ModuleStructure(**struct) for struct in result_data.get("key_structures", [])
        ],
        key_enums=[ModuleEnum(**enum) for enum in result_data.get("key_enums", [])],
        public_functions=[
            ModuleFunction(**func) for func in result_data.get("public_functions", [])
        ],
        api_boundaries=result_data.get("api_boundaries", ""),
        dependencies=result_data.get("dependencies", []),
        analyzed_files=list(files_content.keys()),
    )
