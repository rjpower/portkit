#![no_main]
use libfuzzer_sys::{fuzz_target, arbitrary::{self, Unstructured}};

use std::mem::MaybeUninit;
use zopfli::ffi;
use zopfli::lz77;
use zopfli::util::ZOPFLI_CACHE_LENGTH;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    #[arbitrary(with = |u: &mut Unstructured| u.int_in_range(0..=1024))]
    blockstart: u16,
    #[arbitrary(with = |u: &mut Unstructured| u.int_in_range(0..=1024))]
    blockend: u16,
    add_lmc: bool,
}

fuzz_target!(|input: FuzzInput| {
    let mut options: ffi::ZopfliOptions = unsafe { MaybeUninit::zeroed().assume_init() };
    unsafe { ffi::ZopfliInitOptions(&mut options) };

    let add_lmc = if input.add_lmc { 1 } else { 0 };

    let mut c_state: ffi::ZopfliBlockState = unsafe { MaybeUninit::zeroed().assume_init() };
    let mut rust_state: ffi::ZopfliBlockState = unsafe { MaybeUninit::zeroed().assume_init() };

    let (blockstart, blockend) = if input.blockstart <= input.blockend {
        (input.blockstart as usize, input.blockend as usize)
    } else {
        (input.blockend as usize, input.blockstart as usize)
    };
    
    unsafe {
        ffi::ZopfliInitBlockState(&options, blockstart, blockend, add_lmc, &mut c_state);
        lz77::ZopfliInitBlockState(&options, blockstart, blockend, add_lmc, &mut rust_state);
    }
    
    assert_eq!(c_state.blockstart, rust_state.blockstart);
    assert_eq!(c_state.blockend, rust_state.blockend);
    assert_eq!(c_state.options, rust_state.options);

    assert_eq!(!c_state.lmc.is_null(), !rust_state.lmc.is_null());

    if !c_state.lmc.is_null() {
        let cache_size = blockend - blockstart;
        let c_lmc = unsafe { &*c_state.lmc };
        let rust_lmc = unsafe { &*rust_state.lmc };

        let c_length = unsafe { std::slice::from_raw_parts(c_lmc.length, cache_size) };
        let rust_length = unsafe { std::slice::from_raw_parts(rust_lmc.length, cache_size) };
        assert_eq!(c_length, rust_length);

        let c_dist = unsafe { std::slice::from_raw_parts(c_lmc.dist, cache_size) };
        let rust_dist = unsafe { std::slice::from_raw_parts(rust_lmc.dist, cache_size) };
        assert_eq!(c_dist, rust_dist);

        // sublen is only allocated if ZOPFLI_CACHE_LENGTH is defined
        if !c_lmc.sublen.is_null() {
            assert!(!rust_lmc.sublen.is_null());
            let sublen_size = cache_size * ZOPFLI_CACHE_LENGTH as usize;
            let c_sublen = unsafe { std::slice::from_raw_parts(c_lmc.sublen, sublen_size) };
            let rust_sublen = unsafe { std::slice::from_raw_parts(rust_lmc.sublen, sublen_size) };
            assert_eq!(c_sublen, rust_sublen);
        } else {
            assert!(rust_lmc.sublen.is_null());
        }
    }


    unsafe {
        ffi::ZopfliCleanBlockState(&mut c_state);
        lz77::ZopfliCleanBlockState(&mut rust_state);
    }
});
