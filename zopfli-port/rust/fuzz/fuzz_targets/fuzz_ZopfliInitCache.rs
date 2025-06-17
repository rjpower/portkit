#![no_main]

use libfuzzer_sys::fuzz_target;
use zopfli::cache;
use zopfli::ffi;
use zopfli::util;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    blocksize: u8,
}

fuzz_target!(|input: FuzzInput| {
    let blocksize = input.blocksize as usize;
    if blocksize == 0 {
        return;
    }

    let mut lmc_c = ffi::ZopfliLongestMatchCache {
        length: std::ptr::null_mut(),
        dist: std::ptr::null_mut(),
        sublen: std::ptr::null_mut(),
    };
    let mut lmc_rust = ffi::ZopfliLongestMatchCache {
        length: std::ptr::null_mut(),
        dist: std::ptr::null_mut(),
        sublen: std::ptr::null_mut(),
    };

    unsafe {
        ffi::ZopfliInitCache(blocksize, &mut lmc_c);
        cache::ZopfliInitCache(blocksize, &mut lmc_rust);

        if !lmc_c.length.is_null() && !lmc_rust.length.is_null() {
            let length_c = std::slice::from_raw_parts(lmc_c.length, blocksize);
            let length_rust = std::slice::from_raw_parts(lmc_rust.length, blocksize);
            assert_eq!(length_c, length_rust, "Mismatch in length");
        }

        if !lmc_c.dist.is_null() && !lmc_rust.dist.is_null() {
            let dist_c = std::slice::from_raw_parts(lmc_c.dist, blocksize);
            let dist_rust = std::slice::from_raw_parts(lmc_rust.dist, blocksize);
            assert_eq!(dist_c, dist_rust, "Mismatch in dist");
        }

        if !lmc_c.sublen.is_null() && !lmc_rust.sublen.is_null() {
            let sublen_size = util::ZOPFLI_CACHE_LENGTH as usize * 3 * blocksize;
            let sublen_c = std::slice::from_raw_parts(lmc_c.sublen, sublen_size);
            let sublen_rust = std::slice::from_raw_parts(lmc_rust.sublen, sublen_size);
            assert_eq!(sublen_c, sublen_rust, "Mismatch in sublen");
        }

        ffi::ZopfliCleanCache(&mut lmc_c);
        cache::ZopfliCleanCache(&mut lmc_rust);
    }
});
