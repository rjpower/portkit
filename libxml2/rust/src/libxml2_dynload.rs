use std::sync::OnceLock;
use crate::dynamic_bindings::libxml2_c;

static C_LIBRARY: OnceLock<libxml2_c> = OnceLock::new();

/// Get the global C baseline library instance (lazy-loaded)
/// Uses bindgen-generated dynamic library loader with smart path resolution
pub fn get_c_baseline() -> &'static libxml2_c {
    C_LIBRARY.get_or_init(|| {
        // Try multiple possible paths for the dynamic library
        let lib_path = if cfg!(target_os = "windows") {
            "liblibxml2_c.dll"
        } else if cfg!(target_os = "macos") {
            "liblibxml2_c.dylib"
        } else {
            "liblibxml2_c.so"
        };
        
        let paths_to_try = [
            format!("target/release/build/{}", lib_path),
            format!("target/debug/build/{}", lib_path),
            format!("../target/release/build/{}", lib_path),
            format!("../target/debug/build/{}", lib_path),
            format!("../../target/release/build/{}", lib_path),
            format!("../../target/debug/build/{}", lib_path),
        ];
        
        // Try direct paths first
        for path in &paths_to_try {
            if std::path::Path::new(path).exists() {
                if let Ok(lib) = unsafe { libxml2_c::new(path) } {
                    return lib;
                }
            }
        }
        
        // Fallback: find the library using glob pattern
        let pattern = if cfg!(target_os = "windows") {
            "target/*/build/libxml2-*/out/libxml2_c.dll"
        } else if cfg!(target_os = "macos") {
            "target/*/build/libxml2-*/out/liblibxml2_c.dylib"
        } else {
            "target/*/build/libxml2-*/out/liblibxml2_c.so"
        };
        
        if let Ok(entries) = glob::glob(pattern) {
            for entry in entries.flatten() {
                if let Ok(lib) = unsafe { libxml2_c::new(entry) } {
                    return lib;
                }
            }
        }
        
        panic!("Failed to load C baseline library from any location. Tried paths: {:?}", paths_to_try);
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_c_baseline_loading() {
        let c_lib = get_c_baseline();
        // Test basic function availability
        assert!(c_lib.xmlIsBaseChar.is_ok(), "Failed to load xmlIsBaseChar symbol");
        assert!(c_lib.xmlIsChar.is_ok(), "Failed to load xmlIsChar symbol");
    }
    
    #[test] 
    fn test_symbol_functionality() {
        let c_lib = get_c_baseline();
        
        // Test that symbols work correctly
        unsafe {
            // Test with ASCII 'A' (0x41) which should be a valid char
            let result = c_lib.xmlIsChar(0x41);
            assert_ne!(result, 0, "ASCII 'A' should be a valid XML character");
            
            // Test with null character which should be invalid
            let result = c_lib.xmlIsChar(0x00);
            assert_eq!(result, 0, "Null character should not be a valid XML character");
        }
    }
}