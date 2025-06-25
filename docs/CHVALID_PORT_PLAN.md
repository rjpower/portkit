# libxml2 chvalid Module Porting Plan

## Overview
This document outlines the complete plan for porting the libxml2 chvalid (character validation) module from C to Rust.

## Module Analysis

### C Module Structure
- **File**: `chvalid.c` (175 lines)
- **Header**: `include/libxml/chvalid.h` 
- **Dependencies**: `codegen/ranges.inc` (character range tables)

### Core Functionality
The chvalid module provides Unicode character validation for XML parsing:

1. **Character Range Validation**: Binary search through predefined Unicode ranges
2. **Character Category Checks**: BaseChar, Blank, Char, Combining, Digit, Extender, Ideographic, PubidChar
3. **Lookup Tables**: Precomputed tables for ASCII (0-255) character validation
4. **Range Groups**: Hierarchical data structures for efficient Unicode range queries

### Public API Functions
- `xmlCharInRange(unsigned int val, const xmlChRangeGroup *group)` - Core range validation
- `xmlIsBaseChar(unsigned int ch)` - DEPRECATED wrapper  
- `xmlIsBlank(unsigned int ch)` - DEPRECATED wrapper
- `xmlIsChar(unsigned int ch)` - DEPRECATED wrapper
- `xmlIsCombining(unsigned int ch)` - DEPRECATED wrapper
- `xmlIsDigit(unsigned int ch)` - DEPRECATED wrapper
- `xmlIsExtender(unsigned int ch)` - DEPRECATED wrapper
- `xmlIsIdeographic(unsigned int ch)` - DEPRECATED wrapper
- `xmlIsPubidChar(unsigned int ch)` - DEPRECATED wrapper

### Macro API (Preferred)
- `xmlIsBaseCharQ(c)` - Fast BaseChar validation with ASCII optimization
- `xmlIsBlankQ(c)` - Fast Blank validation
- `xmlIsCharQ(c)` - Fast Char validation with direct Unicode ranges
- `xmlIsCombiningQ(c)` - Fast Combining validation
- `xmlIsDigitQ(c)` - Fast Digit validation
- `xmlIsExtenderQ(c)` - Fast Extender validation  
- `xmlIsIdeographicQ(c)` - Fast Ideographic validation with hardcoded ranges
- `xmlIsPubidCharQ(c)` - Fast PubidChar validation using lookup table

### Data Structures
```c
typedef struct _xmlChSRange {
    unsigned short low;
    unsigned short high;
} xmlChSRange;

typedef struct _xmlChLRange {
    unsigned int low;
    unsigned int high;
} xmlChLRange;

typedef struct _xmlChRangeGroup {
    int nbShortRange;
    int nbLongRange;
    const xmlChSRange *shortRange;
    const xmlChLRange *longRange;
} xmlChRangeGroup;
```

### Global Range Groups
- `xmlIsBaseCharGroup` - 197 short ranges
- `xmlIsCharGroup` - 2 short ranges, 1 long range
- `xmlIsCombiningGroup` - 95 short ranges
- `xmlIsDigitGroup` - 14 short ranges
- `xmlIsExtenderGroup` - 10 short ranges
- `xmlIsIdeographicGroup` - 3 short ranges
- `xmlIsPubidChar_tab[256]` - ASCII lookup table

## Implementation Strategy

### Phase 1: Rust Core Implementation

#### Data Structures
```rust
pub struct ChSRange {
    pub low: u16,
    pub high: u16,
}

pub struct ChLRange {
    pub low: u32,
    pub high: u32,
}

pub struct ChRangeGroup {
    pub short_ranges: &'static [ChSRange],
    pub long_ranges: &'static [ChLRange],
}
```

#### Core Functions
```rust
pub fn char_in_range(val: u32, group: &ChRangeGroup) -> bool;
pub fn is_base_char(ch: u32) -> bool;
pub fn is_blank(ch: u32) -> bool;
pub fn is_char(ch: u32) -> bool;
pub fn is_combining(ch: u32) -> bool;
pub fn is_digit(ch: u32) -> bool;
pub fn is_extender(ch: u32) -> bool;
pub fn is_ideographic(ch: u32) -> bool;
pub fn is_pubid_char(ch: u32) -> bool;
```

