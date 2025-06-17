#![no_main]

use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    let mut c_store = zopfli::ffi::ZopfliLZ77Store {
        litlens: std::ptr::null_mut(),
        dists: std::ptr::null_mut(),
        size: 0,
        data: std::ptr::null(),
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
        data: std::ptr::null(),
        pos: std::ptr::null_mut(),
        ll_symbol: std::ptr::null_mut(),
        d_symbol: std::ptr::null_mut(),
        ll_counts: std::ptr::null_mut(),
        d_counts: std::ptr::null_mut(),
    };

    unsafe {
        zopfli::ffi::ZopfliInitLZ77Store(data.as_ptr(), &mut c_store);
        zopfli::ffi::ZopfliInitLZ77Store(data.as_ptr(), &mut rust_store);
    }

    assert_eq!(c_store.size, rust_store.size);
    assert_eq!(c_store.litlens, rust_store.litlens);
    assert_eq!(c_store.dists, rust_store.dists);
    assert_eq!(c_store.pos, rust_store.pos);
    assert_eq!(c_store.data, rust_store.data);
    assert_eq!(c_store.ll_symbol, rust_store.ll_symbol);
    assert_eq!(c_store.d_symbol, rust_store.d_symbol);
    assert_eq!(c_store.ll_counts, rust_store.ll_counts);
    assert_eq!(c_store.d_counts, rust_store.d_counts);
});
