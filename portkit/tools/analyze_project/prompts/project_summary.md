# Stage 3: Project Summary Generation

Generate a comprehensive project analysis document that synthesizes individual module summaries into an overall migration strategy.

## Input

You have been provided with:

1. **Project sourcemap**: Complete dependency graph of the C project
2. **Module summaries**: Detailed analysis of each identified module
3. **Module grouping**: How the project was divided into logical units

## Module Summaries

{{module_summaries}}

## Module Dependencies

{{module_dependencies}}

## Task

Create a comprehensive project analysis that includes:

1. **High-level project overview**: What does this project do? What is its primary purpose?
2. **Architecture summary**: How are the modules organized? What are the key abstractions?
3. **Migration strategy**: Recommended order for porting modules to Rust
4. **Risk assessment**: Which modules are most complex or have the most dependencies?
5. **Integration considerations**: How should the modules interact during incremental migration?

## Analysis Requirements

### Project Overview
- Identify the project's main purpose and target domain
- Summarize the key functionality and APIs provided
- Note the project's size and complexity

### Module Architecture
- Describe how modules relate to each other
- Identify core vs. peripheral modules
- Note any architectural patterns (layered, plugin-based, etc.)

### Migration Strategy
- Recommend porting order based on dependencies and complexity
- Identify modules that can be ported in parallel
- Suggest FFI integration points for gradual migration
- Highlight modules that should be ported together due to tight coupling

### Risk Assessment
- Flag modules with complex dependencies
- Identify modules with significant global state
- Note modules that might require extensive Rust-specific design changes
- Highlight potential performance-critical sections

### Integration Considerations
- Suggest strategies for maintaining C/Rust interoperability during migration
- Identify shared data structures that need careful handling
- Note modules that might benefit from pure Rust reimplementation vs. FFI wrapping

## Output Format

Generate a markdown document with the following structure:

```markdown
# Project Analysis: [Project Name]

## Overview
[2-3 paragraph summary of project purpose and scope]

## Architecture
[Description of module organization and key patterns]

## Module Summary
| Module | LOC | Dependencies | Complexity | Notes |
|--------|-----|--------------|------------|-------|
| ... | ... | ... | ... | ... |

## Migration Strategy

### Phase 1: Foundation Modules
[Modules with minimal dependencies that can be ported first]

### Phase 2: Core Functionality  
[Main algorithmic modules that depend on foundation]

### Phase 3: Integration Modules
[Modules that tie everything together]

## Risk Assessment

### High Risk Modules
[Modules that will be challenging to port]

### Medium Risk Modules
[Modules with moderate complexity]

### Low Risk Modules
[Straightforward modules for early wins]

## Implementation Recommendations

### FFI Strategy
[How to maintain C compatibility during incremental migration]

### Testing Strategy
[How to validate behavioral equivalence]

### Performance Considerations
[Modules where performance is critical]

## Module Details
[Links to individual module analysis files]
- [Module 1](module_analysis/00001-module1.yaml)
- [Module 2](module_analysis/00002-module2.yaml)
...
```

Focus on providing actionable guidance for engineers planning the C-to-Rust migration.