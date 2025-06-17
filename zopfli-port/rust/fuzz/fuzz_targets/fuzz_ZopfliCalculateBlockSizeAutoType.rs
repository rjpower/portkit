#![no_main]
use libfuzzer_sys::fuzz_target;
use libc::size_t;
use zopfli::ffi;

use arbitrary::{Arbitrary, Unstructured};

#[derive(Debug, Clone, Arbitrary)]
struct LitLenDist {
    litlen: u16,
    dist: u16,
}

#[derive(Debug, Arbitrary)]
struct FuzzInput {
    #[arbitrary(with = |u: &mut Unstructured| {
        let mut pairs = Vec::new();
        for _ in 0..u.int_in_range(0..=1024)? {
            let has_dist = u.ratio(1, 2)?;
            let litlen = if has_dist {
                u.int_in_range(3..=258)?
            } else {
                u.int_in_range(0..=255)?
            };
            let dist = if has_dist {
                u.int_in_range(1..=32768)?
            } else {
                0
            };
            pairs.push(LitLenDist { litlen, dist });
        }
        Ok(pairs)
    })]
    pairs: Vec<LitLenDist>,
    data: Vec<u8>,
    pos: Vec<size_t>,
    lstart: u16,
    lend: u16,
}

fuzz_target!(|input: FuzzInput| {
    let litlens: Vec<u16> = input.pairs.iter().map(|p| p.litlen).collect();
    let dists: Vec<u16> = input.pairs.iter().map(|p| p.dist).collect();

    if litlens.is_empty() {
        return;
    }
    if input.lstart >= input.lend || input.lend as usize > litlens.len() {
        return;
    }

    let size = litlens.len();
    let mut c_litlens = litlens.clone();
    let mut c_dists = dists.clone();

    let mut c_data = input.data.clone();
    let mut c_pos = input.pos.clone();
    if c_pos.len() < size {
        c_pos.resize(size, 0);
    }
    
    let mut c_ll_counts = vec![0; zopfli::util::ZOPFLI_NUM_LL];
    let mut c_d_counts = vec![0; zopfli::util::ZOPFLI_NUM_D];
    let mut c_ll_symbol = vec![0; size];
    let mut c_d_symbol = vec![0; size];
    
    let c_store = ffi::ZopfliLZ77Store {
        litlens: c_litlens.as_mut_ptr(),
        dists: c_dists.as_mut_ptr(),
        size: size as size_t,
        data: c_data.as_mut_ptr(),
        pos: c_pos.as_mut_ptr(),
        ll_symbol: c_ll_symbol.as_mut_ptr(),
        d_symbol: c_d_symbol.as_mut_ptr(),
        ll_counts: c_ll_counts.as_mut_ptr(),
        d_counts: c_d_counts.as_mut_ptr(),
    };

    let mut rust_litlens = litlens.clone();
    let mut rust_dists = dists.clone();

    let mut rust_data = input.data.clone();
    let mut rust_pos = input.pos.clone();
    if rust_pos.len() < size {
        rust_pos.resize(size, 0);
    }

    let mut rust_ll_counts = vec![0; zopfli::util::ZOPFLI_NUM_LL];
    let mut rust_d_counts = vec![0; zopfli::util::ZOPFLI_NUM_D];
    let mut rust_ll_symbol = vec![0; size];
    let mut rust_d_symbol = vec![0; size];

    let rust_store = ffi::ZopfliLZ77Store {
        litlens: rust_litlens.as_mut_ptr(),
        dists: rust_dists.as_mut_ptr(),
        size: size as size_t,
        data: rust_data.as_mut_ptr(),
        pos: rust_pos.as_mut_ptr(),
        ll_symbol: rust_ll_symbol.as_mut_ptr(),
        d_symbol: rust_d_symbol.as_mut_ptr(),
        ll_counts: rust_ll_counts.as_mut_ptr(),
        d_counts: rust_d_counts.as_mut_ptr(),
    };

    let c_result = unsafe { ffi::ZopfliCalculateBlockSizeAutoType(&c_store, input.lstart as size_t, input.lend as size_t) };
    let rust_result = unsafe { zopfli::deflate::ZopfliCalculateBlockSizeAutoType(&rust_store, input.lstart as size_t, input.lend as size_t) };

    assert_eq!(c_result, rust_result);
});
