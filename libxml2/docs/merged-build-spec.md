# Merged Build System Specification - Symbol Swapping Strategy

## Overview

The merged build system enables selective compilation of libxml2 modules using either C or Rust implementations through a sophisticated **symbol swapping mechanism**. This creates multiple library variants that can be tested independently while maintaining full compatibility and functionality.

## Critical Design Goal

**PROBLEM**: Current approach disables C tests when Rust modules are enabled, preventing validation that Rust implementations work correctly with existing C code.

**SOLUTION**: Build multiple library variants with symbol swapping:
- `libxml2.so` - Pure C implementation for baseline testing
- `libxml2_rust.so` - Hybrid C+Rust with specific modules swapped
- Fuzz tests dynamically link against C-only version for differential testing
- C test suite runs against hybrid version to validate integration

## Architecture Overview

### Symbol Swapping Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                    SYMBOL NAMESPACE MANAGEMENT              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │   libxml2.so    │    │ libxml2_rust.so │                │
│  │  (C symbols)    │    │ (swapped symbols)│                │
│  │                 │    │                 │                │
│  │ xmlCharInRange  │    │ xmlCharInRange  │ ← Rust impl   │
│  │ xmlIsBaseChar   │    │ xmlIsBaseChar   │ ← Rust impl   │
│  │ xmlDictCreate   │    │ xmlDictCreate   │ ← C impl      │
│  │ xmlParseDoc     │    │ xmlParseDoc     │ ← C impl      │
│  └─────────────────┘    └─────────────────┘                │
│           │                       │                        │
│           ▼                       ▼                        │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │  Fuzz Tests     │    │  C Test Suite   │                │
│  │  (Baseline)     │    │  (Integration)  │                │
│  └─────────────────┘    └─────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

### Build Process Flow

```
Input: Feature Selection (rust-chvalid, rust-dict, etc.)
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│ PHASE 1: CONDITIONAL SOURCE SELECTION                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ C Sources:              Rust Modules:                      │
│ ├─ chvalid.c (skip)     ├─ chvalid::ffi (selected)         │
│ ├─ dict.c (include)     ├─ dict::ffi (not selected)        │
│ ├─ parser.c (include)   └─ ...                             │
│ └─ ...                                                      │
└─────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│ PHASE 2: DUAL LIBRARY COMPILATION                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ ┌─────────────────┐              ┌─────────────────┐        │
│ │ libxml2_c.a     │              │ libxml2_rust.a  │        │
│ │                 │              │                 │        │
│ │ All C modules   │              │ Selected C +    │        │
│ │ (no exclusions) │              │ Rust FFI mods   │        │
│ │                 │              │                 │        │
│ │ For baseline    │              │ For integration │        │
│ │ testing         │              │ testing         │        │
│ └─────────────────┘              └─────────────────┘        │
└─────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│ PHASE 3: DYNAMIC LIBRARY GENERATION                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ libxml2.so:                     libxml2_rust.so:           │
│ └─ From libxml2_c.a             └─ From libxml2_rust.a      │
│    (Pure C baseline)               (Hybrid C+Rust)         │
│                                                             │
│ Symbol Export Control:                                      │
│ ├─ C symbols: Standard visibility                          │
│ ├─ Rust symbols: #[no_mangle] + extern "C"                 │
│ └─ Linker precedence: Rust overrides C when present        │
└─────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│ PHASE 4: TEST HARNESS INTEGRATION                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Fuzz Tests:                     C Test Suite:              │
│ ├─ dlopen("libxml2.so")         ├─ Linked against          │
│ ├─ Get C baseline symbols       │   libxml2_rust.so        │
│ ├─ Compare with Rust impl       ├─ Uses swapped symbols    │
│ └─ Differential validation      └─ Integration validation  │
└─────────────────────────────────────────────────────────────┘
```

## Detailed Implementation Strategy

### 1. Build System Architecture

#### Modified build.rs Structure:

