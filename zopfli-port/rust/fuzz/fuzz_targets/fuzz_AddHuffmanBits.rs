#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::{c_uint, c_uchar, c_void};
use libc::size_t;
use zopfli::{ffi, deflate};

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    symbol: u32,
    length: u32,
    bp: u8,
    initial_out: Vec<u8>,
}

fuzz_target!(|input: FuzzInput| {
    // Constrain inputs
    let length = input.length % 33; // 0 to 32
    let mut c_bp = input.bp & 7; // 0 to 7
    let mut rust_bp = c_bp;

    let mut initial_out = input.initial_out;
    if initial_out.is_empty() {
        initial_out.push(0);
    }
    // C setup
    let mut c_outsize = initial_out.len();
    let mut c_out_ptr = if c_outsize > 0 {
        let buffer = unsafe { libc::malloc(c_outsize) as *mut u8 };
        unsafe { std::ptr::copy_nonoverlapping(initial_out.as_ptr(), buffer, c_outsize) };
        buffer
    } else {
        std::ptr::null_mut()
    };

    // Rust setup
    let mut rust_outsize = initial_out.len();
    let mut rust_out_ptr = if rust_outsize > 0 {
        let buffer = unsafe { libc::malloc(rust_outsize) as *mut u8 };
        unsafe { std::ptr::copy_nonoverlapping(initial_out.as_ptr(), buffer, rust_outsize) };
        buffer
    } else {
        std::ptr::null_mut()
    };

    // Call C function
    unsafe {
        ffi::AddHuffmanBits(
            input.symbol as c_uint,
            length as c_uint,
            &mut c_bp as *mut c_uchar,
            &mut c_out_ptr as *mut *mut c_uchar,
            &mut c_outsize as *mut size_t,
        );
    }

    // Call Rust function
    unsafe {
        deflate::AddHuffmanBits(
            input.symbol as c_uint,
            length as c_uint,
            &mut rust_bp as *mut c_uchar,
            &mut rust_out_ptr as *mut *mut c_uchar,
            &mut rust_outsize as *mut size_t,
        );
    }

    // Assertions
    assert_eq!(c_bp, rust_bp, "bp mismatch");
    assert_eq!(c_outsize, rust_outsize, "outsize mismatch");

    if c_outsize > 0 {
        let c_slice = unsafe { std::slice::from_raw_parts(c_out_ptr, c_outsize) };
        let rust_slice = unsafe { std::slice::from_raw_parts(rust_out_ptr, rust_outsize) };
        assert_eq!(c_slice, rust_slice, "out buffer mismatch");
    }

    // Cleanup
    unsafe {
        libc::free(c_out_ptr as *mut c_void);
        libc::free(rust_out_ptr as *mut c_void);
    }
});
