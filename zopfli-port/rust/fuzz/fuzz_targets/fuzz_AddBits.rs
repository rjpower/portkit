#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::{c_uchar, c_uint};

use zopfli::ffi;
use zopfli::deflate;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    symbol: c_uint,
    length: c_uint,
    bp: c_uchar,
    initial_out: Vec<u8>,
}

fuzz_target!(|input: FuzzInput| {
    let FuzzInput {
        symbol,
        mut length,
        mut bp,
        initial_out,
    } = input;

    length %= 32;
    bp %= 8;

    if initial_out.is_empty() && bp != 0 {
        // This is an invalid input for the C function, it will crash.
        return;
    }

    let mut c_outsize = initial_out.len();
    let c_capacity = c_outsize.next_power_of_two();
    let mut c_out_ptr = if c_outsize > 0 {
        let ptr = unsafe { libc::malloc(c_capacity) as *mut u8 };
        unsafe { std::ptr::copy_nonoverlapping(initial_out.as_ptr(), ptr, c_outsize) };
        ptr
    } else {
        std::ptr::null_mut()
    };

    let mut rust_outsize = initial_out.len();
    let rust_capacity = rust_outsize.next_power_of_two();
    let mut rust_out_ptr = if rust_outsize > 0 {
        let ptr = unsafe { libc::malloc(rust_capacity) as *mut u8 };
        unsafe { std::ptr::copy_nonoverlapping(initial_out.as_ptr(), ptr, rust_outsize) };
        ptr
    } else {
        std::ptr::null_mut()
    };

    let mut c_bp = bp;
    let mut rust_bp = bp;

    unsafe {
        ffi::AddBits(
            symbol,
            length,
            &mut c_bp,
            &mut c_out_ptr,
            &mut c_outsize,
        );
        let c_result = if c_out_ptr.is_null() {
            &[]
        } else {
            std::slice::from_raw_parts(c_out_ptr, c_outsize)
        };

        deflate::AddBits(
            symbol,
            length,
            &mut rust_bp,
            &mut rust_out_ptr,
            &mut rust_outsize,
        );
        let rust_result = if rust_out_ptr.is_null() {
            &[]
        } else {
            std::slice::from_raw_parts(rust_out_ptr, rust_outsize)
        };

        assert_eq!(c_bp, rust_bp);
        assert_eq!(c_outsize, rust_outsize);
        assert_eq!(c_result, rust_result);

        libc::free(c_out_ptr as *mut _);
        libc::free(rust_out_ptr as *mut _);
    }
});
