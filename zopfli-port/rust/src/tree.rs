//! Glue code for tree.h

use libc::{c_int, c_uint, size_t};

use crate::katajainen::ZopfliLengthLimitedCodeLengths;

pub fn ZopfliCalculateBitLengths(
    count: *const usize,
    n: usize,
    maxbits: c_int,
    bitlengths: *mut c_uint,
) {
    let error = ZopfliLengthLimitedCodeLengths(count, n as c_int, maxbits, bitlengths);
    debug_assert_eq!(error, 0);
}

pub fn ZopfliLengthsToSymbols(
    lengths: *const c_uint,
    n: size_t,
    maxbits: c_uint,
    symbols: *mut c_uint,
) {
    let maxbits = maxbits as usize;
    let n = n as usize;

    // In the C code, bl_count and next_code are dynamically allocated.
    // Here we use Vec, Rust's idiomatic growable array type.
    // The C code uses size_t for bl_count but unsigned for next_code, so we match that.
    let mut bl_count: Vec<usize> = vec![0; maxbits + 1];
    let mut next_code: Vec<c_uint> = vec![0; maxbits + 1];

    // It's unsafe to dereference raw pointers. We create safe slices from them
    // to work with Rust's safety guarantees.
    let lengths_slice = unsafe { std::slice::from_raw_parts(lengths, n) };
    let symbols_slice = unsafe { std::slice::from_raw_parts_mut(symbols, n) };

    // The C code initializes symbols to 0.
    symbols_slice.fill(0);

    /* 1) Count the number of codes for each code length. Let bl_count[N] be the
    number of codes of length N, N >= 1. */
    // The C code initializes bl_count to 0s, which vec![0; size] already does.
    for &len in lengths_slice {
        // The C code asserts lengths[i] <= maxbits, so we don't need to check.
        bl_count[len as usize] += 1;
    }

    /* 2) Find the numerical value of the smallest code for each code length. */
    let mut code: c_uint = 0;
    bl_count[0] = 0;
    for bits in 1..=maxbits {
        code = (code + bl_count[bits - 1] as c_uint) << 1;
        next_code[bits] = code;
    }

    /* 3) Assign numerical values to all codes, using consecutive values for all
    codes of the same length with the base values determined at step 2. */
    for i in 0..n {
        let len = lengths_slice[i] as usize;
        if len != 0 {
            symbols_slice[i] = next_code[len];
            next_code[len] += 1;
        }
    }
}

use std::os::raw::c_double;

extern "C" {
    fn log(n: c_double) -> c_double;
}

pub fn ZopfliCalculateEntropy(count: *const size_t, n: size_t, bitlengths: *mut c_double) {
    let count = unsafe { std::slice::from_raw_parts(count, n) };
    let bitlengths = unsafe { std::slice::from_raw_parts_mut(bitlengths, n) };

    const K_INV_LOG2: f64 = 1.4426950408889; // 1.0 / log(2.0)

    let mut sum: u32 = 0;
    for &c in count {
        sum = sum.wrapping_add(c as u32);
    }

    let log2sum = (if sum == 0 {
        (n as f64).ln()
    } else {
        f64::from(sum).ln()
    }) * K_INV_LOG2;

    for i in 0..n {
        let c = count[i];
        if c == 0 {
            bitlengths[i] = log2sum;
        } else {
            bitlengths[i] = log2sum - unsafe { log(c as f64) } * K_INV_LOG2;
        }
        if bitlengths[i] < 0.0 && bitlengths[i] > -1e-5 {
            bitlengths[i] = 0.0;
        }
        assert!(bitlengths[i] >= 0.0);
    }
}
