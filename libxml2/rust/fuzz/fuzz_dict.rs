#![no_main]

use libfuzzer_sys::fuzz_target;
use libxml2::*;

fuzz_target!(|data: &[u8]| {
    if data.len() == 0 || data.len() > 256 {
        return;
    }
    
    // Create a dictionary and test basic operations
    unsafe {
        let dict = xmlDictCreate();
        if dict.is_null() {
            return;
        }
        
        // Create null-terminated string
        let mut c_str = Vec::with_capacity(data.len() + 1);
        c_str.extend_from_slice(data);
        c_str.push(0);
        
        // Test dictionary operations
        let key = c_str.as_ptr() as *const std::os::raw::c_char;
        let interned = xmlDictLookup(dict, key as *const std::os::raw::c_uchar, -1);
        
        if !interned.is_null() {
            let exists = xmlDictExists(dict, key as *const std::os::raw::c_uchar, -1);
            let _owns = xmlDictOwns(dict, interned);
        }
        
        xmlDictFree(dict);
    }
});