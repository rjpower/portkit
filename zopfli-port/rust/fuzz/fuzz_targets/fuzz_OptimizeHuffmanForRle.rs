#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_int;
use libc::size_t;
use zopfli::ffi;
use zopfli::deflate;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    length: u8,
    counts: Vec<size_t>,
}

fuzz_target!(|input: FuzzInput| {
    let mut length = input.length as c_int;
    let mut c_counts = input.counts.clone();

    if length as usize > c_counts.len() {
        length = c_counts.len() as c_int;
    }

    if length == 0 && c_counts.is_empty() {
        // Avoid creating 0-sized slices, which is UB.
        return;
    }

    let mut rust_counts = c_counts.clone();

    unsafe {
        ffi::OptimizeHuffmanForRle(length, c_counts.as_mut_ptr());
        deflate::OptimizeHuffmanForRle(length, rust_counts.as_mut_ptr());
    }

    if length > 0 {
        let l = length as usize;
        assert_eq!(&c_counts[..l], &rust_counts[..l]);
    }
});
