#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_uchar;
use libc::size_t;
use std::ptr;
use arbitrary::Arbitrary;

use zopfli::ffi::ZopfliOptions;
use zopfli::zopfli_lib;

#[derive(Debug, Arbitrary)]
struct FuzzInput {
    data: Vec<u8>,
    
    #[arbitrary(with = |u: &mut arbitrary::Unstructured| u.int_in_range(0..=2))]
    format_type: u8,
    
    #[arbitrary(with = |u: &mut arbitrary::Unstructured| u.int_in_range(1..=100))]
    numiterations: u8,
    
    blocksplitting: bool,
    blocksplittinglast: bool,
    
    #[arbitrary(with = |u: &mut arbitrary::Unstructured| u.int_in_range(0..=15))]
    blocksplittingmax: u8,
}

fuzz_target!(|input: FuzzInput| {
    if input.data.is_empty() {
        return;
    }

    let format = match input.format_type {
        0 => zopfli::zopfli::ZopfliFormat::ZOPFLI_FORMAT_GZIP,
        1 => zopfli::zopfli::ZopfliFormat::ZOPFLI_FORMAT_ZLIB,
        2 => zopfli::zopfli::ZopfliFormat::ZOPFLI_FORMAT_DEFLATE,
        _ => unreachable!(),
    };

    let c_format = input.format_type as u32;

    let options = ZopfliOptions {
        verbose: 0,
        verbose_more: 0,
        numiterations: input.numiterations as i32,
        blocksplitting: input.blocksplitting as i32,
        blocksplittinglast: input.blocksplittinglast as i32,
        blocksplittingmax: input.blocksplittingmax as i32,
    };

    let mut c_out: *mut c_uchar = ptr::null_mut();
    let mut c_outsize: size_t = 0;

    unsafe {
        zopfli::ffi::ZopfliCompress(
            &options,
            c_format,
            input.data.as_ptr(),
            input.data.len(),
            &mut c_out,
            &mut c_outsize,
        );
    }

    let mut rust_out = Vec::new();
    zopfli_lib::ZopfliCompress(&options, format, &input.data, &mut rust_out);

    let c_result = if c_out.is_null() {
        Vec::new()
    } else {
        unsafe {
            let result = std::slice::from_raw_parts(c_out, c_outsize).to_vec();
            libc::free(c_out as *mut libc::c_void);
            result
        }
    };

    assert_eq!(
        c_result.len(),
        rust_out.len(),
        "Output sizes differ: C={}, Rust={}",
        c_result.len(),
        rust_out.len()
    );

    if !c_result.is_empty() {
        assert_eq!(
            c_result, rust_out,
            "Outputs differ for format {:?} with input length {}",
            format, input.data.len()
        );
    }
});