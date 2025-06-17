
#![no_main]

use libfuzzer_sys::fuzz_target;
use std::os::raw::{c_uchar, c_uint};
use zopfli::ffi;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    litlens: Vec<u16>,
    dists: Vec<u16>,
    ll_symbols: Vec<c_uint>,
    ll_lengths: Vec<c_uint>,
    d_symbols: Vec<c_uint>,
    d_lengths: Vec<c_uint>,
}

const ZOPFLI_NUM_LL: usize = 288;
const ZOPFLI_NUM_D: usize = 32;

fuzz_target!(|input: FuzzInput| {
    let mut input = input;
    let size = input.litlens.len();
    if size == 0 || input.dists.len() != size {
        return;
    }
    let mut litlens = input.litlens;
    let mut dists = input.dists;
    input.ll_symbols.resize(ZOPFLI_NUM_LL, 0);
    input.ll_lengths.resize(ZOPFLI_NUM_LL, 0);
    input.d_symbols.resize(ZOPFLI_NUM_D, 0);
    input.d_lengths.resize(ZOPFLI_NUM_D, 0);

    let mut expected_data_size = 0;
    for i in 0..size {
        if dists[i] == 0 {
            let litlen = litlens[i] as usize;
            if litlen >= 256 {
                return;
            }
            // Ensure length is > 0 so assert(ll_lengths[litlen] > 0) doesn't fire
            if input.ll_lengths[litlen] == 0 {
                input.ll_lengths[litlen] = 1;
            }
            expected_data_size += 1;
        } else {
            let litlen = litlens[i] as i32;
            if !(3..=288).contains(&litlen) {
                return;
            }
            let dist = dists[i] as i32;
            if !(1..=32768).contains(&dist) {
                return;
            }

            let lls = unsafe { ffi::ZopfliGetLengthSymbol(litlen) as usize };
            let ds = unsafe { ffi::ZopfliGetDistSymbol(dist) as usize };
            if lls >= ZOPFLI_NUM_LL || ds >= ZOPFLI_NUM_D {
                return;
            }
            // Ensure lengths are > 0 so asserts don't fire
            if input.ll_lengths[lls] == 0 {
                input.ll_lengths[lls] = 1;
            }
            if input.d_lengths[ds] == 0 {
                input.d_lengths[ds] = 1;
            }
            expected_data_size += litlen as usize;
        }
    }

    let lz77 = ffi::ZopfliLZ77Store {
        litlens: litlens.as_mut_ptr(),
        dists: dists.as_mut_ptr(),
        size: size,
        data: std::ptr::null(),
        pos: std::ptr::null_mut(),
        ll_symbol: std::ptr::null_mut(),
        d_symbol: std::ptr::null_mut(),
        ll_counts: std::ptr::null_mut(),
        d_counts: std::ptr::null_mut(),
    };

    let mut c_bp: c_uchar = 0;
    let mut c_out: *mut c_uchar = std::ptr::null_mut();
    let mut c_outsize: usize = 0;

    let mut rust_bp: c_uchar = 0;
    let mut rust_out: *mut c_uchar = std::ptr::null_mut();
    let mut rust_outsize: usize = 0;

    // We need to use unsafe blocks to call the C FFI and the Rust implementation
    // which has an unsafe signature.
    unsafe {
        ffi::AddLZ77Data(
            &lz77,
            0,
            size,
            0,
            input.ll_symbols.as_ptr(),
            input.ll_lengths.as_ptr(),
            input.d_symbols.as_ptr(),
            input.d_lengths.as_ptr(),
            &mut c_bp,
            &mut c_out,
            &mut c_outsize,
        );

        zopfli::deflate::AddLZ77Data(
            &lz77,
            0,
            size,
            expected_data_size,
            input.ll_symbols.as_ptr(),
            input.ll_lengths.as_ptr(),
            input.d_symbols.as_ptr(),
            input.d_lengths.as_ptr(),
            &mut rust_bp,
            &mut rust_out,
            &mut rust_outsize,
        );

        assert_eq!(c_bp, rust_bp);
        assert_eq!(c_outsize, rust_outsize);
        if c_outsize > 0 {
            let c_slice = std::slice::from_raw_parts(c_out, c_outsize);
            let rust_slice = std::slice::from_raw_parts(rust_out, rust_outsize);
            assert_eq!(c_slice, rust_slice);
        }

        // Free the memory allocated by the C and Rust functions
        libc::free(c_out as *mut libc::c_void);
        libc::free(rust_out as *mut libc::c_void);
    }
});
