//! Tests for dict module

use libxml2::*;

#[cfg(feature = "rust-dict")]
mod rust_tests {
    use super::*;
    
    #[test]
    fn test_dict_rust_implementation() {
        // When rust-dict feature is enabled, test Rust implementation
        unsafe {
            let dict = xmlDictCreate();
            assert!(!dict.is_null());
            
            let test_str = b"test_key\0";
            let key = test_str.as_ptr() as *const std::os::raw::c_uchar;
            
            let interned1 = xmlDictLookup(dict, key, -1);
            assert!(!interned1.is_null());
            
            let interned2 = xmlDictLookup(dict, key, -1);
            assert_eq!(interned1, interned2); // Should be same pointer
            
            let exists = xmlDictExists(dict, key, -1);
            assert!(!exists.is_null());
            
            let owns = xmlDictOwns(dict, interned1);
            assert!(owns != 0);
            
            let size = xmlDictSize(dict);
            assert!(size > 0);
            
            xmlDictFree(dict);
        }
    }
}

#[cfg(not(feature = "rust-dict"))]
mod c_tests {
    use super::*;
    
    #[test] 
    fn test_dict_c_implementation() {
        // When rust-dict feature is disabled, test C implementation
        unsafe {
            let dict = xmlDictCreate();
            assert!(!dict.is_null());
            
            let test_str = b"test_key\0";
            let key = test_str.as_ptr() as *const std::os::raw::c_uchar;
            
            let interned1 = xmlDictLookup(dict, key, -1);
            assert!(!interned1.is_null());
            
            let interned2 = xmlDictLookup(dict, key, -1);
            assert_eq!(interned1, interned2); // Should be same pointer
            
            xmlDictFree(dict);
        }
    }
}

#[test]
fn test_dict_sub_dictionaries() {
    // Test sub-dictionary functionality
    unsafe {
        let parent_dict = xmlDictCreate();
        assert!(!parent_dict.is_null());
        
        let sub_dict = xmlDictCreateSub(parent_dict);
        assert!(!sub_dict.is_null());
        
        xmlDictFree(sub_dict);
        xmlDictFree(parent_dict);
    }
}

#[test]
fn test_dict_qname_lookup() {
    // Test qualified name lookup
    unsafe {
        let dict = xmlDictCreate();
        assert!(!dict.is_null());
        
        let prefix = b"ns\0";
        let local = b"element\0";
        
        let qname = xmlDictQLookup(
            dict, 
            prefix.as_ptr() as *const std::os::raw::c_uchar,
            local.as_ptr() as *const std::os::raw::c_uchar
        );
        assert!(!qname.is_null());
        
        xmlDictFree(dict);
    }
}