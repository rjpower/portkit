
#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::{c_int, c_uint, c_uchar};
use zopfli::ffi;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    ll_lengths: [c_uint; 288],
    d_lengths: [c_uint; 32],
    use_16: bool,
    use_17: bool,
    use_18: bool,
}

fuzz_target!(|input: FuzzInput| {
    let use_16 = input.use_16 as c_int;
    let use_17 = input.use_17 as c_int;
    let use_18 = input.use_18 as c_int;

    let mut c_bp: c_uchar = 0;
    let mut c_out_ptr: *mut c_uchar = std::ptr::null_mut();
    let mut c_outsize: usize = 0;
    let mut c_ll_lengths = input.ll_lengths;
    let mut c_d_lengths = input.d_lengths;

    let c_result = unsafe {
        ffi::EncodeTree(
            c_ll_lengths.as_mut_ptr(),
            c_d_lengths.as_mut_ptr(),
            use_16,
            use_17,
            use_18,
            &mut c_bp,
            &mut c_out_ptr,
            &mut c_outsize,
        )
    };

    let mut rust_bp: c_uchar = 0;
    let mut rust_out_ptr: *mut c_uchar = std::ptr::null_mut();
    let mut rust_outsize: usize = 0;
    let mut rust_ll_lengths = input.ll_lengths;
    let mut rust_d_lengths = input.d_lengths;

    let rust_result = unsafe {
        zopfli::deflate::EncodeTree(
            rust_ll_lengths.as_mut_ptr(),
            rust_d_lengths.as_mut_ptr(),
            use_16,
            use_17,
            use_18,
            &mut rust_bp,
            &mut rust_out_ptr,
            &mut rust_outsize,
        )
    };
    
    if !c_out_ptr.is_null() {
        unsafe { libc::free(c_out_ptr as *mut libc::c_void) };
    }
    if !rust_out_ptr.is_null() {
        unsafe { libc::free(rust_out_ptr as *mut libc::c_void) };
    }

    assert_eq!(c_result, rust_result, "results are not equal");

    // Now test with output enabled
    let mut c_bp: c_uchar = 0;
    let mut c_out_ptr: *mut c_uchar = std::ptr::null_mut();
    let mut c_outsize: usize = 0;
    let mut c_ll_lengths = input.ll_lengths;
    let mut c_d_lengths = input.d_lengths;

    unsafe {
        ffi::EncodeTree(
            c_ll_lengths.as_mut_ptr(),
            c_d_lengths.as_mut_ptr(),
            use_16,
            use_17,
            use_18,
            &mut c_bp,
            &mut c_out_ptr,
            &mut c_outsize,
        );
    };

    let mut rust_bp: c_uchar = 0;
    let mut rust_out_ptr: *mut c_uchar = std::ptr::null_mut();
    let mut rust_outsize: usize = 0;
    let mut rust_ll_lengths = input.ll_lengths;
    let mut rust_d_lengths = input.d_lengths;

    unsafe {
        zopfli::deflate::EncodeTree(
            rust_ll_lengths.as_mut_ptr(),
            rust_d_lengths.as_mut_ptr(),
            use_16,
            use_17,
            use_18,
            &mut rust_bp,
            &mut rust_out_ptr,
            &mut rust_outsize,
        );
    };
    let rust_out_slice = unsafe { std::slice::from_raw_parts(rust_out_ptr, rust_outsize) };
    
    let c_out_slice = unsafe { std::slice::from_raw_parts(c_out_ptr, c_outsize) };

    assert_eq!(c_out_slice, rust_out_slice, "output slices are not equal");
    assert_eq!(c_bp, rust_bp, "bit pointers are not equal");

    if !c_out_ptr.is_null() {
        unsafe { libc::free(c_out_ptr as *mut libc::c_void) };
    }
    if !rust_out_ptr.is_null() {
        unsafe { libc::free(rust_out_ptr as *mut libc::c_void) };
    }
});
