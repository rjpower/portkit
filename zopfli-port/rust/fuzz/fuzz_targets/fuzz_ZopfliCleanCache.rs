#![no_main]

use libfuzzer_sys::fuzz_target;
use std::mem::MaybeUninit;
use zopfli::ffi;

fuzz_target!(|data: &[u8]| {
    if data.is_empty() {
        return;
    }

    let blocksize = data[0] as usize;
    if blocksize == 0 {
        return;
    }

    let mut c_lmc = MaybeUninit::uninit();
    let mut rust_lmc = MaybeUninit::uninit();

    unsafe {
        ffi::ZopfliInitCache(blocksize, c_lmc.as_mut_ptr());
        zopfli::cache::ZopfliInitCache(blocksize, rust_lmc.as_mut_ptr());

        // The interesting part is what happens here. If the implementation is correct,
        // running under ASan should not report any memory leaks.
        ffi::ZopfliCleanCache(c_lmc.as_mut_ptr());
        zopfli::cache::ZopfliCleanCache(rust_lmc.as_mut_ptr());
    }
});
