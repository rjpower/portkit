
#![no_main]
use libfuzzer_sys::fuzz_target;

extern crate zopfli;
use zopfli::ffi;
use zopfli::deflate;
use std::os::raw::c_int;
use std::mem::MaybeUninit;

use arbitrary::{Arbitrary, Unstructured};

#[derive(Debug, Arbitrary)]
struct FuzzInput {
    data: Vec<u8>,
    btype: u8,
    lstart: u16,
    lend: u16,
    use_realistic: bool,
}

fn test_realistic_case() {
    let input_data = vec![189u8, 189, 43, 189, 189, 77, 77, 77, 77, 0, 77, 189, 77, 77, 77, 77, 0, 77, 255, 189, 189, 255, 255, 255, 189, 121, 121, 121, 121, 121, 121, 121, 121, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 189, 189, 255, 189, 189, 189, 189, 121, 121, 121];
    
    let options = ffi::ZopfliOptions {
        verbose: 0,
        verbose_more: 0,
        numiterations: 1,
        blocksplitting: 1,
        blocksplittinglast: 0,
        blocksplittingmax: 3,
    };

    unsafe {
        // Create the LZ77 store using the actual algorithm
        let mut lz77: ffi::ZopfliLZ77Store = std::mem::zeroed();
        ffi::ZopfliInitLZ77Store(input_data.as_ptr(), &mut lz77);
        
        // Fill it with realistic data using the actual compression process
        let mut s: ffi::ZopfliBlockState = std::mem::zeroed();
        ffi::ZopfliInitBlockState(&options, 0, 54, 1, &mut s);
        ffi::ZopfliLZ77Optimal(&mut s, input_data.as_ptr(), 0, 54, options.numiterations, &mut lz77);
        
        if lz77.size > 0 {
            // Test all three block types
            for btype in 0..3 {
                let result_rust = deflate::ZopfliCalculateBlockSize(&lz77, 0, lz77.size, btype);
                let result_c = ffi::ZopfliCalculateBlockSize(&lz77, 0, lz77.size, btype);
                assert!((result_rust - result_c).abs() < 1e-9, 
                    "Realistic case btype: {}, rust: {}, c: {}", btype, result_rust, result_c);
            }
        }
        
        ffi::ZopfliCleanBlockState(&mut s);
        ffi::ZopfliCleanLZ77Store(&mut lz77);
    }
}

fuzz_target!(|input: FuzzInput| {
    // First test the realistic case that was failing
    if input.use_realistic {
        test_realistic_case();
        return;
    }

    let mut lz77_c: zopfli::ffi::ZopfliLZ77Store = unsafe {
        let mut lz77_c_uninit = MaybeUninit::uninit();
        ffi::ZopfliInitLZ77Store(input.data.as_ptr(), lz77_c_uninit.as_mut_ptr());
        lz77_c_uninit.assume_init()
    };

    let mut pos = 0;
    for &byte in &input.data {
        let litlen = byte % 10; // Keep litlen small to avoid large allocations
        unsafe {
            ffi::ZopfliStoreLitLenDist(litlen as u16, 0, pos, &mut lz77_c);
        }
        pos += litlen as usize;
    }
    
    let lstart = input.lstart as usize;
    let lend = input.lend as usize;

    if lz77_c.size == 0 || lstart >= lz77_c.size as usize || lend >= lz77_c.size as usize || lstart >= lend {
        unsafe { ffi::ZopfliCleanLZ77Store(&mut lz77_c) };
        return;
    }

    let btype = (input.btype % 3) as c_int;

    let result_rust = unsafe { deflate::ZopfliCalculateBlockSize(&lz77_c, lstart, lend, btype) };
    let result_c = unsafe { ffi::ZopfliCalculateBlockSize(&lz77_c, lstart, lend, btype) };
    assert!((result_rust - result_c).abs() < 1e-9, "btype: {}, rust: {}, c: {}", btype, result_rust, result_c);

    unsafe { ffi::ZopfliCleanLZ77Store(&mut lz77_c) };
});
