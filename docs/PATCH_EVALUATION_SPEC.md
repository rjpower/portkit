# Patch Tool Evaluation Specification

## Overview

This document specifies the evaluation suite for the `portkit.tidyllm.tools.patch_file` tool. The evaluation tests the tool's ability to correctly interpret natural language requests and apply appropriate patches to C header files from the libxml2 library.

## Objectives

1. Verify the LLM can correctly interpret various patching scenarios
2. Ensure patches are correctly formatted and applied
3. Test edge cases and complex modifications
4. Validate proper handling of C syntax and formatting

## Test Files

All tests will use real files from `/home/power/code/portkit/libxml2/include/libxml/` to ensure realistic scenarios.

## Evaluation Test Cases

### 1. Single Line Replacement
**File**: `tree.h`
**Task**: Replace a single macro definition
**Prompt**: "In tree.h, change the value of xmlDefaultBufferSize from 4096 to 8192"
**Expected**: The macro definition should be updated while preserving formatting

### 2. Multiple Line Replacement
**File**: `xmlerror.h`
**Task**: Replace a multi-line comment block
**Prompt**: "Replace the copyright notice at the top of xmlerror.h with a new simplified version: '/* Copyright (C) 2024 LibXML2 Project */'"
**Expected**: The entire multi-line comment block should be replaced with the single line

### 3. Type Renaming Across File
**File**: `dict.h`
**Task**: Rename a type throughout the file
**Prompt**: "In dict.h, rename all occurrences of 'xmlDict' to 'xmlDictionary'"
**Expected**: All instances should be renamed, including in function declarations and comments

### 4. Function Declaration Addition
**File**: `parser.h`
**Task**: Add a new function declaration
**Prompt**: "Add a new function declaration 'xmlParseEx' after 'xmlParse' in parser.h with the same signature but taking an additional 'int flags' parameter"
**Expected**: New declaration added with proper formatting and alignment

### 5. Enum Value Insertion
**File**: `xmlerror.h`
**Task**: Add a new enum value
**Prompt**: "In xmlerror.h, add a new error code 'XML_ERR_CUSTOM = 5000' at the end of the xmlErrorDomain enum"
**Expected**: New enum value added before the closing brace

### 6. Include Guard Modification
**File**: `hash.h`
**Task**: Standardize include guards
**Prompt**: "Change the include guard in hash.h from '__XML_HASH_H__' to 'LIBXML2_HASH_H'"
**Expected**: All three occurrences (#ifndef, #define, comment) updated

### 7. Function Parameter Update
**File**: `tree.h`
**Task**: Add const qualifier to parameters
**Prompt**: "In tree.h, add 'const' qualifier to all char* parameters in xmlNewText function"
**Expected**: Function declaration updated with const qualifiers

### 8. Macro Definition Complex Update
**File**: `tree.h`
**Task**: Update a complex macro
**Prompt**: "Modify the XML_GET_CONTENT macro to add a NULL check: change it to '((n) && (n)->type == XML_ELEMENT_NODE ? NULL : (n)->content)'"
**Expected**: Macro updated while preserving backslash continuation

### 9. Structure Field Addition
**File**: `tree.h`
**Task**: Add a field to a structure
**Prompt**: "In the xmlNode structure, add a new field 'void *userData;' after the 'content' field"
**Expected**: Field added with proper indentation and semicolon

### 10. Comment Style Conversion
**File**: `parser.h`
**Task**: Convert comment style
**Prompt**: "Convert all single-line C++ style comments (starting with //) to C style comments (/* ... */) in the first 50 lines of parser.h"
**Expected**: All // comments converted to /* */ format

### 11. Typedef Addition
**File**: `xmlstring.h`
**Task**: Add a new typedef
**Prompt**: "Add a typedef for 'xmlString' as 'typedef xmlChar * xmlString;' after the xmlChar typedef"
**Expected**: New typedef added with proper formatting

### 12. Whitespace Normalization
**File**: `uri.h`
**Task**: Fix inconsistent spacing
**Prompt**: "In uri.h, ensure all function declarations have exactly one space between the return type and function name"
**Expected**: Spacing normalized without changing functionality

### 13. Header Reorganization
**File**: `valid.h`
**Task**: Group related declarations
**Prompt**: "Move all xmlValid* function declarations to be grouped together at the end of the file, before the closing extern C"
**Expected**: Functions moved while preserving their declarations

### 14. Preprocessor Directive Update
**File**: `xmlversion.h.in`
**Task**: Update version checks
**Prompt**: "Change all occurrences of '#if LIBXML_VERSION >= 20900' to '#if LIBXML_VERSION >= 21000'"
**Expected**: All version checks updated

### 15. Error Message Update
**File**: `xmlerror.h`
**Task**: Update error message strings
**Prompt**: "In all string literals containing 'parser error', change them to 'parsing error'"
**Expected**: String literals updated while preserving quotes

## Evaluation Criteria

Each test will be evaluated on:

1. **Correctness**: The patch achieves the intended modification
2. **Precision**: Only the specified changes are made
3. **Formatting**: Original file formatting is preserved
4. **Completeness**: All instances are updated when "all" is specified
5. **Syntax**: The resulting code remains syntactically valid

## Implementation Notes

- Use the `@evaluation_test` decorator for each test case
- Each test should read the actual file content from libxml2
- Verify the patch was applied correctly by checking the modified content
- Use assertions to validate specific changes
- Handle both successful patches and expected failures

## Success Metrics

- All 15 test cases should pass
- Patches should apply cleanly without conflicts
- Modified files should maintain valid C syntax
- No unintended modifications should occur