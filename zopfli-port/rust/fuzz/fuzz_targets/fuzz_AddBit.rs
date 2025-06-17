#![no_main]

use libfuzzer_sys::fuzz_target;
use std::os::raw::c_int;
use arbitrary::{Arbitrary, Unstructured};
use std::mem::ManuallyDrop;

#[derive(Debug, Clone)]
struct FuzzInput {
    bit: c_int,
    bp: u8,
    out: Vec<u8>,
}

impl<'a> Arbitrary<'a> for FuzzInput {
    fn arbitrary(u: &mut Unstructured<'a>) -> arbitrary::Result<Self> {
        let bit = u.int_in_range(0..=1)?;
        let bp = u.int_in_range(0..=7)?;
        let len = u.int_in_range(1..=1024)?;
        let out = u.bytes(len)?.to_vec();

        Ok(FuzzInput {
            bit,
            bp,
            out,
        })
    }
}

fuzz_target!(|input: FuzzInput| {
    // C setup
    let mut c_out_vec = ManuallyDrop::new(input.out.clone());
    let mut c_out_ptr = c_out_vec.as_mut_ptr();
    let mut c_out_size = c_out_vec.len();
    let mut c_bp = input.bp;

    // Rust setup
    let mut rust_out_vec = input.out.clone();
    let mut rust_out_ptr = rust_out_vec.as_mut_ptr();
    let mut rust_out_size = rust_out_vec.len();
    let mut rust_bp = input.bp;
    
    // Run implementations
    unsafe {
        zopfli::ffi::AddBit(input.bit, &mut c_bp, &mut c_out_ptr, &mut c_out_size);
        zopfli::deflate::AddBit(input.bit, &mut rust_bp, &mut rust_out_ptr, &mut rust_out_size);
    }

    let c_data = unsafe { std::slice::from_raw_parts(c_out_ptr, c_out_size) };
    let rust_data = unsafe { std::slice::from_raw_parts(rust_out_ptr, rust_out_size) };

    assert_eq!(c_data, rust_data, "Output buffers do not match");
    assert_eq!(c_bp, rust_bp, "Bit pointers do not match");

    unsafe {
        // Free the C buffer that was potentially reallocated
        libc::free(c_out_ptr as *mut _);
    }
});