```rust
fn main() {
    // Determine Rust module selection
    let rust_modules = get_rust_modules();
    
    // ALWAYS build pure C library for baseline testing
    build_pure_c_library().expect("Failed to build C baseline");
    
    // Build hybrid library if Rust modules selected
    if !rust_modules.is_empty() {
        build_hybrid_library(&rust_modules).expect("Failed to build hybrid");
    }
    
    // Build test binaries against appropriate libraries
    build_test_binaries(&rust_modules).expect("Failed to build tests");
    
    // Generate bindings with dynamic library support
    generate_bindings_with_dynamic_support().expect("Failed to generate bindings");
    
    // Configure linking for final library selection
    setup_conditional_linking(&rust_modules);
}

fn build_pure_c_library() -> Result<(), Box<dyn std::error::Error>> {
    // Build ALL C sources (no exclusions)
    // Output: libxml2_c.a (complete C implementation)
    // Purpose: Baseline for fuzz testing
    
    let mut c_files = Vec::new();
    for (_, files) in MODULE_FILES {
        for file in *files {
            if file.ends_with(".c") {
                c_files.push(format!("../{}", file));
            }
        }
    }
    c_files.extend(ADDITIONAL_C_FILES.iter().map(|f| format!("../{}", f)));
    
    compile_c_library(&c_files, "libxml2_c")
}

fn build_hybrid_library(rust_modules: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    // Build C sources EXCLUDING Rust-replaced modules
    // Output: libxml2_hybrid.a (C + Rust FFI symbols)
    // Purpose: Integration testing with C test suite
    
    let mut excluded_files = HashSet::new();
    for module in rust_modules {
        if let Some((_, files)) = MODULE_FILES.iter().find(|(name, _)| *name == module) {
            for file in *files {
                excluded_files.insert(*file);
            }
        }
    }
    
    let mut c_files = Vec::new();
    for (_, files) in MODULE_FILES {
        for file in *files {
            if file.ends_with(".c") && !excluded_files.contains(file) {
                c_files.push(format!("../{}", file));
            }
        }
    }
    c_files.extend(ADDITIONAL_C_FILES.iter().map(|f| format!("../{}", f)));
    
    compile_c_library(&c_files, "libxml2_hybrid")
}
```

### 2. Dynamic Library Management

#### Cargo.toml Configuration:

```toml
[package]
name = "libxml2"
version = "0.1.0"
edition = "2021"

[lib]
name = "libxml2"
# Generate both static and dynamic libraries
crate-type = ["staticlib", "cdylib", "rlib"]

[features]
default = []

# Individual Rust module features
rust-chvalid = []
rust-dict = []
rust-hash = []
# ... etc

# Testing configurations
c-baseline = []          # Force pure C build for baseline
differential-testing = [] # Enable dynamic loading for fuzz tests

# Library variants
hybrid-build = ["rust-chvalid"]  # Example hybrid configuration

[dependencies]
libc = "0.2"
libloading = "0.8"  # For dynamic library loading in tests

[build-dependencies]
cc = "1.1"
bindgen = "0.69"
```

#### Dynamic Symbol Resolution:

