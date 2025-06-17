#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_int;

fuzz_target!(|data: &[u8]| {
    if data.len() < 4 {
        return;
    }

    // The C function is only defined for dist >= 1.
    // We get a positive integer from the fuzz data.
    let dist = u32::from_ne_bytes([data[0], data[1], data[2], data[3]]) as i32;
    if dist < 1 {
        return;
    }

    let c_dist = dist as c_int;
    let rust_dist = dist;

    let c_result = unsafe { zopfli::ffi::ZopfliGetDistSymbol(c_dist) };
    let rust_result = zopfli::symbols::ZopfliGetDistSymbol(rust_dist);

    assert_eq!(
        c_result, rust_result,
        "ZopfliGetDistSymbol({}, {}) returned {} (C) vs {} (Rust)",
        c_dist, rust_dist, c_result, rust_result
    );
});
