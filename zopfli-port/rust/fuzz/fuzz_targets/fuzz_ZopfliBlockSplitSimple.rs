#![no_main]
use libc::{c_void, free, size_t};
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    if data.len() < 4 {
        return;
    }

    // Determine instart, inend, and blocksize from the input data.
    // The function itself doesn't depend on the *content* of the input buffer,
    // only its size parameters.
    let instart = u16::from_le_bytes([data[0], data[1]]) as size_t;
    let inend = u16::from_le_bytes([data[2], data[3]]) as size_t;

    // Ensure instart < inend to have a valid range.
    if instart >= inend {
        return;
    }

    // Use the rest of the data to determine blocksize, ensuring it's not zero.
    let blocksize = if data.len() > 4 {
        let blocksize_val =
            usize::from_le_bytes(data[4..].try_into().unwrap_or(1usize.to_le_bytes()));
        (blocksize_val % (inend - instart + 1)).max(1)
    } else {
        1
    };

    // --- Call C implementation ---
    let mut c_splitpoints: *mut size_t = std::ptr::null_mut();
    let mut c_npoints: size_t = 0;
    unsafe {
        zopfli::ffi::ZopfliBlockSplitSimple(
            // The C function doesn't actually use this pointer, so it's safe to pass null.
            std::ptr::null(),
            instart,
            inend,
            blocksize,
            &mut c_splitpoints,
            &mut c_npoints,
        );
    }

    // --- Call Rust implementation ---
    let mut r_splitpoints: *mut size_t = std::ptr::null_mut();
    let mut r_npoints: size_t = 0;
    unsafe {
        zopfli::blocksplitter::ZopfliBlockSplitSimple(
            std::ptr::null(),
            instart,
            inend,
            blocksize,
            &mut r_splitpoints,
            &mut r_npoints,
        );
    }

    // --- Compare results ---
    assert_eq!(c_npoints, r_npoints, "Number of splitpoints differs");

    if c_npoints > 0 {
        let c_result_slice = unsafe { std::slice::from_raw_parts(c_splitpoints, c_npoints) };
        let r_result_slice = unsafe { std::slice::from_raw_parts(r_splitpoints, r_npoints) };
        assert_eq!(c_result_slice, r_result_slice, "Splitpoints differ");
    }

    // --- Cleanup ---
    // Free the memory allocated by the C and Rust functions.
    unsafe {
        if !c_splitpoints.is_null() {
            free(c_splitpoints as *mut c_void);
        }
        if !r_splitpoints.is_null() {
            // Reconstruct the Vec and let it drop, to free the memory.
            let _ = Vec::from_raw_parts(r_splitpoints, r_npoints, r_npoints);
        }
    }
});
