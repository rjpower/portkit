#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_int;

fuzz_target!(|data: &[u8]| {
    if data.is_empty() {
        return;
    }

    // The function ZopfliGetLengthExtraBitsValue uses the input as an index
    // into a table of size 259. So the valid input range is [0, 258].
    // We'll use the first byte of the fuzzer data and constrain it to this range.
    let l = data[0] as c_int;
    if l > 258 {
        return;
    }

    // Call the C implementation via FFI
    let c_result = unsafe { zopfli::ffi::ZopfliGetLengthExtraBitsValue(l) };

    // Call the Rust implementation
    let rust_result = zopfli::symbols::ZopfliGetLengthExtraBitsValue(l);

    // Compare results
    assert_eq!(
        c_result, rust_result,
        "Return values differ for l={}: C={}, Rust={}",
        l, c_result, rust_result
    );
});
