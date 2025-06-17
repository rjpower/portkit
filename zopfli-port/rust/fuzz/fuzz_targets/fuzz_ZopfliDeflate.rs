#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::{c_int, c_uchar};
use std::ptr;
use zopfli::ffi;
use zopfli::deflate;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    data: Vec<u8>,
    btype: u8,
    final_flag: bool,
}

fuzz_target!(|input: FuzzInput| {
    let mut input = input;
    
    // btype must be 0, 1 or 2
    input.btype %= 3;
    
    if input.data.is_empty() {
        return;
    }

    let insize = input.data.len();
    let final_flag = if input.final_flag { 1 } else { 0 };
    
    unsafe {
        let options = ffi::ZopfliOptions {
            verbose: 0,
            verbose_more: 0,
            numiterations: 1, // Keep small for fuzzing performance
            blocksplitting: 1,
            blocksplittinglast: 0,
            blocksplittingmax: 3, // Keep small for fuzzing performance
        };

        // Setup for C function
        let mut c_out: *mut c_uchar = ptr::null_mut();
        let mut c_outsize: usize = 0;
        let mut c_bp: c_uchar = 0;
        
        // Setup for Rust function
        let mut rust_out: *mut c_uchar = ptr::null_mut();
        let mut rust_outsize: usize = 0;
        let mut rust_bp: c_uchar = 0;
        
        // Call C function
        ffi::ZopfliDeflate(
            &options,
            input.btype as c_int,
            final_flag,
            input.data.as_ptr(),
            insize,
            &mut c_bp,
            &mut c_out,
            &mut c_outsize,
        );
        
        // Call Rust function
        deflate::ZopfliDeflate(
            &options,
            input.btype as c_int,
            final_flag,
            input.data.as_ptr(),
            insize,
            &mut rust_bp,
            &mut rust_out,
            &mut rust_outsize,
        );
        
        // Compare results
        if c_bp != rust_bp {
            eprintln!("Bit position mismatch: C={}, Rust={}", c_bp, rust_bp);
            eprintln!("Input data: {:?}", &input.data[..input.data.len().min(20)]);
            eprintln!("btype={}, final={}, insize={}", input.btype as i32, final_flag, insize);
        }
        if c_outsize != rust_outsize {
            eprintln!("Output size mismatch: C={}, Rust={}", c_outsize, rust_outsize);
        }
        if c_outsize > 0 && rust_outsize > 0 && c_outsize == rust_outsize {
            let c_result = std::slice::from_raw_parts(c_out, c_outsize);
            let rust_result = std::slice::from_raw_parts(rust_out, rust_outsize);
            if c_result != rust_result {
                eprintln!("Output data mismatch");
                eprintln!("C:    {:?}", &c_result[..c_result.len().min(10)]);
                eprintln!("Rust: {:?}", &rust_result[..rust_result.len().min(10)]);
            }
        }
        
        assert_eq!(c_bp, rust_bp, "Bit positions don't match");
        assert_eq!(c_outsize, rust_outsize, "Output sizes don't match");
        
        if c_outsize > 0 {
            let c_result = std::slice::from_raw_parts(c_out, c_outsize);
            let rust_result = std::slice::from_raw_parts(rust_out, rust_outsize);
            assert_eq!(c_result, rust_result, "Output data doesn't match");
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