```rust
// In fuzz tests - dynamically load C baseline
use libloading::{Library, Symbol};

pub struct CBaselineLibrary {
    lib: Library,
}

impl CBaselineLibrary {
    pub fn new() -> Result<Self, Box<dyn std::error::Error>> {
        // Load pure C library for baseline comparison
        let lib = unsafe { Library::new("target/debug/libxml2_c.so")? };
        Ok(CBaselineLibrary { lib })
    }
    
    pub fn get_xml_char_in_range(&self) -> Result<Symbol<unsafe extern "C" fn(u32, *const CXmlChRangeGroup) -> i32>, Box<dyn std::error::Error>> {
        unsafe { self.lib.get(b"xmlCharInRange") }
    }
    
    pub fn get_xml_is_base_char(&self) -> Result<Symbol<unsafe extern "C" fn(u32) -> i32>, Box<dyn std::error::Error>> {
        unsafe { self.lib.get(b"xmlIsBaseChar") }
    }
    
    // ... other baseline functions
}

// Updated fuzz test structure
fuzz_target!(|input: FuzzInput| {
    // Load C baseline dynamically
    let c_lib = CBaselineLibrary::new().expect("Failed to load C baseline");
    let c_xml_is_base_char = c_lib.get_xml_is_base_char().expect("Symbol not found");
    
    // Call C baseline (dynamically loaded)
    let c_result = unsafe { c_xml_is_base_char(input.char_code) };
    
    // Call Rust implementation (statically linked)
    let rust_result = libxml2::chvalid::is_base_char(input.char_code);
    
    // Compare results
    assert_eq!(c_result != 0, rust_result, 
        "Mismatch for char 0x{:x}: C={}, Rust={}", input.char_code, c_result, rust_result);
});
```

### 3. Bindgen Integration with Dynamic Loading

#### Enhanced bindgen Configuration:

```rust
fn generate_bindings_with_dynamic_support() -> Result<(), Box<dyn std::error::Error>> {
    // Generate bindings for BOTH static and dynamic use
    
    // Static bindings (for hybrid library)
    let static_bindings = bindgen::Builder::default()
        .header("wrapper.h")
        .parse_callbacks(Box::new(bindgen::CargoCallbacks::default()))
        .clang_arg("-I../include")
        .clang_arg("-I../include/libxml")
        .clang_arg("-I..")
        .clang_arg("-DHAVE_CONFIG_H")
        .clang_arg("-DLIBXML_STATIC")
        .allowlist_type(".*xml.*")
        .allowlist_function(".*xml.*")
        .allowlist_var(".*xml.*")
        .generate()?;
    
    // Dynamic bindings (for baseline testing)
    let dynamic_bindings = bindgen::Builder::default()
        .header("wrapper.h")
        .parse_callbacks(Box::new(bindgen::CargoCallbacks::default()))
        .clang_arg("-I../include")
        .clang_arg("-I../include/libxml")
        .clang_arg("-I..")
        .clang_arg("-DHAVE_CONFIG_H")
        .clang_arg("-DLIBXML_DYNAMIC")  // Different define for dynamic
        .allowlist_type(".*xml.*")
        .allowlist_function(".*xml.*")
        .allowlist_var(".*xml.*")
        // Prefix all symbols for dynamic use
        .module_raw_line("", "pub mod c_baseline {")
        .module_raw_line("", "    use super::*;")
        .generate()?;
    
    let out_path = PathBuf::from(env::var("OUT_DIR")?);
    static_bindings.write_to_file(out_path.join("bindings.rs"))?;
    dynamic_bindings.write_to_file(out_path.join("c_baseline_bindings.rs"))?;
    
    Ok(())
}
```

### 4. Test Integration Strategy

#### Differential Fuzz Testing:

```rust
// fuzz/fuzz_targets/fuzz_chvalid_differential.rs
#![no_main]
use libfuzzer_sys::fuzz_target;
use libxml2::{chvalid, c_baseline::*};
use libloading::{Library, Symbol};

lazy_static::lazy_static! {
    static ref C_LIBRARY: CBaselineLibrary = 
        CBaselineLibrary::new().expect("Failed to load C baseline library");
}

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    #[arbitrary(with = |u: &mut Unstructured| u.int_in_range(0..=0x10FFFF))]
    char_code: u32,
    
    function: CharFunction,
}

fuzz_target!(|input: FuzzInput| {
    match input.function {
        CharFunction::BaseChar => {
            // C baseline (dynamically loaded)
            let c_func = C_LIBRARY.get_xml_is_base_char().unwrap();
            let c_result = unsafe { c_func(input.char_code) };
            
            // Rust implementation (statically linked)
            let rust_result = chvalid::is_base_char(input.char_code);
            
            assert_eq!(c_result != 0, rust_result,
                "BaseChar mismatch for 0x{:x}: C={}, Rust={}", 
                input.char_code, c_result, rust_result);
        },
        // ... other function types
    }
});
```

