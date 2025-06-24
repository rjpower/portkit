# Project Analysis Tool Specification

## Overview

This tool performs hierarchical analysis of C projects for migration planning. It uses a three-stage pipeline:

1. **Module Identification**: Analyze sourcemap to identify logical module boundaries
2. **Parallel Module Summarization**: Generate detailed summaries for each identified module
3. **Project Summary Generation**: Combine module summaries into overall project analysis

## Architecture

```
tools/analyze_project/
├── spec.md                      # This specification
├── main.py                      # CLI entry point and orchestration
├── lib.py                       # Core analysis logic
├── prompts/
│   ├── group_modules.md         # Stage 1: Module boundary identification
│   ├── summarize_modules.md     # Stage 2: Individual module analysis
│   └── project_summary.md       # Stage 3: Overall project synthesis
└── models.py                    # Pydantic models for structured output
```

## Data Flow

### Input
- `sourcemap.txt`: Dependency graph in CSV format (`name,kind,location,is_cycle,is_static,dependencies`)

### Stage 1: Module Identification
- **Input**: Sourcemap + project file structure
- **Model**: Group related functions/files into logical modules
- **Output**: List of modules with files, estimated LOC, dependencies

### Stage 2: Module Summarization  
- **Input**: Module file lists from Stage 1
- **Process**: Run summarize_module tool in parallel for each module
- **Output**: Individual YAML summaries (reusing existing format)

### Stage 3: Project Summary
- **Input**: All module summaries + original sourcemap
- **Model**: Synthesize into overall project understanding
- **Output**: Top-level markdown document

## Output Structure

### Final Output: `PROJECT_ANALYSIS.md`
```markdown
# Project Analysis: {project_name}

## Overview
[High-level project purpose and architecture]

## Module Layout
[Table of modules with descriptions and dependencies]

## Migration Strategy
[Recommended porting order and considerations]

## Module Details
- [Module 1](module_analysis/00001-module1.yaml)
- [Module 2](module_analysis/00002-module2.yaml)
...
```

### Individual Module Files: `module_analysis/{index:05d}-{name}.yaml`
Reuses existing format from libxml2 example.

## Implementation

1. **Module Boundary Detection**:
   - Never split a file
   - You may group utility modules if they have related functionality.
   - Circular module dependencies should be processed as a _single combined module_

2. **Parallelization**: 
   - Use asyncio with N parallel calls to the summarize_project tool
   - Don't rate limit

3. **Error Handling**:
   - Fail if any summarization fails.
   - Cache results across runs and re-use.

4. **Configuration**:
   - Should LOC thresholds be configurable? Yes via Click flag.
   - Which LLM model to use for each stage? Gemini-2.5-Flash for summary, 2.5-Pro for strong analysis.