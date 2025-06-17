#![no_main]

use libfuzzer_sys::fuzz_target;

use zopfli::ffi;
use zopfli::squeeze::ZopfliLZ77OptimalFixed;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    data: Vec<u8>,
}

fuzz_target!(|input: FuzzInput| {
    if input.data.is_empty() {
        return;
    }
    let mut c_s: ffi::ZopfliBlockState = unsafe { std::mem::zeroed() };
    let mut rust_s: ffi::ZopfliBlockState = unsafe { std::mem::zeroed() };
    let mut c_store = ffi::ZopfliLZ77Store::default();
    let mut rust_store = ffi::ZopfliLZ77Store::default();
    
    let options = ffi::ZopfliOptions::default();
    c_s.options = &options;
    rust_s.options = &options;

    unsafe {
        ffi::ZopfliInitLZ77Store(input.data.as_ptr(), &mut c_store);
        ffi::ZopfliInitLZ77Store(input.data.as_ptr(), &mut rust_store);

        ffi::ZopfliLZ77OptimalFixed(&mut c_s, input.data.as_ptr(), 0, input.data.len(), &mut c_store);
        ZopfliLZ77OptimalFixed(&mut rust_s, input.data.as_ptr(), 0, input.data.len(), &mut rust_store);

        assert_eq!(c_store.size, rust_store.size);
        
        let c_litlens = std::slice::from_raw_parts(c_store.litlens, c_store.size);
        let rust_litlens = std::slice::from_raw_parts(rust_store.litlens, rust_store.size);
        assert_eq!(c_litlens, rust_litlens);

        let c_dists = std::slice::from_raw_parts(c_store.dists, c_store.size);
        let rust_dists = std::slice::from_raw_parts(rust_store.dists, rust_store.size);
        assert_eq!(c_dists, rust_dists);

        ffi::ZopfliCleanLZ77Store(&mut c_store);
        ffi::ZopfliCleanLZ77Store(&mut rust_store);
    }
});
