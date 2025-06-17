#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_int;

use zopfli::ffi;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    data: Vec<u8>,
    num_iterations: u8, // Keep it small to avoid timeouts
}

fuzz_target!(|input: FuzzInput| {
    let mut options = zopfli::ffi::ZopfliOptions::default();
    unsafe {
        ffi::ZopfliInitOptions(&mut options);
    }
    options.numiterations = input.num_iterations as c_int;

    let mut c_s = ffi::ZopfliBlockState {
        options: &options,
        lmc: std::ptr::null_mut(),
        blockstart: 0,
        blockend: input.data.len(),
    };
    let mut rust_s = ffi::ZopfliBlockState {
        options: &options,
        lmc: std::ptr::null_mut(),
        blockstart: 0,
        blockend: input.data.len(),
    };

    let mut c_store = ffi::ZopfliLZ77Store::default();
    let mut rust_store = ffi::ZopfliLZ77Store::default();

    unsafe {
        ffi::ZopfliInitLZ77Store(input.data.as_ptr(), &mut c_store);
        ffi::ZopfliInitLZ77Store(input.data.as_ptr(), &mut rust_store);

        ffi::ZopfliLZ77Optimal(
            &mut c_s,
            input.data.as_ptr(),
            0,
            input.data.len(),
            options.numiterations,
            &mut c_store,
        );
        zopfli::squeeze::ZopfliLZ77Optimal(
            &mut rust_s,
            input.data.as_ptr(),
            0,
            input.data.len(),
            options.numiterations,
            &mut rust_store,
        );
    }

    if input.data.is_empty() {
        assert_eq!(c_store.size, 0);
        assert_eq!(rust_store.size, 0);
    } else {
        assert_eq!(c_store.size, rust_store.size);
        if c_store.size > 0 {
            let c_litlens = unsafe { std::slice::from_raw_parts(c_store.litlens, c_store.size) };
            let rust_litlens = unsafe { std::slice::from_raw_parts(rust_store.litlens, rust_store.size) };
            assert_eq!(c_litlens, rust_litlens);

            let c_dists = unsafe { std::slice::from_raw_parts(c_store.dists, c_store.size) };
            let rust_dists = unsafe { std::slice::from_raw_parts(rust_store.dists, rust_store.size) };
            assert_eq!(c_dists, rust_dists);
        }
    }

    unsafe {
        ffi::ZopfliCleanLZ77Store(&mut c_store);
        zopfli::lz77::ZopfliCleanLZ77Store(&mut rust_store);
    }
});
