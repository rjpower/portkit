
#![no_main]

use libfuzzer_sys::fuzz_target;
use std::slice;
use zopfli::ffi;
use zopfli::lz77;

unsafe fn clone_store(store: &ffi::ZopfliLZ77Store) -> ffi::ZopfliLZ77Store {
    let mut new_store = ffi::ZopfliLZ77Store {
        litlens: std::ptr::null_mut(),
        dists: std::ptr::null_mut(),
        size: store.size,
        data: store.data,
        pos: std::ptr::null_mut(),
        ll_symbol: std::ptr::null_mut(),
        d_symbol: std::ptr::null_mut(),
        ll_counts: std::ptr::null_mut(),
        d_counts: std::ptr::null_mut(),
    };

    if store.size > 0 {
        let size = store.size as usize;
        new_store.litlens = libc::malloc(size * std::mem::size_of::<u16>()) as *mut u16;
        new_store.dists = libc::malloc(size * std::mem::size_of::<u16>()) as *mut u16;
        new_store.pos = libc::malloc(size * std::mem::size_of::<usize>()) as *mut usize;
        new_store.ll_symbol = libc::malloc(size * std::mem::size_of::<u16>()) as *mut u16;
        new_store.d_symbol = libc::malloc(size * std::mem::size_of::<u16>()) as *mut u16;

        let ll_counts_size = (size / zopfli::util::ZOPFLI_NUM_LL as usize + 1) * zopfli::util::ZOPFLI_NUM_LL as usize;
        new_store.ll_counts = libc::malloc(ll_counts_size * std::mem::size_of::<libc::size_t>()) as *mut libc::size_t;

        let d_counts_size = (size / zopfli::util::ZOPFLI_NUM_D as usize + 1) * zopfli::util::ZOPFLI_NUM_D as usize;
        new_store.d_counts = libc::malloc(d_counts_size * std::mem::size_of::<libc::size_t>()) as *mut libc::size_t;


        std::ptr::copy_nonoverlapping(store.litlens, new_store.litlens, size);
        std::ptr::copy_nonoverlapping(store.dists, new_store.dists, size);
        std::ptr::copy_nonoverlapping(store.pos, new_store.pos, size);
        std::ptr::copy_nonoverlapping(store.ll_symbol, new_store.ll_symbol, size);
        std::ptr::copy_nonoverlapping(store.d_symbol, new_store.d_symbol, size);
        std::ptr::copy_nonoverlapping(store.ll_counts, new_store.ll_counts, ll_counts_size);
        std::ptr::copy_nonoverlapping(store.d_counts, new_store.d_counts, d_counts_size);
    }
    new_store
}

fuzz_target!(|data: &[u8]| {
    if data.len() < 5 {
        return;
    }
    let length = u16::from_le_bytes([data[0], data[1]]) % 259;
    if length == 0 {
        return;
    }
    let dist = u16::from_le_bytes([data[2], data[3]]);
    let pos = data[4] as usize;

    let mut c_store: ffi::ZopfliLZ77Store = unsafe { std::mem::zeroed() };
    let mut rust_store: ffi::ZopfliLZ77Store = unsafe { std::mem::zeroed() };

    lz77::ZopfliInitLZ77Store(data.as_ptr(), &mut c_store);
    lz77::ZopfliInitLZ77Store(data.as_ptr(), &mut rust_store);

    let mut c_store_pre = unsafe { clone_store(&c_store) }; // will be empty now
    rust_store = unsafe { clone_store(&c_store) };

    unsafe {
        ffi::ZopfliStoreLitLenDist(length, dist, pos, &mut c_store);
        lz77::ZopfliStoreLitLenDist(length, dist, pos, &mut rust_store);

        assert_eq!(c_store.size, rust_store.size, "size mismatch");

        let size = c_store.size as usize;
        if size > 0 {
            let c_litlens = slice::from_raw_parts(c_store.litlens, size);
            let rust_litlens = slice::from_raw_parts(rust_store.litlens, size);
            assert_eq!(c_litlens, rust_litlens, "litlens mismatch");

            let c_dists = slice::from_raw_parts(c_store.dists, size);
            let rust_dists = slice::from_raw_parts(rust_store.dists, size);
            assert_eq!(c_dists, rust_dists, "dists mismatch");

            let c_pos = slice::from_raw_parts(c_store.pos, size);
            let rust_pos = slice::from_raw_parts(rust_store.pos, size);
            assert_eq!(c_pos, rust_pos, "pos mismatch");

            let c_ll_symbol = slice::from_raw_parts(c_store.ll_symbol, size);
            let rust_ll_symbol = slice::from_raw_parts(rust_store.ll_symbol, size);
            assert_eq!(c_ll_symbol, rust_ll_symbol, "ll_symbol mismatch");

            let c_d_symbol = slice::from_raw_parts(c_store.d_symbol, size);
            let rust_d_symbol = slice::from_raw_parts(rust_store.d_symbol, size);
            assert_eq!(c_d_symbol, rust_d_symbol, "d_symbol mismatch");

            let ll_counts_size = (size as usize / zopfli::util::ZOPFLI_NUM_LL as usize + 1) * zopfli::util::ZOPFLI_NUM_LL as usize;
            let c_ll_counts = slice::from_raw_parts(c_store.ll_counts, ll_counts_size);
            let rust_ll_counts = slice::from_raw_parts(rust_store.ll_counts, ll_counts_size);
            assert_eq!(c_ll_counts, rust_ll_counts, "ll_counts mismatch");

            let d_counts_size = (size as usize / zopfli::util::ZOPFLI_NUM_D as usize + 1) * zopfli::util::ZOPFLI_NUM_D as usize;
            let c_d_counts = slice::from_raw_parts(c_store.d_counts, d_counts_size);
            let rust_d_counts = slice::from_raw_parts(rust_store.d_counts, d_counts_size);
            assert_eq!(c_d_counts, rust_d_counts, "d_counts mismatch");
        }

        lz77::ZopfliCleanLZ77Store(&mut c_store);
        lz77::ZopfliCleanLZ77Store(&mut rust_store);
        lz77::ZopfliCleanLZ77Store(&mut c_store_pre);
    }
});
