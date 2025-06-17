#![no_main]
use libfuzzer_sys::fuzz_target;
use std::mem::size_of;
use zopfli::ffi::{ZopfliBlockState, ZopfliLongestMatchCache, ZopfliOptions};

use arbitrary::Arbitrary;

#[derive(Debug, Arbitrary)]
struct FuzzInput {
    block_start: usize,
    block_end: usize,
    add_lmc: i32,
    options: FuzzZopfliOptions,
}

#[derive(Debug, Arbitrary)]
struct FuzzZopfliOptions {
    verbose: i32,
    verbose_more: i32,
    numiterations: i32,
    blocksplitting: i32,
    blocksplittinglast: i32,
    blocksplittingmax: i32,
}

impl FuzzZopfliOptions {
    fn to_zopfli_options(&self) -> ZopfliOptions {
        ZopfliOptions {
            verbose: self.verbose,
            verbose_more: self.verbose_more,
            numiterations: self.numiterations,
            blocksplitting: self.blocksplitting,
            blocksplittinglast: self.blocksplittinglast,
            blocksplittingmax: self.blocksplittingmax,
        }
    }
}

fuzz_target!(|input: FuzzInput| {
    // The fuzzer can generate very large values for block_end, which can cause
    // ZopfliInitCache to fail due to an attempted large allocation. We constrain
    // the values to be more reasonable.
    let block_start = input.block_start % 10000;
    let block_end = input.block_end % 10000;

    if block_end < block_start {
        return;
    }

    let mut fuzz_options = input.options;
    // numiterations can significantly slow down the fuzzer.
    fuzz_options.numiterations %= 16;
    if fuzz_options.numiterations == 0 {
        fuzz_options.numiterations = 1;
    }


    unsafe {
        let mut c_state: ZopfliBlockState = std::mem::zeroed();
        let mut rust_state: ZopfliBlockState = std::mem::zeroed();

        // To properly test ZopfliCleanBlockState, we need to initialize a block state
        // with a longest match cache, since that's what the function cleans up.
        let c_lmc = libc::malloc(size_of::<ZopfliLongestMatchCache>()) as *mut ZopfliLongestMatchCache;
        let rust_lmc = libc::malloc(size_of::<ZopfliLongestMatchCache>()) as *mut ZopfliLongestMatchCache;

        if c_lmc.is_null() || rust_lmc.is_null() {
            if !c_lmc.is_null() {
                libc::free(c_lmc as *mut libc::c_void);
            }
            if !rust_lmc.is_null() {
                libc::free(rust_lmc as *mut libc::c_void);
            }
            return;
        }

        zopfli::ffi::ZopfliInitCache(block_end.saturating_sub(block_start), c_lmc);
        zopfli::ffi::ZopfliInitCache(block_end.saturating_sub(block_start), rust_lmc);

        c_state.lmc = c_lmc;
        rust_state.lmc = rust_lmc;

        c_state.blockstart = block_start;
        c_state.blockend = block_end;
        rust_state.blockstart = block_start;
        rust_state.blockend = block_end;

        let c_options = fuzz_options.to_zopfli_options();
        let rust_options = fuzz_options.to_zopfli_options();

        c_state.options = &c_options;
        rust_state.options = &rust_options;

        zopfli::ffi::ZopfliCleanBlockState(&mut c_state);
        zopfli::lz77::ZopfliCleanBlockState(&mut rust_state);

        // After cleaning, the lmc pointer should be null in the Rust implementation's case as a sign of being freed.
        // The C implementation does not nullify the pointer after freeing, so we can't directly compare them.
        // The main purpose of this test is to catch memory errors (like double-frees or invalid frees)
        // that would be detected by libfuzzer's memory sanitizer.
        assert!(rust_state.lmc.is_null());
    }
});
