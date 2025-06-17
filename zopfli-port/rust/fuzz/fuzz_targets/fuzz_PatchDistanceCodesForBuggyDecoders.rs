#![no_main]

use arbitrary::Arbitrary;
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_uint;
use zopfli::deflate;
use zopfli::ffi;

#[derive(Debug, Arbitrary)]
struct FuzzInput {
    d_lengths: [c_uint; 32],
}

fuzz_target!(|input: FuzzInput| {
    let mut c_d_lengths = input.d_lengths;
    let mut rust_d_lengths = input.d_lengths;

    unsafe {
        ffi::PatchDistanceCodesForBuggyDecoders(c_d_lengths.as_mut_ptr());
    }

    deflate::PatchDistanceCodesForBuggyDecoders(&mut rust_d_lengths);

    assert_eq!(
        c_d_lengths, rust_d_lengths,
        "Mismatch after PatchDistanceCodesForBuggyDecoders"
    );
});
