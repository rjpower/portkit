#![no_main]
use libfuzzer_sys::{fuzz_target, arbitrary::{self, Arbitrary, Unstructured}};
use libc::{c_void, free, size_t};
use std::os::raw::c_uchar;
use zopfli::ffi;

#[derive(Debug)]
struct FuzzInput {
    data: Vec<u8>,
    instart: usize,
    inend: usize,
    maxblocks: usize,
}

impl<'a> Arbitrary<'a> for FuzzInput {
    fn arbitrary(u: &mut Unstructured<'a>) -> arbitrary::Result<Self> {
        let data_size = u.int_in_range(10..=1024)?;
        let mut data = Vec::with_capacity(data_size);
        for _ in 0..data_size {
            data.push(u.arbitrary()?);
        }

        let instart = u.int_in_range(0..=data_size - 1)?;
        let inend = u.int_in_range(instart + 1..=data_size)?;
        let maxblocks = u.int_in_range(0..=10)?;

        Ok(FuzzInput {
            data,
            instart,
            inend,
            maxblocks,
        })
    }
}

fuzz_target!(|input: FuzzInput| {
    if input.data.is_empty() || input.instart >= input.inend {
        return;
    }

    // Limit input size to avoid excessive computation
    if input.inend - input.instart > 256 {
        return;
    }

    let options = ffi::ZopfliOptions {
        verbose: 0,
        verbose_more: 0,
        numiterations: 5, // Reduce iterations for faster fuzzing
        blocksplitting: 1,
        blocksplittinglast: 0,
        blocksplittingmax: 5, // Reduce max blocks for faster fuzzing
    };

    // --- Call C implementation ---
    let c_result = std::panic::catch_unwind(|| {
        let mut c_splitpoints: *mut size_t = std::ptr::null_mut();
        let mut c_npoints: size_t = 0;
        unsafe {
            ffi::ZopfliBlockSplit(
                &options,
                input.data.as_ptr() as *const c_uchar,
                input.instart,
                input.inend,
                input.maxblocks,
                &mut c_splitpoints,
                &mut c_npoints,
            );
        }
        (c_splitpoints, c_npoints)
    });

    // --- Call Rust implementation ---
    let r_result = std::panic::catch_unwind(|| {
        let mut r_splitpoints: *mut size_t = std::ptr::null_mut();
        let mut r_npoints: size_t = 0;
        unsafe {
            zopfli::blocksplitter::ZopfliBlockSplit(
                &options,
                input.data.as_ptr() as *const c_uchar,
                input.instart,
                input.inend,
                input.maxblocks,
                &mut r_splitpoints,
                &mut r_npoints,
            );
        }
        (r_splitpoints, r_npoints)
    });

    match (c_result, r_result) {
        (Ok((c_splitpoints, c_npoints)), Ok((r_splitpoints, r_npoints))) => {
            // Both succeeded, compare results
            assert_eq!(c_npoints, r_npoints, "Number of splitpoints differs");

            if c_npoints > 0 {
                let c_result_slice = unsafe { std::slice::from_raw_parts(c_splitpoints, c_npoints) };
                let r_result_slice = unsafe { std::slice::from_raw_parts(r_splitpoints, r_npoints) };
                assert_eq!(c_result_slice, r_result_slice, "Splitpoints differ");
            }

            // --- Cleanup ---
            unsafe {
                if !c_splitpoints.is_null() {
                    free(c_splitpoints as *mut c_void);
                }
                if !r_splitpoints.is_null() {
                    free(r_splitpoints as *mut c_void);
                }
            }
        }
        (Err(_), Err(_)) => {
            // Both panicked, that's fine - probably invalid input
            return;
        }
        (Ok(_), Err(_)) => {
            panic!("C implementation succeeded but Rust implementation panicked");
        }
        (Err(_), Ok(_)) => {
            panic!("Rust implementation succeeded but C implementation panicked");
        }
    }
});