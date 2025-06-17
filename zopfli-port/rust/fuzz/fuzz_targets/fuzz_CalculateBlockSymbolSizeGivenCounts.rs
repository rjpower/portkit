#![no_main]
use libfuzzer_sys::fuzz_target;

use zopfli::ffi;
use zopfli::util::{ZOPFLI_NUM_D, ZOPFLI_NUM_LL};
use std::mem::MaybeUninit;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    ll_counts: [usize; ZOPFLI_NUM_LL],
    d_counts: [usize; ZOPFLI_NUM_D],
    ll_lengths: [u32; ZOPFLI_NUM_LL],
    d_lengths: [u32; ZOPFLI_NUM_D],
    data: Vec<u8>,
    lstart: usize,
    lend: usize,
}

fuzz_target!(|input: FuzzInput| {
    let mut lz77 = MaybeUninit::<ffi::ZopfliLZ77Store>::uninit();
    unsafe {
        ffi::ZopfliInitLZ77Store(input.data.as_ptr(), lz77.as_mut_ptr());
    }
    let mut lz77 = unsafe { lz77.assume_init() };

    // The C code doesn't check for this, but it will read out of bounds.
    let lend = input.lend % (input.data.len() + 1);
    let lstart = input.lstart % (lend + 1);

    lz77.size = input.data.len() as libc::size_t;

    let c_result = unsafe {
        ffi::CalculateBlockSymbolSizeGivenCounts(
            input.ll_counts.as_ptr(),
            input.d_counts.as_ptr(),
            input.ll_lengths.as_ptr(),
            input.d_lengths.as_ptr(),
            &lz77,
            lstart,
            lend,
        )
    };

    let rust_result = unsafe {
        zopfli::deflate::CalculateBlockSymbolSizeGivenCounts(
            input.ll_counts.as_ptr(),
            input.d_counts.as_ptr(),
            input.ll_lengths.as_ptr(),
            input.d_lengths.as_ptr(),
            &mut lz77,
            lstart,
            lend,
        )
    };

    assert_eq!(c_result, rust_result);

    unsafe {
        ffi::ZopfliCleanLZ77Store(&mut lz77);
    }
});
