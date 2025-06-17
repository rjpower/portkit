#![no_main]

use libfuzzer_sys::fuzz_target;
use zopfli::ffi;
use zopfli::lz77;

use libc::malloc;

fuzz_target!(|data: &[u8]| {
    if data.len() < 1 {
        return;
    }
    let size = data[0] as usize;
    if size == 0 {
        return;
    }

    unsafe {
        // C store
        let mut c_store: zopfli::ffi::ZopfliLZ77Store = std::mem::zeroed();
        lz77::ZopfliInitLZ77Store(data.as_ptr(), &mut c_store);
        c_store.litlens = malloc(size * std::mem::size_of::<u16>()) as *mut u16;
        c_store.dists = malloc(size * std::mem::size_of::<u16>()) as *mut u16;
        c_store.pos = malloc(size * std::mem::size_of::<usize>()) as *mut usize;
        c_store.ll_symbol = malloc(size * std::mem::size_of::<u16>()) as *mut u16;
        c_store.d_symbol = malloc(size * std::mem::size_of::<u16>()) as *mut u16;
        c_store.ll_counts = malloc(288 * std::mem::size_of::<usize>()) as *mut usize;
        c_store.d_counts = malloc(32 * std::mem::size_of::<usize>()) as *mut usize;

        // Rust store
        let mut rust_store: zopfli::ffi::ZopfliLZ77Store = std::mem::zeroed();
        lz77::ZopfliInitLZ77Store(data.as_ptr(), &mut rust_store);
        rust_store.litlens = malloc(size * std::mem::size_of::<u16>()) as *mut u16;
        rust_store.dists = malloc(size * std::mem::size_of::<u16>()) as *mut u16;
        rust_store.pos = malloc(size * std::mem::size_of::<usize>()) as *mut usize;
        rust_store.ll_symbol = malloc(size * std::mem::size_of::<u16>()) as *mut u16;
        rust_store.d_symbol = malloc(size * std::mem::size_of::<u16>()) as *mut u16;
        rust_store.ll_counts = malloc(288 * std::mem::size_of::<usize>()) as *mut usize;
        rust_store.d_counts = malloc(32 * std::mem::size_of::<usize>()) as *mut usize;

        ffi::ZopfliCleanLZ77Store(&mut c_store);
        lz77::ZopfliCleanLZ77Store(&mut rust_store);
    }
});
