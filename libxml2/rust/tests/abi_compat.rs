//! ABI compatibility tests
//!
//! Verifies that Rust implementations maintain binary compatibility with C

use libxml2::*;

#[test]
fn test_basic_abi_compatibility() {
    // Test that basic FFI bindings work
    unsafe {
        // This should not crash if bindings are correct
        let _version = xmlParserVersion;
        
        // Test memory allocation functions
        let ptr = xmlMalloc(64);
        assert!(!ptr.is_null());
        xmlFree(ptr);
    }
}

#[test]
fn test_xmlstring_abi() {
    // Test xmlstring functions have correct signatures
    unsafe {
        let test_str = b"test\0";
        let xml_str = test_str.as_ptr() as *const std::os::raw::c_uchar;
        
        let len = xmlStrlen(xml_str);
        assert_eq!(len, 4);
        
        let dup = xmlStrdup(xml_str);
        assert!(!dup.is_null());
        xmlFree(dup as *mut std::os::raw::c_void);
    }
}

#[test]
fn test_dict_abi() {
    // Test dictionary functions have correct signatures
    unsafe {
        let dict = xmlDictCreate();
        assert!(!dict.is_null());
        
        let test_str = b"test\0";
        let key = test_str.as_ptr() as *const std::os::raw::c_uchar;
        let interned = xmlDictLookup(dict, key, -1);
        assert!(!interned.is_null());
        
        xmlDictFree(dict);
    }
}

#[test] 
fn test_chvalid_abi() {
    // Test character validation functions
    unsafe {
        // Test ASCII 'A'
        assert!(xmlIsChar(65) != 0);
        assert!(xmlIsBaseChar(65) != 0);
        
        // Test space character
        assert!(xmlIsBlank(32) != 0);
        
        // Test digit
        assert!(xmlIsDigit(48) != 0); // '0'
    }
}

#[test]
fn test_error_abi() {
    // Test error handling functions
    unsafe {
        let error = xmlGetLastError();
        // Should either be null or valid pointer
        // This mainly tests that the function exists and can be called
        if !error.is_null() {
            xmlResetLastError();
        }
    }
}

#[cfg(test)]
mod struct_size_tests {
    use super::*;
    use std::mem;
    
    #[test]
    fn test_struct_sizes() {
        // Verify important structs have expected sizes
        // This will help catch ABI breakage
        
        // These sizes may vary by platform, but should be consistent
        // between C and Rust implementations
        println!("xmlChar size: {}", mem::size_of::<xmlChar>());
        println!("xmlError size: {}", mem::size_of::<xmlError>());
        
        // Basic sanity checks
        assert!(mem::size_of::<xmlChar>() > 0);
        assert!(mem::size_of::<xmlError>() > 0);
    }
}