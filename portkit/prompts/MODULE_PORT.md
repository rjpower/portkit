# Chimera Build System - Module Implementation

Generate Rust module stub and testing infrastructure for a single C module.

Module specification in YAML format:
```yaml
{{module_yaml}}
```

## Required Outputs

You will output:

* A Rust module with an idiomatic Rust implementation of the C module
* A C compatible wrapper providing an _exact_ replica of the public C API,
* Fuzz test to validate your program against the original C library.
* Documentation for your newly ported module.

```
// src/<module>>/mod.rs

pub mod core;
pub mod ffi;

pub use core::*;


// src/dict/core.rs

pub struct Dict {
    // implementation
}

impl Dict {
    pub fn new() -> Self {
        Dict {}
    }
    
    pub fn insert(&mut self, key: String, value: String) {
        // implementation
    }
}

src/dict/ffi.rs

use std::ffi::{CStr, CString};
use std::os::raw::c_char;
use super::core::Dict;

pub struct XmlDict {}
pub type XmlDictPtr = usize;

static DICTS: OnceLock<Mutex<
    HashMap<XmlDictPtr, Box<XmlDict>, BuildHasherDefault<DefaultHasher>>
>> = OnceLock::new();


#[no_mangle]
pub extern "C" fn xmlDictCreate() -> XmlDictPtr
...
```

Follow the general coding guidelines from {{include:RUST_PORTING.md}}

### 2. Differential Fuzz Test (`fuzz/fuzz_<module_name>.rs`)

Generate a fuzz test that:
- Requires the rust module feature to compile
- Imports C version from bindings with aliased names
- Tests both implementations with identical inputs
- Asserts behavioral equivalence
- Handles the specific API patterns of this module

{{include: EXAMPLE_FUZZ_TEST.md}}

### 3. Porting summary

Document the resulting module in <module>/port.md

Your document should concisely summarize the Rust implementation including
example usage and potential concerns. Note any:

- Thread safety requirements  
- Special memory management patterns
- Dependencies on other modules