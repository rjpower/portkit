#![no_main]

use libfuzzer_sys::{fuzz_target, arbitrary::Arbitrary};
use zopfli::ffi;
use zopfli::util;
use zopfli::lz77;
use zopfli::deflate;

#[derive(Debug, Arbitrary)]
struct FuzzInput {
    data: Vec<u8>,
    lstart: u16,
    lend: u16,
}

fuzz_target!(|input: FuzzInput| {
    let in_size = input.data.len();
    if in_size == 0 {
        return;
    }

    unsafe {
        let options = ffi::ZopfliOptions {
            verbose: 0,
            verbose_more: 0,
            numiterations: 15,
            blocksplitting: 1,
            blocksplittinglast: 0,
            blocksplittingmax: 15,
        };

        let mut c_s = std::mem::MaybeUninit::<ffi::ZopfliBlockState>::uninit();
        ffi::ZopfliInitBlockState(&options, 0, in_size, 0, c_s.as_mut_ptr());
        let mut c_s = c_s.assume_init();

        let mut rust_s = std::mem::MaybeUninit::<ffi::ZopfliBlockState>::uninit();
        ffi::ZopfliInitBlockState(&options, 0, in_size, 0, rust_s.as_mut_ptr());
        let mut rust_s = rust_s.assume_init();

        let mut c_store = std::mem::MaybeUninit::<ffi::ZopfliLZ77Store>::uninit();
        ffi::ZopfliInitLZ77Store(input.data.as_ptr(), c_store.as_mut_ptr());
        let mut c_store = c_store.assume_init();

        let mut rust_store = std::mem::MaybeUninit::<ffi::ZopfliLZ77Store>::uninit();
        ffi::ZopfliInitLZ77Store(input.data.as_ptr(), rust_store.as_mut_ptr());
        let mut rust_store = rust_store.assume_init();

        let mut h = std::mem::MaybeUninit::<ffi::ZopfliHash>::uninit();
        ffi::ZopfliAllocHash(65536, h.as_mut_ptr());
        let mut h = h.assume_init();

        lz77::ZopfliLZ77Greedy(&mut c_s, input.data.as_ptr(), 0, in_size, &mut c_store, &mut h);
        lz77::ZopfliLZ77Greedy(&mut rust_s, input.data.as_ptr(), 0, in_size, &mut rust_store, &mut h);

        let store_size = c_store.size;
        if store_size == 0 {
            ffi::ZopfliCleanLZ77Store(&mut c_store);
            ffi::ZopfliCleanLZ77Store(&mut rust_store);
            ffi::ZopfliCleanHash(&mut h);
            ffi::ZopfliCleanBlockState(&mut c_s);
            ffi::ZopfliCleanBlockState(&mut rust_s);
            return;
        }

        let lstart = (input.lstart as usize) % store_size;
        let lend = (input.lend as usize) % store_size;
        if lstart > lend {
            ffi::ZopfliCleanLZ77Store(&mut c_store);
            ffi::ZopfliCleanLZ77Store(&mut rust_store);
            ffi::ZopfliCleanHash(&mut h);
            ffi::ZopfliCleanBlockState(&mut c_s);
            ffi::ZopfliCleanBlockState(&mut rust_s);
            return;
        }

        let mut c_ll_lengths = [0u32; util::ZOPFLI_NUM_LL];
        let mut c_d_lengths = [0u32; util::ZOPFLI_NUM_D];
        let mut rust_ll_lengths = [0u32; util::ZOPFLI_NUM_LL];
        let mut rust_d_lengths = [0u32; util::ZOPFLI_NUM_D];

        let c_result = ffi::GetDynamicLengths(
            &c_store,
            lstart,
            lend,
            c_ll_lengths.as_mut_ptr(),
            c_d_lengths.as_mut_ptr(),
        );
        let rust_result = deflate::GetDynamicLengths(
            &rust_store,
            lstart,
            lend,
            rust_ll_lengths.as_mut_ptr(),
            rust_d_lengths.as_mut_ptr(),
        );

        assert_eq!(c_ll_lengths, rust_ll_lengths, "ll_lengths mismatch");
        assert_eq!(c_d_lengths, rust_d_lengths, "d_lengths mismatch");
        assert!((c_result - rust_result).abs() < 1e-9, "result mismatch: c={} rust={}", c_result, rust_result);

        ffi::ZopfliCleanLZ77Store(&mut c_store);
        ffi::ZopfliCleanLZ77Store(&mut rust_store);
        ffi::ZopfliCleanHash(&mut h);
        ffi::ZopfliCleanBlockState(&mut c_s);
        ffi::ZopfliCleanBlockState(&mut rust_s);
    }
});