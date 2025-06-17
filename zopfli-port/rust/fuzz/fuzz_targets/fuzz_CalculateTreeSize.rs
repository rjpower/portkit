#![no_main]
use libfuzzer_sys::fuzz_target;
use std::os::raw::{c_int, c_uint};
use zopfli::ffi;
use zopfli::util::{ZOPFLI_NUM_D, ZOPFLI_NUM_LL};

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    ll_counts: [usize; ZOPFLI_NUM_LL],
    d_counts: [usize; ZOPFLI_NUM_D],
}

fuzz_target!(|input: FuzzInput| {
    let mut ll_lengths: [c_uint; ZOPFLI_NUM_LL] = [0; ZOPFLI_NUM_LL];
    let mut d_lengths: [c_uint; ZOPFLI_NUM_D] = [0; ZOPFLI_NUM_D];

    unsafe {
        ffi::ZopfliCalculateBitLengths(
            input.ll_counts.as_ptr(),
            ZOPFLI_NUM_LL,
            15,
            ll_lengths.as_mut_ptr(),
        );
        ffi::ZopfliCalculateBitLengths(
            input.d_counts.as_ptr(),
            ZOPFLI_NUM_D,
            15,
            d_lengths.as_mut_ptr(),
        );

        // The C code we are testing does not like it if there are no codes for lit/lengths.
        // This is a bug in zopfli, so we avoid it.
        let mut has_ll_code = false;
        for i in 0..ZOPFLI_NUM_LL {
            if ll_lengths[i] > 0 {
                has_ll_code = true;
                break;
            }
        }
        if !has_ll_code {
            return;
        }

        let c_result = ffi::CalculateTreeSize(ll_lengths.as_ptr(), d_lengths.as_ptr());
        let rust_result =
            zopfli::deflate::CalculateTreeSize(ll_lengths.as_ptr(), d_lengths.as_ptr());

        assert_eq!(c_result, rust_result);
    }
});
