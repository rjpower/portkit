#![no_main]
use libfuzzer_sys::fuzz_target;
use zopfli::ffi;
use zopfli::util;
use zopfli::lz77;
use arbitrary::{Arbitrary, Result, Unstructured};

#[derive(Debug, Clone)]
struct FuzzInput {
    litlens: Vec<u16>,
    dists: Vec<u16>,
    lpos: usize,
    ll_symbol: Vec<u16>,
    d_symbol: Vec<u16>,
    ll_counts: Vec<usize>,
    d_counts: Vec<usize>,
}

impl<'a> Arbitrary<'a> for FuzzInput {
    fn arbitrary(u: &mut Unstructured<'a>) -> Result<Self> {
        let len = u.int_in_range(1..=64)?;
        let litlens = (0..len).map(|_| u.int_in_range(0..=258u16)).collect::<Result<Vec<_>>>()?;
        let dists = (0..len).map(|_| u16::arbitrary(u)).collect::<Result<Vec<_>>>()?;
        let lpos = u.int_in_range(0..=(len-1))?;
        let ll_symbol = (0..len).map(|_| u.int_in_range(0..=287u16)).collect::<Result<Vec<_>>>()?;
        let d_symbol = (0..len).map(|_| u.int_in_range(0..=31u16)).collect::<Result<Vec<_>>>()?;
        
        // The C implementation expects ll_counts and d_counts to contain cumulative histograms
        // The C code subtracts values from the histogram, so we need to ensure there are 
        // enough counts to prevent underflow.
        // 
        // The C code calculates llpos and dpos, then copies initial values and subtracts
        // Based on the algorithm, we need to build valid histogram data
        let llpos = 288 * (lpos / 288);
        let dpos = 32 * (lpos / 32);
        
        let ll_counts_len = llpos + 288;
        let d_counts_len = dpos + 32;
        
        // Initialize histogram with reasonable values that account for the symbols that will be subtracted
        let mut ll_counts = vec![0usize; ll_counts_len];
        let mut d_counts = vec![0usize; d_counts_len];
        
        // Pre-populate the histogram with counts for each symbol that appears in the range
        for i in 0..len {
            let symbol = ll_symbol[i] as usize;
            if symbol < 288 {
                ll_counts[llpos + symbol] += 1;
            }
            if dists[i] != 0 {
                let d_sym = d_symbol[i] as usize;
                if d_sym < 32 {
                    d_counts[dpos + d_sym] += 1;
                }
            }
        }
        
        // Add some extra counts to prevent underflow during subtraction
        for i in llpos..llpos + 288 {
            ll_counts[i] += u.int_in_range(1..=10)?;
        }
        for i in dpos..dpos + 32 {
            d_counts[i] += u.int_in_range(1..=10)?;
        }
        
        Ok(FuzzInput {
            litlens,
            dists,
            lpos,
            ll_symbol,
            d_symbol,
            ll_counts,
            d_counts,
        })
    }
}

fuzz_target!(|input: FuzzInput| {
    let input = input;
    let size = input.litlens.len();

    let lpos = input.lpos % size;

    let mut c_input = input.clone();
    let mut rust_input = input.clone();

    let c_store = ffi::ZopfliLZ77Store {
        litlens: c_input.litlens.as_mut_ptr(),
        dists: c_input.dists.as_mut_ptr(),
        size,
        data: std::ptr::null(),
        pos: std::ptr::null_mut(),
        ll_symbol: c_input.ll_symbol.as_mut_ptr(),
        d_symbol: c_input.d_symbol.as_mut_ptr(),
        ll_counts: c_input.ll_counts.as_mut_ptr(),
        d_counts: c_input.d_counts.as_mut_ptr(),
    };

    let rust_store = ffi::ZopfliLZ77Store {
        litlens: rust_input.litlens.as_mut_ptr(),
        dists: rust_input.dists.as_mut_ptr(),
        size,
        data: std::ptr::null(),
        pos: std::ptr::null_mut(),
        ll_symbol: rust_input.ll_symbol.as_mut_ptr(),
        d_symbol: rust_input.d_symbol.as_mut_ptr(),
        ll_counts: rust_input.ll_counts.as_mut_ptr(),
        d_counts: rust_input.d_counts.as_mut_ptr(),
    };

    let mut c_ll_counts = vec![0; util::ZOPFLI_NUM_LL as usize];
    let mut c_d_counts = vec![0; util::ZOPFLI_NUM_D as usize];

    let mut rust_ll_counts = vec![0; util::ZOPFLI_NUM_LL as usize];
    let mut rust_d_counts = vec![0; util::ZOPFLI_NUM_D as usize];

    unsafe {
        ffi::ZopfliLZ77GetHistogramAt(
            &c_store,
            lpos,
            c_ll_counts.as_mut_ptr(),
            c_d_counts.as_mut_ptr(),
        );
        lz77::ZopfliLZ77GetHistogramAt(
            &rust_store,
            lpos,
            rust_ll_counts.as_mut_ptr(),
            rust_d_counts.as_mut_ptr(),
        );
    }

    assert_eq!(c_ll_counts, rust_ll_counts);
    assert_eq!(c_d_counts, rust_d_counts);
});