### Phase 2: C-Compatible FFI Layer

#### FFI Structures
```rust
#[repr(C)]
pub struct xmlChSRange {
    pub low: c_ushort,
    pub high: c_ushort,
}

#[repr(C)]
pub struct xmlChLRange {
    pub low: c_uint,
    pub high: c_uint,
}

#[repr(C)]
pub struct xmlChRangeGroup {
    pub nbShortRange: c_int,
    pub nbLongRange: c_int,
    pub shortRange: *const xmlChSRange,
    pub longRange: *const xmlChLRange,
}
```

#### FFI Functions
```rust
#[no_mangle]
pub extern "C" fn xmlCharInRange(val: c_uint, rptr: *const xmlChRangeGroup) -> c_int;

#[no_mangle]
pub extern "C" fn xmlIsBaseChar(ch: c_uint) -> c_int;
// ... all other deprecated functions
```

### Phase 3: Build System Integration

#### Cargo Configuration
- Add `chvalid` feature to enable Rust implementation
- Configure conditional compilation for C/Rust selection
- Set up static linking for FFI layer

#### CMake Integration
- Add option to use Rust implementation
- Link Rust static library when enabled
- Preserve original C build when disabled

### Phase 4: Differential Fuzz Testing

#### Fuzz Test Structure
```rust
#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    #[arbitrary(with = |u: &mut Unstructured| u.int_in_range(0..=0x10FFFF))]
    char_code: u32,
    
    range_group_type: RangeGroupType,
}

fuzz_target!(|input: FuzzInput| {
    let c_result = unsafe { ffi::xmlIsBaseChar(input.char_code) };
    let rust_result = chvalid::is_base_char(input.char_code);
    assert_eq!(c_result != 0, rust_result);
});
```

### Phase 5: Integration Testing

#### Test Plan
1. **Unit Tests**: Test individual character validation functions
2. **Range Tests**: Verify boundary conditions for Unicode ranges  
3. **Performance Tests**: Compare C vs Rust performance
4. **Integration Tests**: Test with existing libxml2 C test suite
5. **Regression Tests**: Ensure no behavioral changes

## Implementation Files

### Rust Module Structure
```
libxml2/rust/src/chvalid/
├── mod.rs           # Module exports
├── core.rs          # Core Rust implementation
├── ffi.rs           # C-compatible FFI layer
├── ranges.rs        # Static range data
└── tests.rs         # Unit tests
```

### Fuzz Test
```
libxml2/rust/fuzz/fuzz_targets/
└── fuzz_chvalid.rs  # Differential fuzz testing
```

### Documentation
```
libxml2/rust/src/chvalid/
└── port.md          # Porting documentation
```

## Success Criteria

1. **Functional Equivalence**: All C functions have identical Rust counterparts
2. **Performance Parity**: Rust implementation matches or exceeds C performance
3. **Memory Safety**: No undefined behavior or memory errors
4. **API Compatibility**: Existing C code works without modification
5. **Test Coverage**: 100% differential fuzz test coverage
6. **Build Integration**: Seamless build system integration

## Risk Mitigation

### Potential Issues
1. **Unicode Range Accuracy**: Ensure exact match with libxml2's Unicode tables
2. **Performance Regression**: Binary search optimization in Rust
3. **Build Complexity**: Cross-compilation and linking challenges
4. **API Compatibility**: Exact C ABI compliance

### Mitigation Strategies
1. **Data Validation**: Extensive testing against original C implementation
2. **Performance Testing**: Benchmark-driven optimization
3. **Incremental Integration**: Gradual rollout with fallback options
4. **Comprehensive Testing**: Differential fuzzing and integration tests

## Timeline Estimate

- **Phase 1 (Core)**: 2-3 hours
- **Phase 2 (FFI)**: 1-2 hours  
- **Phase 3 (Build)**: 1-2 hours
- **Phase 4 (Fuzz)**: 1 hour
- **Phase 5 (Test)**: 1-2 hours
- **Total**: 6-10 hours

This plan provides a comprehensive roadmap for successfully porting the libxml2 chvalid module to Rust while maintaining full compatibility and performance.