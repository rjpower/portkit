#![no_main]

use libfuzzer_sys::fuzz_target;
use std::slice;
use zopfli::katajainen::ZopfliLengthLimitedCodeLengths as rust_ZopfliLengthLimitedCodeLengths;

use arbitrary::{Arbitrary, Unstructured};

extern "C" {
    fn ZopfliLengthLimitedCodeLengths(
        frequencies: *const usize,
        n: libc::c_int,
        maxbits: libc::c_int,
        bitlengths: *mut libc::c_uint,
    ) -> libc::c_int;
}


#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    #[arbitrary(with = |u: &mut Unstructured| u.int_in_range(0..=30))]
    maxbits: u8,
    frequencies: Vec<usize>,
}


fuzz_target!(|input: FuzzInput| {
    let maxbits = input.maxbits as i32;
    let frequencies = input.frequencies;
    let n = frequencies.len();
    
    // We need n frequencies, each taking up to size_of::<usize>() bytes.
    let frequency_data_len = n * std::mem::size_of::<usize>();
    if frequencies.len() < frequency_data_len {
        return;
    }


    let mut c_bitlengths = vec![0u32; n];
    let mut rust_bitlengths = vec![0u32; n];

    let c_ret;
    let rust_ret;

    unsafe {
        c_ret = ZopfliLengthLimitedCodeLengths(
            frequencies.as_ptr(),
            n as libc::c_int,
            maxbits as libc::c_int,
            c_bitlengths.as_mut_ptr(),
        );
    }

    rust_ret = rust_ZopfliLengthLimitedCodeLengths(
        frequencies.as_ptr(),
        n as libc::c_int,
        maxbits as libc::c_int,
        rust_bitlengths.as_mut_ptr(),
    );

    assert_eq!(c_ret, rust_ret, "Return values differ");

    if c_ret == 0 {
        // Unsafe block to create a slice from the raw pointer.
        // This is safe because we know the `bitlengths` pointer is valid
        // and points to `n` elements.
        let c_slice = unsafe { slice::from_raw_parts(c_bitlengths.as_ptr(), n) };
        let rust_slice = unsafe { slice::from_raw_parts(rust_bitlengths.as_ptr(), n) };
        
        // Use a verbose assert to show the difference
        assert_eq!(
            c_slice,
            rust_slice,
            "\nBitlengths differ for n={}, maxbits={}:\n  C: {:?}\n  Rust: {:?}\n  Frequencies: {:?}\n C_ret: {}, Rust_ret: {}",
            n,
            maxbits,
            c_slice,
            rust_slice,
            frequencies,
            c_ret,
            rust_ret
        );
    }
});
