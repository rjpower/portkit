# Stage 1: Module Identification for C-to-Rust Migration

Analyze a C project's dependency graph to identify logical modules suitable for incremental Rust migration.

## Input

The project dependency graph is as follows.

```
{{include: sourcemap.txt}}
```

Format: `function_name,type,source_location,metadata,dependencies`

## Task

Analyze the dependency graph and source structure to identify logical modules that:

1. Group related functionality with clear API boundaries
2. Contain approximately 500-1000 lines of C code each
3. Have minimal circular dependencies between modules
4. Represent cohesive units of functionality

You will output a summary file for each module, indicating the module
dependencies and summary information relevant to porting the module to Rust,
including any warnings or issues that might occur during integration. Your
summary must be _complete_: if an engineer was given your summary and _no other
information_, they should be able to sucessfully construct a Rust port for the
module.

First, create a task list consisting of every header & source file in the repository.
You will check entries off this task list as you analyze the codebase and write module summary files.

## Tools

Module summarization:

This tool will summarize any modules you specify. You may use it as much as needed to understand the file structure.

`uv run python -m portkit.tools.summarize_module --paths=dict.c --paths=include/libxml/dict.h`

The output will be something like: 

```
{
  "module_name": "dict",
  "overview": "The 'dict' module provides a string dictionary (interning) service for libxml2. Its primary responsibility is to efficiently store and manage reusable strings, such as element names, attribute names, and namespace URIs, to avoid redundant memory allocations and enable fast string comparisons (by pointer). It uses a hash table for quick lookups and memory pools for contiguous string storage, supporting hierarchical dictionaries and thread-safe operations.",
  "key_structures": [
    {
      "name": "xmlDict",
      "purpose": "The primary structure representing a string dictionary. It manages the hash table for string lookups and the memory pools where the actual string data is stored.",
      "key_fields": [
        "ref_counter: Tracks references to the dictionary, enabling shared dictionaries.",
        "table: Pointer to the hash table array (xmlDictEntrys) for efficient string lookup.",
        "strings: Pointer to a linked list of xmlDictStrings pools, where string data is allocated.",
        "subdict: Optional pointer to a parent dictionary for hierarchical string lookups.",
        "limit: Maximum memory usage allowed for string storage."
      ]
    },
    ...
  ],
  "key_enums": [],
  "public_functions": [
    {
      "signature": "int xmlInitializeDict(void)",
      "description": "Deprecated. Alias for xmlInitParser. Initializes parser-related global state."
    },
    ...
  ]
}
```

## Output

For each output module, create a generate a `module_analysis/{%05d-index}{module}.yaml` with the following structure, with one entry for every output module you produce.
The index value indicates the order the module should be processed. Modules should be ordered in _dependency order_, with the most basic modules coming first.

```yaml
module:
  name: dict
  description: "Dictionary/hash table implementation for string interning"
  estimated_loc: 750
  c_files:
    - dict.c
  header_files:
    - include/libxml/dict.h
    - include/private/dict.h
  key_functions:
    - xmlDictCreate
    - xmlDictFree
    - xmlDictLookup
    - xmlDictReference
    - xmlDictSize
  dependencies:
    # dependent modules in this library.
    - foo
  api_overview: |
    Implements the string interning dictionary for libxml2.
    As this uses an opaque dictionary, you may use a pure Rust implementation
    with the standard HashMap based thunk.
```

## Analysis Guidelines

1. **Module Boundaries**: Look for:
   - Common prefixes (e.g., `xmlDict*`, `xmlList*`)
   - Single source files that implement a complete feature
   - Groups of functions that operate on the same data structures
   - Natural abstraction boundaries in the code

2. **Size Constraints**:
   - Prefer modules of 500-1000 LOC for manageable porting
   - Can go up to 1500 LOC if splitting would break cohesion
   - Very small modules (<300 LOC) can be grouped if related
   - C source files should never be broken across module boundaries.

3. **Dependency Analysis**:
   - Identify which modules depend on which others
   - Flag circular dependencies that need resolution
   - Note if modules share private/internal headers

4. **API Quality Assessment**:
   - Rate how clean the module boundary is (clean/moderate/tangled)
   - Identify if the module uses opaque pointers (good for FFI)
   - Note any global state or initialization requirements
