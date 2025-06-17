#![no_main]
use libfuzzer_sys::fuzz_target;
use libc::size_t;
use zopfli::ffi;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    x: size_t,
    y: size_t,
}

fuzz_target!(|input: FuzzInput| {
    let c_result = unsafe { ffi::AbsDiff(input.x, input.y) };
    let rust_result = zopfli::deflate::AbsDiff(input.x, input.y);
    assert_eq!(c_result, rust_result);
});
