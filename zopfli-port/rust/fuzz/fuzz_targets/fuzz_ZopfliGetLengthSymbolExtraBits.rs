#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_int;

fuzz_target!(|data: &[u8]| {
    if data.is_empty() {
        return;
    }

    // The length symbol s should be in the range [257, 285].
    // This gives 29 possible values.
    let s = 257 as c_int + (data[0] % 29) as c_int;

    let c_result = unsafe { zopfli::ffi::ZopfliGetLengthSymbolExtraBits(s) };
    let rust_result = zopfli::symbols::ZopfliGetLengthSymbolExtraBits(s as i32);

    assert_eq!(
        c_result, rust_result,
        "Mismatch for symbol {}: C={}, Rust={}",
        s, c_result, rust_result
    );
});
