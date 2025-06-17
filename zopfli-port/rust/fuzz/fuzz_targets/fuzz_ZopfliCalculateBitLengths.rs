#![no_main]

use libfuzzer_sys::fuzz_target;
use std::os::raw::{c_int, c_uint};
use zopfli::ffi;

fuzz_target!(|data: &[u8]| {
    if data.len() < 2 {
        return;
    }

    // Parameters for ZopfliCalculateBitLengths
    // n: Number of symbols. DEFLATE uses up to 286, but we test up to 288.
    // The minimum number of symbols is 1.
    let n = (data[0] as usize % 288) + 1;

    // maxbits: Maximum bit length for a symbol. For DEFLATE, this is 15.
    let maxbits = (data[1] % 15) as c_int + 1;

    // We need at least `n` bytes to create the counts.
    if data.len() < 2 + n {
        return;
    }

    // count: Frequencies of each symbol.
    // We use the raw byte values as frequencies.
    let mut counts: Vec<SizeT> = data[2..2 + n].iter().map(|&b| b as SizeT).collect();

    // The C implementation has a special case for a single symbol.
    // If there's only one symbol, its frequency must be 1 for the bit length to be 0.
    // If we have only one symbol, let's manually set its count to 1 to match C's behavior
    // for a single-symbol tree, which should result in a 0-bit length code.
    // The C code doesn't explicitly require the count to be 1, but for a single present symbol,
    // the package-merge algorithm assigns a bit length of 0, which is standard for a trivial tree.
    // If we let the count be something other than 1, it doesn't change the outcome for a single symbol.
    // However, if all counts are 0, the C code might behave differently.
    // Let's ensure at least one count is non-zero to avoid trivial cases where no symbols are present.
    if n > 0 && counts.iter().all(|&c| c == 0) {
        counts[0] = 1;
    }

    let non_zero_counts = counts.iter().filter(|&&c| c > 0).count();
    if non_zero_counts as u64 > (1u64 << maxbits) {
        return;
    }


    // Output arrays for bit lengths.
    let mut c_bitlengths = vec![0 as c_uint; n];
    let mut rust_bitlengths = vec![0 as c_uint; n];

    // Call the C implementation.
    unsafe {
        ffi::ZopfliCalculateBitLengths(
            counts.as_ptr(),
            n,
            maxbits,
            c_bitlengths.as_mut_ptr(),
        );
    }

    // Call the Rust implementation.
    zopfli::tree::ZopfliCalculateBitLengths(
        counts.as_ptr(),
        n,
        maxbits,
        rust_bitlengths.as_mut_ptr(),
    );

    // Compare the results.
    assert_eq!(c_bitlengths, rust_bitlengths,
        "Bitlengths differ for n={}, maxbits={}", n, maxbits);
});

// In C, size_t is an unsigned integer type. We define it as usize for Rust.
type SizeT = usize;
