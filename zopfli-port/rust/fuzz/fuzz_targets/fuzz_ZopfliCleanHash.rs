#![no_main]
use libfuzzer_sys::fuzz_target;
use zopfli::ffi;
use zopfli::hash;
use libc::malloc;
use std::mem;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    window_size: u16,
}

fuzz_target!(|input: FuzzInput| {
    let window_size = input.window_size as usize;
    if window_size == 0 {
        return;
    }

    unsafe {
        let h_ptr = malloc(mem::size_of::<ffi::ZopfliHash>()) as *mut ffi::ZopfliHash;
        if h_ptr.is_null() {
            return;
        }
        let h = &mut *h_ptr;

        hash::ZopfliAllocHash(window_size, h);
        // This test only checks that ZopfliCleanHash does not crash.
        hash::ZopfliCleanHash(h);

        // We can't really assert anything here, because after cleaning, the memory is freed.
        // The fuzz test's goal is to not crash.
        // We also can't call the C version because that would be a double free.
        
        // Free the ZopfliHash struct itself
        libc::free(h_ptr as *mut libc::c_void);
    }
});
