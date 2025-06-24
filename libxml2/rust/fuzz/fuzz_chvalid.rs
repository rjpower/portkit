#![no_main]

use libfuzzer_sys::fuzz_target;
use libxml2::*;

fuzz_target!(|data: &[u8]| {
    if data.len() < 4 {
        return;
    }
    
    // Extract a unicode codepoint from the input
    let codepoint = u32::from_le_bytes([
        data.get(0).copied().unwrap_or(0),
        data.get(1).copied().unwrap_or(0),
        data.get(2).copied().unwrap_or(0),
        data.get(3).copied().unwrap_or(0),
    ]);
    
    // Test character validation functions
    unsafe {
        let _is_char = xmlIsChar(codepoint);
        let _is_blank = xmlIsBlank(codepoint);
        let _is_base_char = xmlIsBaseChar(codepoint);
        let _is_digit = xmlIsDigit(codepoint);
        let _is_combining = xmlIsCombining(codepoint);
        let _is_extender = xmlIsExtender(codepoint);
        let _is_ideographic = xmlIsIdeographic(codepoint);
        let _is_pubid_char = xmlIsPubidChar(codepoint);
    }
});