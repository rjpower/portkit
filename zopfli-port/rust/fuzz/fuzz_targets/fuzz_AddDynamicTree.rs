#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::{c_uchar, c_uint};
use zopfli::{
    deflate, ffi,
    util::{ZOPFLI_NUM_D, ZOPFLI_NUM_LL},
};

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    ll_lengths: Vec<u32>,
    d_lengths: Vec<u32>,
}

fuzz_target!(|input: FuzzInput| {
    let mut ll_lengths = input.ll_lengths;
    ll_lengths.resize(ZOPFLI_NUM_LL as usize, 0);
    for x in &mut ll_lengths {
        *x %= 16;
    }

    let mut d_lengths = input.d_lengths;
    d_lengths.resize(ZOPFLI_NUM_D as usize, 0);
    for x in &mut d_lengths {
        *x %= 16;
    }

    let mut c_bp = 0;
    let mut c_out: *mut c_uchar = std::ptr::null_mut();
    let mut c_outsize = 0;

    let mut rust_bp = 0;
    let mut rust_out: *mut c_uchar = std::ptr::null_mut();
    let mut rust_outsize = 0;

    unsafe {
        ffi::AddDynamicTree(
            ll_lengths.as_ptr() as *const c_uint,
            d_lengths.as_ptr() as *const c_uint,
            &mut c_bp,
            &mut c_out,
            &mut c_outsize,
        );

        deflate::AddDynamicTree(
            ll_lengths.as_ptr() as *const c_uint,
            d_lengths.as_ptr() as *const c_uint,
            &mut rust_bp,
            &mut rust_out,
            &mut rust_outsize,
        );

        assert_eq!(c_bp, rust_bp);
        assert_eq!(c_outsize, rust_outsize);
        if !c_out.is_null() && !rust_out.is_null() {
            let c_slice = std::slice::from_raw_parts(c_out, c_outsize);
            let rust_slice = std::slice::from_raw_parts(rust_out, rust_outsize);
            assert_eq!(c_slice, rust_slice);
        }

        libc::free(c_out as *mut _);
        libc::free(rust_out as *mut _);
    }
});
