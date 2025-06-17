#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::{c_int, c_uchar};
use std::ptr;
use zopfli::ffi;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    btype: u8,
    final_block: bool,
    data: Vec<u8>,
}

fuzz_target!(|input: FuzzInput| {
    let mut input = input;
    // btype must be 0, 1 or 2
    input.btype %= 3;

    if input.data.is_empty() {
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

        // C part
        let mut c_store = std::mem::MaybeUninit::<ffi::ZopfliLZ77Store>::uninit();
        ffi::ZopfliInitLZ77Store(input.data.as_ptr(), c_store.as_mut_ptr());
        let mut c_store = c_store.assume_init();

        let mut s = std::mem::MaybeUninit::<ffi::ZopfliBlockState>::uninit();
        ffi::ZopfliInitBlockState(&options, 0, input.data.len(), 0, s.as_mut_ptr());
        let mut s = s.assume_init();

        let mut h = std::mem::MaybeUninit::<ffi::ZopfliHash>::uninit();
        ffi::ZopfliAllocHash(zopfli::util::ZOPFLI_WINDOW_SIZE as usize, h.as_mut_ptr());
        let mut h = h.assume_init();
        ffi::ZopfliResetHash(zopfli::util::ZOPFLI_WINDOW_SIZE as usize, &mut h);

        ffi::ZopfliLZ77Greedy(
            &mut s,
            input.data.as_ptr(),
            0,
            input.data.len(),
            &mut c_store,
            &mut h,
        );

        let mut c_bp: c_uchar = 0;
        let mut c_out: *mut c_uchar = ptr::null_mut();
        let mut c_outsize: usize = 0;

        ffi::AddLZ77Block(
            &options,
            input.btype as c_int,
            input.final_block as c_int,
            &c_store,
            0,
            c_store.size,
            input.data.len(),
            &mut c_bp,
            &mut c_out,
            &mut c_outsize,
        );

        // Rust part
        let mut rust_store = std::mem::MaybeUninit::<ffi::ZopfliLZ77Store>::uninit();
        zopfli::ffi::ZopfliInitLZ77Store(input.data.as_ptr(), rust_store.as_mut_ptr());
        let mut rust_store = rust_store.assume_init();

        ffi::ZopfliLZ77Greedy(
            &mut s,
            input.data.as_ptr(),
            0,
            input.data.len(),
            &mut rust_store,
            &mut h,
        );

        let mut rust_bp: c_uchar = 0;
        let mut rust_out: *mut c_uchar = ptr::null_mut();
        let mut rust_outsize: usize = 0;

        zopfli::deflate::AddLZ77Block(
            &options,
            input.btype as c_int,
            input.final_block as c_int,
            &rust_store,
            0,
            rust_store.size,
            input.data.len(),
            &mut rust_bp,
            &mut rust_out,
            &mut rust_outsize,
        );

        assert_eq!(c_outsize, rust_outsize);
        if c_outsize > 0 {
            let c_slice = std::slice::from_raw_parts(c_out, c_outsize);
            let rust_slice = std::slice::from_raw_parts(rust_out, rust_outsize);
            assert_eq!(c_slice, rust_slice);
        }

        ffi::ZopfliCleanLZ77Store(&mut c_store);
        zopfli::ffi::ZopfliCleanLZ77Store(&mut rust_store);
        ffi::ZopfliCleanHash(&mut h);
        ffi::ZopfliCleanBlockState(&mut s);

        if !c_out.is_null() {
            libc::free(c_out as *mut libc::c_void);
        }
        if !rust_out.is_null() {
            libc::free(rust_out as *mut libc::c_void);
        }
    }
});