### 5. Build Output Structure

#### Target Directory Layout:

```
target/debug/
├── liblibxml2_c.a              # Pure C static library
├── liblibxml2_hybrid.a         # Hybrid C+Rust static library  
├── libxml2_c.so                # Pure C dynamic library
├── libxml2_rust.so             # Hybrid dynamic library (default)
├── libxml2.rlib                # Rust library
│
├── test_binaries/
│   ├── runtest_c               # Linked against C library
│   ├── runtest_rust            # Linked against hybrid library
│   ├── testchar_c              # Linked against C library
│   ├── testchar_rust           # Linked against hybrid library
│   └── ...
│
└── fuzz/
    ├── baseline/               # For loading C library
    └── differential/           # For comparison testing
```

#### Library Selection Logic:

```rust
fn setup_conditional_linking(rust_modules: &[String]) {
    let out_dir = env::var("OUT_DIR").unwrap();
    
    if rust_modules.is_empty() {
        // Pure C build
        println!("cargo:rustc-link-lib=static=libxml2_c");
        println!("cargo:rustc-env=LIBXML2_VARIANT=c");
    } else {
        // Hybrid build
        println!("cargo:rustc-link-lib=static=libxml2_hybrid");
        println!("cargo:rustc-env=LIBXML2_VARIANT=hybrid");
        
        // Export hybrid library as default
        println!("cargo:rustc-link-arg=-Wl,-soname,libxml2.so");
    }
    
    // Always make both libraries available for testing
    println!("cargo:rustc-link-search=native={}", out_dir);
    
    // Set up test binary paths
    for test_name in TEST_BINARIES {
        println!("cargo:rustc-env=TEST_{}_C_BINARY={}/test_{}_c", 
            test_name.to_uppercase(), out_dir, test_name);
        println!("cargo:rustc-env=TEST_{}_RUST_BINARY={}/test_{}_rust", 
            test_name.to_uppercase(), out_dir, test_name);
    }
}
```

## Current State Assessment

### ✅ COMPLETED (from chvalid port):
1. **Rust Module Implementation**: Complete chvalid module with FFI layer
2. **Symbol Export**: All required C symbols properly exported via #[no_mangle]
3. **ABI Compatibility**: Struct layouts and function signatures match C exactly
4. **Unit Testing**: Core Rust functionality validated
5. **Build Feature Selection**: Feature flags control module selection
6. **C Source Exclusion**: Build system excludes C files when Rust enabled

### ❌ GAPS REQUIRING IMMEDIATE IMPLEMENTATION:
1. **Dual Library Build**: Currently only builds hybrid OR C, not both
2. **Dynamic Loading**: No mechanism for fuzz tests to load C baseline
3. **Test Binary Integration**: Tests disabled when Rust modules enabled
4. **Symbol Namespace Management**: No separation between C/Rust variants
5. **Bindgen Dynamic Support**: No dynamic library symbol generation

## Implementation Steps Required

### PHASE 1: Build System Restructure (HIGH PRIORITY)

1. **Modify build.rs to build BOTH libraries**:
   ```rust
   // ALWAYS build pure C (libxml2_c.a -> libxml2_c.so)
   build_pure_c_library()?;
   
   // IF Rust modules selected, ALSO build hybrid (libxml2_hybrid.a -> libxml2_rust.so)  
   if !rust_modules.is_empty() {
       build_hybrid_library(&rust_modules)?;
   }
   ```

2. **Create dual test binary sets**:
   ```rust
   // Build test binaries against BOTH libraries
   build_test_binaries_for_library("c", "libxml2_c")?;
   if !rust_modules.is_empty() {
       build_test_binaries_for_library("rust", "libxml2_hybrid")?;
   }
   ```

