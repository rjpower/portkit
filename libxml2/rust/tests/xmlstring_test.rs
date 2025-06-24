//! Tests for xmlstring module

use libxml2::*;

#[cfg(feature = "rust-xmlstring")]
mod rust_tests {
    use super::*;
    
    #[test]
    fn test_xmlstring_rust_implementation() {
        // When rust-xmlstring feature is enabled, test Rust implementation
        unsafe {
            let test_str = b"hello\0";
            let xml_str = test_str.as_ptr() as *const std::os::raw::c_uchar;
            
            let len = xmlStrlen(xml_str);
            assert_eq!(len, 5);
            
            let dup = xmlStrdup(xml_str);
            assert!(!dup.is_null());
            
            let cmp = xmlStrcmp(xml_str, dup);
            assert_eq!(cmp, 0);
            
            xmlFree(dup as *mut std::os::raw::c_void);
        }
    }
    
    #[test]
    fn test_xmlstring_utf8() {
        // Test UTF-8 handling
        unsafe {
            let utf8_str = "hello🦀\0";
            let bytes = utf8_str.as_bytes();
            let xml_str = bytes.as_ptr() as *const std::os::raw::c_uchar;
            
            let utf8_len = xmlUTF8Strlen(xml_str);
            assert_eq!(utf8_len, 6); // 5 ASCII chars + 1 emoji
            
            let is_valid = xmlCheckUTF8(xml_str);
            assert!(is_valid != 0);
        }
    }
}

#[cfg(not(feature = "rust-xmlstring"))]
mod c_tests {
    use super::*;
    
    #[test]
    fn test_xmlstring_c_implementation() {
        // When rust-xmlstring feature is disabled, test C implementation
        unsafe {
            let test_str = b"hello\0";
            let xml_str = test_str.as_ptr() as *const std::os::raw::c_uchar;
            
            let len = xmlStrlen(xml_str);
            assert_eq!(len, 5);
            
            let dup = xmlStrdup(xml_str);
            assert!(!dup.is_null());
            
            let cmp = xmlStrcmp(xml_str, dup);
            assert_eq!(cmp, 0);
            
            xmlFree(dup as *mut std::os::raw::c_void);
        }
    }
}

#[test]
fn test_common_xmlstring_functionality() {
    // Tests that should pass regardless of implementation
    unsafe {
        let empty_str = b"\0";
        let xml_str = empty_str.as_ptr() as *const std::os::raw::c_uchar;
        let len = xmlStrlen(xml_str);
        assert_eq!(len, 0);
    }
}