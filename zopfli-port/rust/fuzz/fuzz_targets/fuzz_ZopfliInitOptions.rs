#![no_main]
use libfuzzer_sys::fuzz_target;

use zopfli::ffi;
use zopfli::util;

fuzz_target!(|_data: &[u8]| {
    let mut c_options = ffi::ZopfliOptions {
        verbose: 0,
        verbose_more: 0,
        numiterations: 0,
        blocksplitting: 0,
        blocksplittinglast: 0,
        blocksplittingmax: 0,
    };
    let mut rust_options = c_options;

    unsafe {
        ffi::ZopfliInitOptions(&mut c_options);
        util::ZopfliInitOptions(&mut rust_options);
    }

    assert_eq!(c_options, rust_options);
});