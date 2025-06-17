#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_int;

fuzz_target!(|data: &[u8]| {
    if data.is_empty() {
        return;
    }

    // The C function ZopfliGetLengthExtraBits uses its input `l` to index into a
    // 259-element array. Therefore, valid values for `l` are in the range [0, 258].
    // We generate a value within this range to avoid out-of-bounds access.
    let l = (data[0] as usize % 259) as c_int;

    // Call the C implementation via FFI
    let c_result = unsafe { zopfli::ffi::ZopfliGetLengthExtraBits(l) };

    // Call the Rust implementation
    let rust_result = zopfli::symbols::ZopfliGetLengthExtraBits(l);

    // Compare the results
    assert_eq!(
        c_result, rust_result,
        "Mismatch for l = {}: C returned {}, Rust returned {}",
        l, c_result, rust_result
    );
});
