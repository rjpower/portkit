#![no_main]
use libfuzzer_sys::fuzz_target;
use zopfli::ffi;
use zopfli::lz77;
use std::ptr;
use std::mem;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    data: Vec<u8>,
    litlens: Vec<u16>,
    dists: Vec<u16>,
    pos: Vec<usize>,
    ll_symbol: Vec<u16>,
    d_symbol: Vec<u16>,
    ll_counts: Vec<usize>,
    d_counts: Vec<usize>,
}

unsafe fn init_store(store: *mut ffi::ZopfliLZ77Store, input: &FuzzInput) {
    let store = &mut *store;
    ffi::ZopfliInitLZ77Store(input.data.as_ptr(), store);
    store.size = input.litlens.len() as libc::size_t;

    store.litlens = libc::malloc(input.litlens.len() * mem::size_of::<u16>()) as *mut u16;
    ptr::copy_nonoverlapping(input.litlens.as_ptr(), store.litlens, input.litlens.len());

    store.dists = libc::malloc(input.dists.len() * mem::size_of::<u16>()) as *mut u16;
    ptr::copy_nonoverlapping(input.dists.as_ptr(), store.dists, input.dists.len());

    store.pos = libc::malloc(input.pos.len() * mem::size_of::<usize>()) as *mut usize;
    ptr::copy_nonoverlapping(input.pos.as_ptr(), store.pos, input.pos.len());

    store.ll_symbol = libc::malloc(input.ll_symbol.len() * mem::size_of::<u16>()) as *mut u16;
    ptr::copy_nonoverlapping(input.ll_symbol.as_ptr(), store.ll_symbol, input.ll_symbol.len());

    store.d_symbol = libc::malloc(input.d_symbol.len() * mem::size_of::<u16>()) as *mut u16;
    ptr::copy_nonoverlapping(input.d_symbol.as_ptr(), store.d_symbol, input.d_symbol.len());

    store.ll_counts = libc::malloc(input.ll_counts.len() * mem::size_of::<usize>()) as *mut usize;
    ptr::copy_nonoverlapping(input.ll_counts.as_ptr(), store.ll_counts, input.ll_counts.len());

    store.d_counts = libc::malloc(input.d_counts.len() * mem::size_of::<usize>()) as *mut usize;
    ptr::copy_nonoverlapping(input.d_counts.as_ptr(), store.d_counts, input.d_counts.len());
}

unsafe fn compare_stores(store1: *const ffi::ZopfliLZ77Store, store2: *const ffi::ZopfliLZ77Store) {
    let store1 = &*store1;
    let store2 = &*store2;
    assert_eq!(store1.size, store2.size);
    if store1.size == 0 {
        return;
    }
    assert_eq!(std::slice::from_raw_parts(store1.litlens, store1.size as usize), std::slice::from_raw_parts(store2.litlens, store2.size as usize));
    assert_eq!(std::slice::from_raw_parts(store1.dists, store1.size as usize), std::slice::from_raw_parts(store2.dists, store2.size as usize));
    assert_eq!(std::slice::from_raw_parts(store1.pos, store1.size as usize), std::slice::from_raw_parts(store2.pos, store2.size as usize));
    assert_eq!(std::slice::from_raw_parts(store1.ll_symbol, store1.size as usize), std::slice::from_raw_parts(store2.ll_symbol, store2.size as usize));
    assert_eq!(std::slice::from_raw_parts(store1.d_symbol, store1.size as usize), std::slice::from_raw_parts(store2.d_symbol, store2.size as usize));

    let llsize = 288 * lz77::CeilDiv(store1.size as usize, 288);
    let dsize = 32 * lz77::CeilDiv(store1.size as usize, 32);

    assert_eq!(std::slice::from_raw_parts(store1.ll_counts, llsize), std::slice::from_raw_parts(store2.ll_counts, llsize));
    assert_eq!(std::slice::from_raw_parts(store1.d_counts, dsize), std::slice::from_raw_parts(store2.d_counts, dsize));
}

fuzz_target!(|input: FuzzInput| {
    if input.litlens.len() != input.dists.len() || input.litlens.len() != input.pos.len() || input.litlens.len() != input.ll_symbol.len() || input.litlens.len() != input.d_symbol.len() {
        return;
    }

    let llsize = 288 * lz77::CeilDiv(input.litlens.len(), 288);
    let dsize = 32 * lz77::CeilDiv(input.litlens.len(), 32);

    if input.ll_counts.len() != llsize || input.d_counts.len() != dsize {
        return;
    }

    unsafe {
        let mut c_source_store: ffi::ZopfliLZ77Store = mem::zeroed();
        let mut rust_source_store: ffi::ZopfliLZ77Store = mem::zeroed();
        let mut c_dest_store: ffi::ZopfliLZ77Store = mem::zeroed();
        let mut rust_dest_store: ffi::ZopfliLZ77Store = mem::zeroed();

        init_store(&mut c_source_store, &input);
        init_store(&mut rust_source_store, &input);

        ffi::ZopfliCopyLZ77Store(&c_source_store, &mut c_dest_store);
        zopfli::lz77::ZopfliCopyLZ77Store(&rust_source_store, &mut rust_dest_store);

        compare_stores(&c_dest_store, &rust_dest_store);

        ffi::ZopfliCleanLZ77Store(&mut c_source_store);
        ffi::ZopfliCleanLZ77Store(&mut rust_source_store);
        ffi::ZopfliCleanLZ77Store(&mut c_dest_store);
        ffi::ZopfliCleanLZ77Store(&mut rust_dest_store);
    }
});
