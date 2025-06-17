## Fuzzing Guidelines

Only write fuzz tests for functions.
Don't test inputs that are invalid for the C function, e.g. if an input expects a number between 0 and 30, don't test with 123123.

When appropriate, use the C FFI bindings to initialize data, e.g. use ffi::ZopfliInitLZ77Store to initialize a ZopfliLZ77Store,
instead of trying to manually initialize the data.

- Use libfuzzer_sys to generate random inputs
- Call C version first (via FFI) and then Rust version
- Compare outputs and assert they are identical
- Only test valid inputs for the C function.
- Use Arbitrary to generate inputs.

!!!! IMPORTANT !!!!
If the C function asserts on an input, remove that input from the fuzz tests. 
Don't try to fix the C function, or try to make the Rust function assert identically.
!!!! IMPORTANT !!!!

#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_ushort;

use zopfli::ffi;
use zopfli::lz77;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    data: Vec<u8>,

    // Constrain input to a valid range, don't test on invalid inputs
    #[arbitrary(with = |u: &mut Unstructured| u.int_in_range(0..=30))]
    start: u16,

    #[arbitrary(with = |u: &mut Unstructured| u.int_in_range(0..=30))]
    end: u16,
}

fuzz_target!(|input: FuzzInput| {
    let size = input.data.len();
    let mut c_input = zopfli::ffi::SomeStruct { a: input.start, b: input.end };
    let mut rust_input = zopfli::ffi::SomeStruct { a: input.start, b: input.end };

    let c_result = zopfli::ffi::SomeFunction(&c_input);
    let rust_result = zopfli::ffi::SomeFunction(&rust_input);

    assert_eq!(c_result, rust_result);
});