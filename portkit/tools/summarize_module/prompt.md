# C Module Summarization Tool

Analyze and summarize C/C++ modules to understand their structure, APIs, and functionality using AI-powered code analysis.

## Purpose

This tool uses Gemini 2.5 Flash to analyze C header and source files, providing comprehensive summaries that help developers understand:

- Module purpose and overall functionality
- Key data structures and their roles
- Important enumerations and error codes
- Public API functions and interfaces
- Dependencies and relationships with other modules
- Integration points and usage patterns

## Parameters

- **paths** (required): List of C/C++ file paths to analyze
  - Supported extensions: .h, .c, .cc, .cpp, .hpp
  - Examples: `["libxml2/include/libxml/xpath.h"]`, `["header.h", "impl.c"]`
  - All files must exist and be valid C/C++ source files

## Examples

### Analyze Single Header File
```json
{
  "paths": ["libxml2/include/libxml/xpath.h"]
}
```
**Use case**: Understanding public API of a specific module like XPath functionality.

### Analyze Module with Implementation
```json
{
  "paths": ["include/xpath.h", "src/xpath.c"]
}
```
**Use case**: Full analysis including implementation details for porting or refactoring.

### Analyze Multiple Related Files
```json
{
  "paths": [
    "include/network/socket.h",
    "include/network/protocol.h", 
    "src/network/socket.c"
  ]
}
```
**Use case**: Understanding a complete subsystem with multiple header and source files.

## Return Value

The tool returns a comprehensive `SummarizeModuleResult` with:

### Core Information
- **module_name**: Identified module name/identifier
- **overview**: High-level description of module purpose and functionality
- **analyzed_files**: List of files that were processed

### Structural Analysis
- **key_structures**: Important data structures with:
  - Structure name and purpose
  - Key fields and their meanings
  - Role in module functionality

- **key_enums**: Important enumerations with:
  - Enum name and what it represents
  - Key values and their meanings
  - Usage patterns in the API

### API Analysis  
- **public_functions**: Key public functions with:
  - Function name and purpose
  - Parameter types and meanings
  - Return type and semantics
  - Role in the overall API

### Integration Information
- **api_boundaries**: Description of how module interfaces with other components
- **dependencies**: List of other modules/libraries this module depends on

## Usage Scenarios

### 1. Code Documentation
Generate comprehensive module documentation for existing C libraries:
```json
{
  "paths": ["include/libxml/tree.h"]
}
```

### 2. API Understanding for Integration
Understand how to use a C library in your project:
```json
{
  "paths": [
    "third_party/lib/networking/socket.h",
    "third_party/lib/networking/protocol.h",
    "third_party/lib/networking/utils.h"
  ]
}
```

### 3. Porting Preparation
Analyze modules before porting to another language:
```json
{
  "paths": ["legacy_src/core_module.h", "legacy_src/core_module.c"]
}
```

### 4. Code Review and Analysis
Understand unfamiliar codebases:
```json
{
  "paths": [
    "vendor/library/src/main.h",
    "vendor/library/src/engine.h", 
    "vendor/library/src/utils.c"
  ]
}
```

## Technical Details

- **AI Model**: Uses Gemini 2.5 Flash for code analysis
- **File Size Limits**: Large files are truncated to ~50,000 characters to fit context limits
- **Supported Languages**: C, C++ (extensions: .h, .c, .cc, .cpp)
- **Analysis Focus**: Prioritizes public APIs, key structures, and integration points
- **Error Handling**: Gracefully handles unreadable files and analysis failures

## Output Quality

The tool focuses on providing:
- **Actionable insights** for developers who need to use or modify the module
- **Clear explanations** of complex data structures and their relationships
- **API-focused analysis** highlighting the most important functions for integration
- **Dependency mapping** to understand module relationships
- **Practical examples** showing how structures and functions work together

The analysis prioritizes clarity and usefulness over exhaustive completeness, focusing on the elements most important for understanding and using the module effectively.