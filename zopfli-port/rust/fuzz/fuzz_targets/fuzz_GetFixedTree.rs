#![no_main]

use libfuzzer_sys::fuzz_target;
use std::os::raw::c_uint;
use zopfli::{deflate, ffi, util};

fuzz_target!(|_data: &[u8]| {
    const ZOPFLI_NUM_LL: usize = util::ZOPFLI_NUM_LL;
    const ZOPFLI_NUM_D: usize = util::ZOPFLI_NUM_D;

    let mut c_ll_lengths = [0u32; ZOPFLI_NUM_LL];
    let mut c_d_lengths = [0u32; ZOPFLI_NUM_D];
    let mut rust_ll_lengths = [0u32; ZOPFLI_NUM_LL];
    let mut rust_d_lengths = [0u32; ZOPFLI_NUM_D];

    unsafe {
        ffi::GetFixedTree(c_ll_lengths.as_mut_ptr(), c_d_lengths.as_mut_ptr());
        deflate::GetFixedTree(
            rust_ll_lengths.as_mut_ptr() as *mut c_uint,
            rust_d_lengths.as_mut_ptr() as *mut c_uint,
        );
    }

    assert_eq!(c_ll_lengths, rust_ll_lengths);
    assert_eq!(c_d_lengths, rust_d_lengths);
});
