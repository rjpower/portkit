#![no_main]
use libfuzzer_sys::{fuzz_target, arbitrary::{self, Arbitrary, Unstructured}};
use std::os::raw::{c_ushort};
use zopfli::{ffi, util};

#[derive(Debug)]
struct FuzzInput {
    data: Vec<u8>,
    maxblocks: usize,
}

impl<'a> Arbitrary<'a> for FuzzInput {
    fn arbitrary(u: &mut Unstructured<'a>) -> arbitrary::Result<Self> {
        let size = u.int_in_range(10..=1024)?;
        let mut data = Vec::with_capacity(size);
        for _ in 0..size {
            data.push(u.arbitrary()?);
        }
        let maxblocks = u.int_in_range(0..=10)?;

        Ok(FuzzInput {
            data,
            maxblocks,
        })
    }
}

unsafe fn init_store(store: *mut ffi::ZopfliLZ77Store, input: &FuzzInput) {
    // Use the actual ZopfliInitLZ77Store function with the input data
    ffi::ZopfliInitLZ77Store(input.data.as_ptr(), store);
}

unsafe fn clean_store(store: *mut ffi::ZopfliLZ77Store) {
    // Use the actual ZopfliCleanLZ77Store function which properly handles all pointers
    ffi::ZopfliCleanLZ77Store(store);
}

fuzz_target!(|input: FuzzInput| {
    if input.data.is_empty() {
        return;
    }

    let mut c_store = std::mem::MaybeUninit::uninit();
    let mut rust_store = std::mem::MaybeUninit::uninit();

    unsafe {
        init_store(c_store.as_mut_ptr(), &input);
        init_store(rust_store.as_mut_ptr(), &input);
    }

    let mut c_store = unsafe { c_store.assume_init() };
    let mut rust_store = unsafe { rust_store.assume_init() };

    let options = ffi::ZopfliOptions {
        verbose: 0,
        verbose_more: 0,
        numiterations: 15,
        blocksplitting: 1,
        blocksplittinglast: 0,
        blocksplittingmax: 15,
    };

    let mut c_splitpoints: *mut usize = std::ptr::null_mut();
    let mut c_npoints: usize = 0;
    let mut rust_splitpoints: *mut usize = std::ptr::null_mut();
    let mut rust_npoints: usize = 0;

    unsafe {
        ffi::ZopfliBlockSplitLZ77(
            &options,
            &c_store,
            input.maxblocks,
            &mut c_splitpoints,
            &mut c_npoints,
        );
        zopfli::blocksplitter::ZopfliBlockSplitLZ77(
            &options,
            &rust_store,
            input.maxblocks,
            &mut rust_splitpoints,
            &mut rust_npoints,
        );
    }

    assert_eq!(c_npoints, rust_npoints);

    if c_npoints > 0 {
        let c_splits = unsafe { std::slice::from_raw_parts(c_splitpoints, c_npoints) };
        let rust_splits = unsafe { std::slice::from_raw_parts(rust_splitpoints, rust_npoints) };
        assert_eq!(c_splits, rust_splits);
    }

    unsafe {
        if !c_splitpoints.is_null() {
            libc::free(c_splitpoints as *mut _);
        }
        if !rust_splitpoints.is_null() {
            libc::free(rust_splitpoints as *mut _);
        }
        clean_store(&mut c_store);
        clean_store(&mut rust_store);
    }
});
