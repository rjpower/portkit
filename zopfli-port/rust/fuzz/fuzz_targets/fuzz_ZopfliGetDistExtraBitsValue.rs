#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_int;

fuzz_target!(|data: &[u8]| {
    if data.len() < 4 {
        return;
    }

    // Interpret the first 4 bytes of the input data as an integer for `dist`.
    // The C implementation has specific behavior for positive integers, especially
    // those up to 16385. Using a random i32 will cover a wide range of inputs.
    let dist = i32::from_ne_bytes(data[0..4].try_into().unwrap());

    // Call the C implementation via FFI
    let c_result = unsafe { zopfli::ffi::ZopfliGetDistExtraBitsValue(dist as c_int) };

    // Call the Rust implementation
    // Note: This is expected to panic until it's implemented.
    let rust_result = zopfli::symbols::ZopfliGetDistExtraBitsValue(dist as c_int);

    // Compare the results
    assert_eq!(
        c_result,
        rust_result,
        "Return values differ for dist={}: C={}, Rust={}",
        dist,
        c_result,
        rust_result
    );
});
