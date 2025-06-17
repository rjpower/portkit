#![no_main]

use libfuzzer_sys::fuzz_target;
use std::os::raw::c_uint;
use zopfli::ffi;
use zopfli::util::{ZOPFLI_MAX_MATCH, ZOPFLI_NUM_LL};
use arbitrary::{Arbitrary, Unstructured};

#[derive(Debug)]
struct FuzzInput {
    ll_lengths: Vec<c_uint>,
    d_lengths: Vec<c_uint>,
    litlens: Vec<u16>,
    dists: Vec<u16>,
    size: usize,
    lstart: usize,
    lend: usize,
}

impl Clone for FuzzInput {
    fn clone(&self) -> Self {
        Self {
            ll_lengths: self.ll_lengths.clone(),
            d_lengths: self.d_lengths.clone(),
            litlens: self.litlens.clone(),
            dists: self.dists.clone(),
            size: self.size,
            lstart: self.lstart,
            lend: self.lend,
        }
    }
}

impl<'a> Arbitrary<'a> for FuzzInput {
    fn arbitrary(u: &mut Unstructured<'a>) -> arbitrary::Result<Self> {
        let mut ll_lengths = Vec::with_capacity(ZOPFLI_NUM_LL);
        for _ in 0..ZOPFLI_NUM_LL {
            ll_lengths.push(u.int_in_range(0..=15)?);
        }

        let mut d_lengths = Vec::with_capacity(32);
        for _ in 0..32 {
            d_lengths.push(u.int_in_range(0..=15)?);
        }

        let size = u.int_in_range(0..=1024)?;
        let mut dists = Vec::with_capacity(size);
        for _ in 0..size {
            if u.ratio(1, 2)? {
                dists.push(u.int_in_range(1..=ZOPFLI_MAX_MATCH as u16)?);
            } else {
                dists.push(0);
            }
        }

        let mut litlens = Vec::with_capacity(size);
        for i in 0..size {
            if dists[i] == 0 {
                // literal
                litlens.push(u.int_in_range(0..=255)?);
            } else {
                // length
                litlens.push(u.int_in_range(3..=258)?);
            }
        }

        let lstart = if size == 0 { 0 } else { u.int_in_range(0..=size-1)? };
        let lend = if lstart >= size { lstart } else { u.int_in_range(lstart..=size)? };

        Ok(FuzzInput {
            ll_lengths,
            d_lengths,
            litlens,
            dists,
            size,
            lstart,
            lend,
        })
    }
}

fuzz_target!(|input: FuzzInput| {
    let mut c_input = input.clone();
    let mut rust_input = input.clone();

    let c_lz77 = zopfli::ffi::ZopfliLZ77Store {
        litlens: c_input.litlens.as_mut_ptr(),
        dists: c_input.dists.as_mut_ptr(),
        size: c_input.size,
        data: std::ptr::null(),
        pos: std::ptr::null_mut(),
        ll_symbol: std::ptr::null_mut(),
        d_symbol: std::ptr::null_mut(),
        ll_counts: std::ptr::null_mut(),
        d_counts: std::ptr::null_mut(),
    };

    let rust_lz77 = zopfli::ffi::ZopfliLZ77Store {
        litlens: rust_input.litlens.as_mut_ptr(),
        dists: rust_input.dists.as_mut_ptr(),
        size: rust_input.size,
        data: std::ptr::null(),
        pos: std::ptr::null_mut(),
        ll_symbol: std::ptr::null_mut(),
        d_symbol: std::ptr::null_mut(),
        ll_counts: std::ptr::null_mut(),
        d_counts: std::ptr::null_mut(),
    };

    let c_result = unsafe {
        ffi::CalculateBlockSymbolSize(
            c_input.ll_lengths.as_ptr(),
            c_input.d_lengths.as_ptr(),
            &c_lz77,
            c_input.lstart,
            c_input.lend,
        )
    };

    let rust_result = unsafe {
        zopfli::deflate::CalculateBlockSymbolSize(
            rust_input.ll_lengths.as_ptr(),
            rust_input.d_lengths.as_ptr(),
            &rust_lz77,
            rust_input.lstart,
            rust_input.lend,
        )
    };

    assert_eq!(c_result, rust_result);
});
