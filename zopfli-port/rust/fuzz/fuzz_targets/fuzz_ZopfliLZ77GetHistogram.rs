#![no_main]

use libfuzzer_sys::fuzz_target;
extern crate zopfli;

use zopfli::ffi;
use zopfli::lz77::ZopfliLZ77GetHistogram;
use zopfli::ffi::ZopfliLZ77Store;
use zopfli::util::{ZOPFLI_NUM_D, ZOPFLI_NUM_LL};

fuzz_target!(|data: &[u8]| {
    if data.len() < 4 {
        return;
    }
    let lstart = u16::from_le_bytes([data[0], data[1]]) as usize;
    let lend = u16::from_le_bytes([data[2], data[3]]) as usize;
    let data = &data[4..];

    if lstart >= lend || lend > data.len() {
        return;
    }

    let mut ll_symbol_vec = data
        .iter()
        .map(|&x| (x as u16) % (ZOPFLI_NUM_LL as u16))
        .collect::<Vec<u16>>();
    let mut d_symbol_vec = data
        .iter()
        .map(|&x| (x as u16) % (ZOPFLI_NUM_D as u16))
        .collect::<Vec<u16>>();
    let mut dists_vec = data.iter().map(|&x| x as u16).collect::<Vec<u16>>();

    let mut ll_counts_vec = vec![0usize; data.len() * (ZOPFLI_NUM_LL as usize)];
    let mut d_counts_vec = vec![0usize; data.len() * (ZOPFLI_NUM_D as usize)];

    // Generate a valid cumulative histogram for the test.
    if !data.is_empty() {
        // First element
        ll_counts_vec[ll_symbol_vec[0] as usize] = 1;
        if dists_vec[0] != 0 {
            d_counts_vec[d_symbol_vec[0] as usize] = 1;
        }

        // Subsequent elements
        for i in 1..data.len() {
            let ll_prev_start = (i - 1) * (ZOPFLI_NUM_LL as usize);
            let ll_curr_start = i * (ZOPFLI_NUM_LL as usize);
            let ll_symbol = ll_symbol_vec[i] as usize;

            let d_prev_start = (i - 1) * (ZOPFLI_NUM_D as usize);
            let d_curr_start = i * (ZOPFLI_NUM_D as usize);
            let d_symbol = d_symbol_vec[i] as usize;

            for j in 0..(ZOPFLI_NUM_LL as usize) {
                ll_counts_vec[ll_curr_start + j] = ll_counts_vec[ll_prev_start + j];
            }
            ll_counts_vec[ll_curr_start + ll_symbol] += 1;

            for j in 0..(ZOPFLI_NUM_D as usize) {
                d_counts_vec[d_curr_start + j] = d_counts_vec[d_prev_start + j];
            }
            if dists_vec[i] != 0 {
                d_counts_vec[d_curr_start + d_symbol] += 1;
            }
        }
    }

    let store = ZopfliLZ77Store {
        litlens: std::ptr::null_mut(),
        dists: dists_vec.as_mut_ptr(),
        size: data.len(),
        data: data.as_ptr(),
        pos: std::ptr::null_mut(),
        ll_symbol: ll_symbol_vec.as_mut_ptr(),
        d_symbol: d_symbol_vec.as_mut_ptr(),
        ll_counts: ll_counts_vec.as_mut_ptr(),
        d_counts: d_counts_vec.as_mut_ptr(),
    };


    let mut rust_ll_counts = vec![0; ZOPFLI_NUM_LL as usize];
    let mut rust_d_counts = vec![0; ZOPFLI_NUM_D as usize];
    let mut c_ll_counts = vec![0; ZOPFLI_NUM_LL as usize];
    let mut c_d_counts = vec![0; ZOPFLI_NUM_D as usize];

    unsafe {
        ZopfliLZ77GetHistogram(
            std::mem::transmute(&store),
            lstart,
            lend,
            rust_ll_counts.as_mut_ptr(),
            rust_d_counts.as_mut_ptr(),
        );
    }

    unsafe {
        ffi::ZopfliLZ77GetHistogram(
            &store as *const ZopfliLZ77Store,
            lstart,
            lend,
            c_ll_counts.as_mut_ptr(),
            c_d_counts.as_mut_ptr(),
        );
    }
    assert_eq!(rust_ll_counts, c_ll_counts);
    assert_eq!(rust_d_counts, c_d_counts);
});
