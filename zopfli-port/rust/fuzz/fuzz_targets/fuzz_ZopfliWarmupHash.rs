#![no_main]
use libfuzzer_sys::fuzz_target;
use std::mem::MaybeUninit;
use zopfli::{ffi, hash};

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    data: Vec<u8>,
}

const WINDOW_SIZE: usize = 32768;

fuzz_target!(|input: FuzzInput| {
    let data = input.data;
    if data.len() < 2 {
        return;
    }

    let mut c_hash = MaybeUninit::uninit();
    let mut rust_hash = MaybeUninit::uninit();

    unsafe {
        ffi::ZopfliAllocHash(WINDOW_SIZE, c_hash.as_mut_ptr());
        ffi::ZopfliResetHash(WINDOW_SIZE, c_hash.as_mut_ptr());

        ffi::ZopfliAllocHash(WINDOW_SIZE, rust_hash.as_mut_ptr());
        ffi::ZopfliResetHash(WINDOW_SIZE, rust_hash.as_mut_ptr());

        let mut c_hash = c_hash.assume_init();
        let mut rust_hash = rust_hash.assume_init();

        ffi::ZopfliWarmupHash(data.as_ptr(), 0, data.len(), &mut c_hash);
        hash::ZopfliWarmupHash(data.as_ptr(), 0, data.len(), &mut rust_hash);

        // We can't compare the pointers, so we'll just compare the `val` field.
        assert_eq!(c_hash.val, rust_hash.val);

        ffi::ZopfliCleanHash(&mut c_hash);
        ffi::ZopfliCleanHash(&mut rust_hash);
    }
});