3. **Configure library output naming**:
   ```rust
   // Pure C: target/debug/libxml2_c.so
   // Hybrid: target/debug/libxml2_rust.so (or libxml2.so as default)
   ```

### PHASE 2: Dynamic Loading Infrastructure (HIGH PRIORITY)

1. **Add libloading dependency**:
   ```toml
   [dependencies]
   libloading = "0.8"
   ```

2. **Create C baseline loading wrapper**:
   ```rust
   // src/c_baseline.rs
   pub struct CBaselineLibrary { /* ... */ }
   impl CBaselineLibrary {
       pub fn new() -> Result<Self, Error> { /* ... */ }
       pub fn get_symbol<T>(&self, name: &[u8]) -> Result<Symbol<T>, Error> { /* ... */ }
   }
   ```

3. **Update bindgen for dual output**:
   ```rust
   // Generate both static bindings.rs AND c_baseline_bindings.rs
   ```

### PHASE 3: Test Framework Integration (MEDIUM PRIORITY)

1. **Restructure fuzz tests**:
   ```rust
   // Load C library dynamically in fuzz tests
   // Compare against statically linked Rust
   ```

2. **Enable C test suite**:
   ```rust
   // Remove test binary disabling from build.rs  
   // Create integration tests that run both variants
   ```

3. **Differential validation**:
   ```rust
   // Run same test against both libraries
   // Compare outputs for identical behavior
   ```

### PHASE 4: Integration Validation (MEDIUM PRIORITY)

1. **Cross-library compatibility tests**:
   - C test suite runs against hybrid library
   - Rust test suite validates against C baseline
   - Performance benchmarking between variants

2. **Symbol resolution verification**:
   - Ensure Rust symbols properly override C symbols
   - Validate no symbol conflicts in hybrid library
   - Test dynamic loading works correctly

### PHASE 5: Documentation & Tooling (LOW PRIORITY)

1. **Developer documentation**: Update build instructions
2. **CI/CD integration**: Automated testing of both variants  
3. **Performance monitoring**: Benchmark regression detection

## Critical Success Metrics

### Functional Validation:
- ✅ Pure C library builds and all tests pass (baseline)
- ✅ Hybrid library builds with Rust modules enabled  
- ✅ Fuzz tests load C baseline dynamically and compare with Rust
- ✅ C test suite runs successfully against hybrid library
- ✅ Identical test results between C and hybrid variants

### Performance Validation:
- ✅ No performance regression in C-only mode
- ✅ Rust modules match or exceed C performance
- ✅ Library loading overhead acceptable for testing

### Integration Validation:
- ✅ Symbol swapping works correctly at runtime
- ✅ No undefined symbol errors in any configuration
- ✅ Memory layout compatibility maintained
- ✅ Thread safety preserved across C/Rust boundary

## Risk Mitigation

### HIGH RISK: Symbol Conflicts
- **Mitigation**: Careful linker ordering, separate library builds
- **Validation**: Symbol table inspection, runtime loading tests

### MEDIUM RISK: ABI Incompatibility  
- **Mitigation**: Extensive #[repr(C)] usage, bindgen validation
- **Validation**: Cross-library function calls, struct layout tests

### LOW RISK: Performance Regression
- **Mitigation**: Benchmark-driven development, optimization profiles
- **Validation**: Continuous performance monitoring

## Timeline Estimate

- **Phase 1** (Build System): 1-2 days
- **Phase 2** (Dynamic Loading): 1-2 days  
- **Phase 3** (Test Integration): 1-2 days
- **Phase 4** (Validation): 1-2 days
- **Phase 5** (Documentation): 0.5-1 day

**Total: 4.5-8 days for complete implementation**

This symbol swapping strategy provides the robust testing framework needed to validate C-to-Rust migrations while maintaining full compatibility and enabling differential validation.