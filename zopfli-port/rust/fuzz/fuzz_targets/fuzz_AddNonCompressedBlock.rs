#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_uchar;
use libc::size_t;

use zopfli::ffi;
use zopfli::deflate;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    data: Vec<u8>,
    final_flag: bool,
    start_offset: u8,
    end_offset: u8,
}

fuzz_target!(|input: FuzzInput| {
    if input.data.is_empty() {
        return;
    }

    let data_len = input.data.len();
    let instart = (input.start_offset as usize) % data_len;
    let inend = std::cmp::max(instart, instart + (input.end_offset as usize) % (data_len - instart + 1));
    
    let final_flag = if input.final_flag { 1 } else { 0 };
    
    // Setup for C function
    let mut c_out: *mut c_uchar = std::ptr::null_mut();
    let mut c_outsize: size_t = 0;
    let mut c_bp: c_uchar = 0;
    let options = zopfli::ffi::ZopfliOptions::default();
    
    // Setup for Rust function
    let mut rust_out: *mut c_uchar = std::ptr::null_mut();
    let mut rust_outsize: size_t = 0;
    let mut rust_bp: c_uchar = 0;
    
    unsafe {
        // Call C function
        ffi::AddNonCompressedBlock(
            &options,
            final_flag,
            input.data.as_ptr(),
            instart,
            inend,
            &mut c_bp,
            &mut c_out,
            &mut c_outsize,
        );
        
        // Call Rust function
        deflate::AddNonCompressedBlock(
            &options,
            final_flag,
            input.data.as_ptr(),
            instart,
            inend,
            &mut rust_bp,
            &mut rust_out,
            &mut rust_outsize,
        );
        
        assert_eq!(c_bp, rust_bp);
        assert_eq!(c_outsize, rust_outsize);
        
        if c_outsize > 0 {
            let c_result = std::slice::from_raw_parts(c_out, c_outsize);
            let rust_result = std::slice::from_raw_parts(rust_out, rust_outsize);
            assert_eq!(c_result, rust_result);
        }
        
        // Clean up
        if !c_out.is_null() {
            libc::free(c_out as *mut libc::c_void);
        }
        if !rust_out.is_null() {
            libc::free(rust_out as *mut libc::c_void);
        }
    }
});