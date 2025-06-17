#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_int;

fuzz_target!(|data: &[u8]| {
    if data.is_empty() {
        return;
    }

    // The C function uses the input `l` to index into a table of size 259.
    // We constrain `l` to be within the valid range [0, 258] to avoid UB.
    let l = data[0] as c_int;
    if l < 0 || l > 258 {
        return;
    }

    let c_result = unsafe { zopfli::ffi::ZopfliGetLengthSymbol(l) };
    let rust_result = zopfli::symbols::ZopfliGetLengthSymbol(l);

    assert_eq!(c_result, rust_result, "ZopfliGetLengthSymbol mismatch at l={}", l);
});
