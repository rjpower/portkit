#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_int;
use zopfli::ffi;
use zopfli::lz77;
use arbitrary::{Arbitrary, Unstructured};

#[derive(Debug, Clone)]
pub struct FuzzInput {
    pub in_data: Vec<u8>,
    pub instart: usize,
    pub inend: usize,
    pub add_lmc: c_int,
}

impl<'a> Arbitrary<'a> for FuzzInput {
    fn arbitrary(u: &mut Unstructured<'a>) -> arbitrary::Result<Self> {
        let in_data: Vec<u8> = u.arbitrary()?;
        let instart = if in_data.is_empty() { 0 } else { u.int_in_range(0..=in_data.len() - 1)? };
        let inend = if in_data.is_empty() || instart >= in_data.len() {
             instart
        } else {
             u.int_in_range(instart..=in_data.len() - 1)?
        };

        let add_lmc = u.int_in_range(0..=1)?;

        Ok(FuzzInput {
            in_data,
            instart,
            inend,
            add_lmc,
        })
    }
}

unsafe fn run_test(input: &FuzzInput) {
    let mut c_s: ffi::ZopfliBlockState = std::mem::zeroed();
    let mut rust_s: ffi::ZopfliBlockState = std::mem::zeroed();
    let c_options: ffi::ZopfliOptions = Default::default();
    let rust_options: ffi::ZopfliOptions = Default::default();

    let blockstart = input.instart;
    let blockend = input.inend;

    ffi::ZopfliInitBlockState(&c_options, blockstart, blockend, input.add_lmc, &mut c_s);
    lz77::ZopfliInitBlockState(&rust_options, blockstart, blockend, input.add_lmc, &mut rust_s);

    let mut c_store: ffi::ZopfliLZ77Store = std::mem::zeroed();
    let mut rust_store: ffi::ZopfliLZ77Store = std::mem::zeroed();

    let in_ptr = input.in_data.as_ptr();

    lz77::ZopfliInitLZ77Store(in_ptr, &mut c_store);
    lz77::ZopfliInitLZ77Store(in_ptr, &mut rust_store);

    let mut c_h: ffi::ZopfliHash = std::mem::zeroed();
    let mut rust_h: ffi::ZopfliHash = std::mem::zeroed();

    ffi::ZopfliAllocHash(zopfli::util::ZOPFLI_WINDOW_SIZE, &mut c_h);
    ffi::ZopfliAllocHash(zopfli::util::ZOPFLI_WINDOW_SIZE, &mut rust_h);

    ffi::ZopfliLZ77Greedy(&mut c_s, in_ptr, input.instart, input.inend, &mut c_store, &mut c_h);
    lz77::ZopfliLZ77Greedy(&mut rust_s, in_ptr, input.instart, input.inend, &mut rust_store, &mut rust_h);

    assert_eq!(c_store.size, rust_store.size, "lz77 store size mismatch");

    if c_store.size > 0 {
        let c_litlens = std::slice::from_raw_parts(c_store.litlens, c_store.size);
        let rust_litlens = std::slice::from_raw_parts(rust_store.litlens, rust_store.size);
        assert_eq!(c_litlens, rust_litlens, "litlens mismatch");

        let c_dists = std::slice::from_raw_parts(c_store.dists, c_store.size);
        let rust_dists = std::slice::from_raw_parts(rust_store.dists, rust_store.size);
        assert_eq!(c_dists, rust_dists, "dists mismatch");

        let c_pos = std::slice::from_raw_parts(c_store.pos, c_store.size);
        let rust_pos = std::slice::from_raw_parts(rust_store.pos, rust_store.size);
        assert_eq!(c_pos, rust_pos, "pos mismatch");
    }

    ffi::ZopfliCleanHash(&mut c_h);
    ffi::ZopfliCleanHash(&mut rust_h);

    lz77::ZopfliCleanLZ77Store(&mut c_store);
    lz77::ZopfliCleanLZ77Store(&mut rust_store);
    
    lz77::ZopfliCleanBlockState(&mut c_s);
    lz77::ZopfliCleanBlockState(&mut rust_s);
}

fuzz_target!(|input: FuzzInput| {
    unsafe {
        run_test(&input);
    }
});
