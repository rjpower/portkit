#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_uint;

fuzz_target!(|data: &[u8]| {
    if data.len() < 2 {
        return;
    }

    // The number of symbols, n, can be up to 288 for lit/len and 32 for dists in DEFLATE.
    // We'll allow a bit more for general-purpose testing.
    let n = (data[0] as usize) % 512;
    // maxbits is typically 15 for DEFLATE.
    let maxbits = (data[1] % 15) as c_uint + 1;

    if data.len() < 2 + n {
        return;
    }

    let mut lengths: Vec<c_uint> = Vec::with_capacity(n);
    for i in 0..n {
        // Ensure lengths[i] <= maxbits as per the assertion in the C code.
        lengths.push(data[2 + i] as c_uint % (maxbits + 1));
    }

    let mut c_symbols: Vec<c_uint> = vec![0; n];
    let mut rust_symbols: Vec<c_uint> = vec![0; n];

    // Call C implementation
    unsafe {
        zopfli::ffi::ZopfliLengthsToSymbols(
            lengths.as_ptr(),
            n,
            maxbits,
            c_symbols.as_mut_ptr(),
        );
    }

    // Call Rust implementation
    zopfli::tree::ZopfliLengthsToSymbols(
        lengths.as_ptr(),
        n,
        maxbits,
        rust_symbols.as_mut_ptr(),
    );

    // Compare results
    assert_eq!(c_symbols, rust_symbols, "Symbols produced by C and Rust implementations differ.");
});
