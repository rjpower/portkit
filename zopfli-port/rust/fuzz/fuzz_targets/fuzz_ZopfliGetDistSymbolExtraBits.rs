#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_int;

fuzz_target!(|data: &[u8]| {
    if data.is_empty() {
        return;
    }

    // The distance symbol 's' in DEFLATE is in the range 0-29.
    // The C function uses a static table of 30 elements.
    let s = data[0] as c_int % 30;

    // Call C implementation
    let c_result = unsafe { zopfli::ffi::ZopfliGetDistSymbolExtraBits(s) };

    // Call Rust implementation
    let rust_result = zopfli::symbols::ZopfliGetDistSymbolExtraBits(s);

    // Compare results
    assert_eq!(
        c_result, rust_result,
        "Mismatch for s = {}: C = {}, Rust = {}",
        s, c_result, rust_result
    );
});
