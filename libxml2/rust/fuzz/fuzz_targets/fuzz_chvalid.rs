#![no_main]
use libfuzzer_sys::fuzz_target;
use arbitrary::{Arbitrary, Unstructured};
use libxml2::libxml2_dynload::get_c_baseline;
use libxml2::chvalid;

#[derive(Debug, Clone, Copy, Arbitrary)]
enum CharFunction {
    BaseChar,
    Blank,
    Char,
    Combining,
    Digit,
    Extender,
    Ideographic,
    PubidChar,
}

#[derive(Debug, Arbitrary)]
struct FuzzInput {
    #[arbitrary(with = |u: &mut Unstructured| u.int_in_range(0..=0x10FFFF))]
    char_code: u32,
    
    function: CharFunction,
}

fuzz_target!(|input: FuzzInput| {
    let c_lib = get_c_baseline();
    let ch = input.char_code;
    
    match input.function {
        CharFunction::BaseChar => {
            // C baseline (dynamically loaded pure C library)
            let c_result = unsafe { c_lib.xmlIsBaseChar(ch) };
            
            // Rust implementation
            let rust_result = chvalid::is_base_char(ch);
            
            assert_eq!(c_result != 0, rust_result,
                "BaseChar mismatch for 0x{:x}: C={}, Rust={}", ch, c_result, rust_result);
        },
        CharFunction::Blank => {
            let c_result = unsafe { c_lib.xmlIsBlank(ch) };
            let rust_result = chvalid::is_blank(ch);
            
            assert_eq!(c_result != 0, rust_result,
                "Blank mismatch for 0x{:x}: C={}, Rust={}", ch, c_result, rust_result);
        },
        CharFunction::Char => {
            let c_result = unsafe { c_lib.xmlIsChar(ch) };
            let rust_result = chvalid::is_char(ch);
            
            assert_eq!(c_result != 0, rust_result,
                "Char mismatch for 0x{:x}: C={}, Rust={}", ch, c_result, rust_result);
        },
        CharFunction::Combining => {
            let c_result = unsafe { c_lib.xmlIsCombining(ch) };
            let rust_result = chvalid::is_combining(ch);
            
            assert_eq!(c_result != 0, rust_result,
                "Combining mismatch for 0x{:x}: C={}, Rust={}", ch, c_result, rust_result);
        },
        CharFunction::Digit => {
            let c_result = unsafe { c_lib.xmlIsDigit(ch) };
            let rust_result = chvalid::is_digit(ch);
            
            assert_eq!(c_result != 0, rust_result,
                "Digit mismatch for 0x{:x}: C={}, Rust={}", ch, c_result, rust_result);
        },
        CharFunction::Extender => {
            let c_result = unsafe { c_lib.xmlIsExtender(ch) };
            let rust_result = chvalid::is_extender(ch);
            
            assert_eq!(c_result != 0, rust_result,
                "Extender mismatch for 0x{:x}: C={}, Rust={}", ch, c_result, rust_result);
        },
        CharFunction::Ideographic => {
            let c_result = unsafe { c_lib.xmlIsIdeographic(ch) };
            let rust_result = chvalid::is_ideographic(ch);
            
            assert_eq!(c_result != 0, rust_result,
                "Ideographic mismatch for 0x{:x}: C={}, Rust={}", ch, c_result, rust_result);
        },
        CharFunction::PubidChar => {
            let c_result = unsafe { c_lib.xmlIsPubidChar(ch) };
            let rust_result = chvalid::is_pubid_char(ch);
            
            assert_eq!(c_result != 0, rust_result,
                "PubidChar mismatch for 0x{:x}: C={}, Rust={}", ch, c_result, rust_result);
        },
    }
});