#![no_main]

use libfuzzer_sys::fuzz_target;
use std::os::raw::c_ushort;

use zopfli::ffi;
use zopfli::lz77;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    data: Vec<u8>,
    lstart: u16,
    lend: u16,
}

fuzz_target!(|input: FuzzInput| {
    let mut c_store = zopfli::ffi::ZopfliLZ77Store {
        litlens: std::ptr::null_mut(),
        dists: std::ptr::null_mut(),
        size: 0,
        data: input.data.as_ptr(),
        pos: std::ptr::null_mut(),
        ll_symbol: std::ptr::null_mut(),
        d_symbol: std::ptr::null_mut(),
        ll_counts: std::ptr::null_mut(),
        d_counts: std::ptr::null_mut(),
    };

    let mut rust_store = zopfli::ffi::ZopfliLZ77Store {
        litlens: std::ptr::null_mut(),
        dists: std::ptr::null_mut(),
        size: 0,
        data: input.data.as_ptr(),
        pos: std::ptr::null_mut(),
        ll_symbol: std::ptr::null_mut(),
        d_symbol: std::ptr::null_mut(),
        ll_counts: std::ptr::null_mut(),
        d_counts: std::ptr::null_mut(),
    };

    let size = input.data.len();

    if size > 0 {
        c_store.litlens =
            unsafe { libc::malloc(size * std::mem::size_of::<c_ushort>()) as *mut c_ushort };
        c_store.dists =
            unsafe { libc::malloc(size * std::mem::size_of::<c_ushort>()) as *mut c_ushort };
        c_store.pos = unsafe { libc::malloc(size * std::mem::size_of::<usize>()) as *mut usize };

        rust_store.litlens =
            unsafe { libc::malloc(size * std::mem::size_of::<c_ushort>()) as *mut c_ushort };
        rust_store.dists =
            unsafe { libc::malloc(size * std::mem::size_of::<c_ushort>()) as *mut c_ushort };
        rust_store.pos = unsafe { libc::malloc(size * std::mem::size_of::<usize>()) as *mut usize };

        for i in 0..size {
            unsafe {
                *c_store.litlens.add(i) = (i % 256) as c_ushort;
                *c_store.dists.add(i) = if i % 4 == 0 { 0 } else { (i % 32) as c_ushort };
                *c_store.pos.add(i) = i;

                *rust_store.litlens.add(i) = (i % 256) as c_ushort;
                *rust_store.dists.add(i) = if i % 4 == 0 { 0 } else { (i % 32) as c_ushort };
                *rust_store.pos.add(i) = i;
            }
        }
    }
    c_store.size = size;
    rust_store.size = size;

    let lstart = input.lstart as usize % (size + 1);
    let lend = input.lend as usize % (size + 1);
    let (lstart, lend) = if lstart > lend {
        (lend, lstart)
    } else {
        (lstart, lend)
    }; 

    let c_result = unsafe { ffi::ZopfliLZ77GetByteRange(&c_store, lstart, lend) };
    let rust_result = unsafe { lz77::ZopfliLZ77GetByteRange(&rust_store, lstart, lend) };

    assert_eq!(c_result, rust_result);

    unsafe {
        ffi::ZopfliCleanLZ77Store(&mut c_store);
        lz77::ZopfliCleanLZ77Store(&mut rust_store);
    }
});
