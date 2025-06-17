#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_int;

fuzz_target!(|data: &[u8]| {
    if data.len() < std::mem::size_of::<c_int>() {
        return;
    }

    let dist = c_int::from_ne_bytes(data[0..std::mem::size_of::<c_int>()].try_into().unwrap());

    // The valid range for dist in DEFLATE is 1 to 32768.
    // The C function has specific checks for values < 5, so we should ensure
    // a good mix of values are tested. The raw integer from the fuzzer
    // will cover a wide range of inputs, including negative and large values,
    // testing the robustness of both implementations.

    let c_result = unsafe { zopfli::ffi::ZopfliGetDistExtraBits(dist) };
    let rust_result = zopfli::symbols::ZopfliGetDistExtraBits(dist);

    assert_eq!(
        c_result, rust_result,
        "ZopfliGetDistExtraBits mismatch for dist={}: C={}, Rust={}",
        dist, c_result, rust_result
    );
});
