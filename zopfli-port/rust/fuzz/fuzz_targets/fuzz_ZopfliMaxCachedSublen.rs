#![no_main]

use libfuzzer_sys::fuzz_target;
extern crate zopfli;

use zopfli::ffi;
use zopfli::cache;
use zopfli::util;

use std::ptr;


fuzz_target!(|data: &[u8]| {
    if data.len() < 2 {
        return;
    }

    let blocksize = data[0] as usize;
    if blocksize == 0 {
        return;
    }
    let pos = data[1] as usize;
    if pos >= blocksize {
        return;
    }

    let mut lmc_c = ffi::ZopfliLongestMatchCache {
        length: ptr::null_mut(),
        dist: ptr::null_mut(),
        sublen: ptr::null_mut(),
    };
    let mut lmc_rust = ffi::ZopfliLongestMatchCache {
        length: ptr::null_mut(),
        dist: ptr::null_mut(),
        sublen: ptr::null_mut(),
    };

    unsafe {
        ffi::ZopfliInitCache(blocksize, &mut lmc_c);
        cache::ZopfliInitCache(blocksize, &mut lmc_rust as *mut _);
    }

    let sublen_size = util::ZOPFLI_CACHE_LENGTH * 3 * blocksize;

    if data.len() > 2 {
        let sublen_data = &data[2..];
        let copy_size = sublen_size.min(sublen_data.len());
        unsafe {
            ptr::copy_nonoverlapping(sublen_data.as_ptr(), lmc_c.sublen, copy_size);
            ptr::copy_nonoverlapping(sublen_data.as_ptr(), lmc_rust.sublen, copy_size);
        }
    }

    let result_c = unsafe { ffi::ZopfliMaxCachedSublen(&lmc_c, pos, blocksize) };
    let result_rust = unsafe { cache::ZopfliMaxCachedSublen(&lmc_rust, pos, blocksize) };

    assert_eq!(result_c, result_rust, "ZopfliMaxCachedSublen results differ");

    unsafe {
        ffi::ZopfliCleanCache(&mut lmc_c);
        cache::ZopfliCleanCache(&mut lmc_rust as *mut _);
    }
});
