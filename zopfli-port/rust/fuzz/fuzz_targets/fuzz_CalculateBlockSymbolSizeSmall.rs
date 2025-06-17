#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::c_uint;
use zopfli::ffi;
use zopfli::util::{ZOPFLI_NUM_D, ZOPFLI_NUM_LL};
use zopfli;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    ll_lengths: [c_uint; ZOPFLI_NUM_LL],
    d_lengths: [c_uint; ZOPFLI_NUM_D],
    lz77_litlens: Vec<u16>,
    lz77_dists: Vec<u16>,
    lstart: u16,
    lend: u16,
}

fuzz_target!(|input: FuzzInput| {
    let mut litlens = input.lz77_litlens;
    let size = litlens.len();
    let mut dists = input.lz77_dists;
    dists.resize(size, 0);

    for i in 0..size {
        if dists[i] == 0 {
            litlens[i] = litlens[i] % 256;
        } else {
            litlens[i] = (litlens[i] % 256) + 3;
            if litlens[i] > 258 {
                litlens[i] = 258;
            }
        }
    }

    let lstart = input.lstart as usize;
    let lend = input.lend as usize;

    if lstart >= size || lend > size || lstart > lend {
        return;
    }

    let c_lz77 = ffi::ZopfliLZ77Store {
        litlens: litlens.as_mut_ptr(),
        dists: dists.as_mut_ptr(),
        size: size as libc::size_t,
        data: std::ptr::null(),
        pos: std::ptr::null_mut(),
        ll_symbol: std::ptr::null_mut(),
        d_symbol: std::ptr::null_mut(),
        ll_counts: std::ptr::null_mut(),
        d_counts: std::ptr::null_mut(),
    };

    let rust_lz77 = ffi::ZopfliLZ77Store {
        litlens: litlens.as_mut_ptr(),
        dists: dists.as_mut_ptr(),
        size: size as libc::size_t,
        data: std::ptr::null(),
        pos: std::ptr::null_mut(),
        ll_symbol: std::ptr::null_mut(),
        d_symbol: std::ptr::null_mut(),
        ll_counts: std::ptr::null_mut(),
        d_counts: std::ptr::null_mut(),
    };

    let c_result = unsafe {
        ffi::CalculateBlockSymbolSizeSmall(
            input.ll_lengths.as_ptr(),
            input.d_lengths.as_ptr(),
            &c_lz77,
            lstart,
            lend,
        )
    };
    let rust_result = unsafe {
        zopfli::deflate::CalculateBlockSymbolSizeSmall(
            input.ll_lengths.as_ptr(),
            input.d_lengths.as_ptr(),
            &rust_lz77,
            lstart,
            lend,
        )
    };

    assert_eq!(c_result, rust_result);
});
