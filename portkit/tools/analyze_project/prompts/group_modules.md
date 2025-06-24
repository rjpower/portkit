# Stage 1: Module Identification for C-to-Rust Migration

Analyze a C project's dependency graph and file structure to identify logical modules suitable for incremental Rust migration.

## Input

The project dependency graph is as follows:

```
{{sourcemap}}
```

Format: `name,kind,location,is_cycle,is_static,dependencies`

## Task

Analyze the dependency graph and source structure to identify logical modules that:

1. Group related functionality with clear API boundaries
2. Contain approximately 500-1000 lines of C code each
3. Have minimal circular dependencies between modules
4. Represent cohesive units of functionality

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
   - C source files should never be broken across module boundaries

3. **Dependency Analysis**:
   - Identify which modules depend on which others
   - Flag circular dependencies that need resolution
   - Note if modules share private/internal headers

## Output Format

Return a JSON object with this structure:

```json
{
  "modules": [
    {
      "name": "dict",
      "description": "Dictionary/hash table implementation for string interning",
      "estimated_loc": 750,
      "c_files": ["dict.c"],
      "header_files": ["include/libxml/dict.h", "include/private/dict.h"],
      "key_functions": ["xmlDictCreate", "xmlDictFree", "xmlDictLookup"],
      "dependencies": ["xmlstring"],
      "api_quality": "clean",
      "notes": "Self-contained module with opaque pointer API"
    }
  ],
  "processing_order": ["xmlstring", "dict", "hash", "tree", "parser"]
}
```

Focus on creating modules that can be ported independently with minimal interdependencies.