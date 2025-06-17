#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_double;

const MAX_N: usize = 1024;

fuzz_target!(|data: &[u8]| {
    if data.len() < 1 {
        return;
    }

    let n = (data.len() - 1).min(MAX_N);
    if n == 0 {
        return;
    }

    let counts: Vec<usize> = data[1..=n].iter().map(|&b| b as usize).collect();

    let mut c_bitlengths: Vec<c_double> = vec![0.0; n];
    let mut rust_bitlengths: Vec<c_double> = vec![0.0; n];

    // Call C implementation
    unsafe {
        zopfli::ffi::ZopfliCalculateEntropy(
            counts.as_ptr(),
            n,
            c_bitlengths.as_mut_ptr(),
        );
    }

    // Call Rust implementation
    zopfli::tree::ZopfliCalculateEntropy(
        counts.as_ptr(),
        n,
        rust_bitlengths.as_mut_ptr(),
    );

    // Compare results
    for i in 0..n {
        let c_val = c_bitlengths[i];
        let rust_val = rust_bitlengths[i];
        // Using an epsilon for float comparison
        assert!((c_val - rust_val).abs() < 1e-9,
            "Bit lengths differ at index {}: C={}, Rust={}, counts[{}]={}",
            i, c_val, rust_val, i, counts[i]);
    }
});
