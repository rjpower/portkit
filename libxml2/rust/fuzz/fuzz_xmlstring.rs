#![no_main]

use libfuzzer_sys::fuzz_target;
use libxml2::*;

fuzz_target!(|data: &[u8]| {
    // Convert input to null-terminated string for C compatibility
    if data.len() == 0 || data.len() > 1024 {
        return;
    }
    
    let mut c_str = Vec::with_capacity(data.len() + 1);
    c_str.extend_from_slice(data);
    c_str.push(0);
    
    unsafe {
        let xml_str = c_str.as_ptr() as *const std::os::raw::c_uchar;
        
        // Test key xmlstring functions
        let len = xmlStrlen(xml_str);
        if len > 0 && len < 1024 {
            let dup = xmlStrdup(xml_str);
            if !dup.is_null() {
                xmlFree(dup as *mut std::os::raw::c_void);
            }
        }
    }
});