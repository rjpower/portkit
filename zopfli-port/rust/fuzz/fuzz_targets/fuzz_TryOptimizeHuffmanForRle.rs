
#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::{c_uint};
use libc::size_t;

use zopfli::ffi;
use zopfli::deflate;
use zopfli::ffi::{ZopfliLZ77Store, ZopfliCleanLZ77Store};
use zopfli::util::{ZOPFLI_NUM_LL, ZOPFLI_NUM_D};

use zopfli::lz77::ZopfliInitLZ77Store;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    data: Vec<u8>,
    lstart: u16,
    lend: u16,
    ll_counts: [size_t; ZOPFLI_NUM_LL],
    d_counts: [size_t; ZOPFLI_NUM_D],
    ll_lengths: [c_uint; ZOPFLI_NUM_LL],
    d_lengths: [c_uint; ZOPFLI_NUM_D],
}

fuzz_target!(|input: FuzzInput| {
    let mut lz77 = ZopfliLZ77Store::default();
    ZopfliInitLZ77Store(input.data.as_ptr(), &mut lz77);

    let lstart = input.lstart as size_t;
    let mut lend = input.lend as size_t;
    if lstart >= lz77.size {
        unsafe { ZopfliCleanLZ77Store(&mut lz77) };
        return;
    }
    if lend > lz77.size {
        lend = lz77.size;
    }
    if lstart >= lend {
        unsafe { ZopfliCleanLZ77Store(&mut lz77) };
        return;
    }
    
    let mut c_ll_lengths = input.ll_lengths;
    let mut c_d_lengths = input.d_lengths;
    let mut rust_ll_lengths = input.ll_lengths;
    let mut rust_d_lengths = input.d_lengths;

    let c_result = unsafe {
        ffi::TryOptimizeHuffmanForRle(
            &lz77,
            lstart,
            lend,
            input.ll_counts.as_ptr(),
            input.d_counts.as_ptr(),
            c_ll_lengths.as_mut_ptr(),
            c_d_lengths.as_mut_ptr(),
        )
    };
    let rust_result = unsafe {
        deflate::TryOptimizeHuffmanForRle(
            &lz77,
            lstart,
            lend,
            input.ll_counts.as_ptr(),
            input.d_counts.as_ptr(),
            rust_ll_lengths.as_mut_ptr(),
            rust_d_lengths.as_mut_ptr(),
        )
    };

    assert_eq!(c_result, rust_result, "Results differ");
    assert_eq!(c_ll_lengths, rust_ll_lengths, "ll_lengths differ");
    assert_eq!(c_d_lengths, rust_d_lengths, "d_lengths differ");

    unsafe {
        ZopfliCleanLZ77Store(&mut lz77);
    }
});
