use crate::ffi;
use crate::util::ZOPFLI_CACHE_LENGTH;
use libc::{calloc, c_void, free, size_t, c_ushort};
use std::mem::size_of;
use std::os::raw::c_uchar;

pub unsafe fn ZopfliInitCache(blocksize: size_t, lmc: *mut ffi::ZopfliLongestMatchCache) {
    (*lmc).length = calloc(blocksize, size_of::<c_ushort>()) as *mut c_ushort;
    (*lmc).dist = calloc(blocksize, size_of::<c_ushort>()) as *mut c_ushort;
    (*lmc).sublen = calloc(
        ZOPFLI_CACHE_LENGTH as usize * 3 * blocksize,
        size_of::<c_uchar>(),
    ) as *mut c_uchar;

    for i in 0..blocksize {
        *(*lmc).length.add(i) = 1;
    }
}

pub unsafe fn ZopfliCleanCache(lmc: *mut ffi::ZopfliLongestMatchCache) {
    free((*lmc).length as *mut c_void);
    free((*lmc).dist as *mut c_void);
    free((*lmc).sublen as *mut c_void);
}

pub unsafe fn ZopfliMaxCachedSublen(lmc: *const ffi::ZopfliLongestMatchCache, pos: size_t, _length: size_t) -> ::std::os::raw::c_uint {
    if ZOPFLI_CACHE_LENGTH == 0 {
        return 0;
    }
    let cache = (*lmc).sublen.offset((ZOPFLI_CACHE_LENGTH * pos * 3) as isize);
    if *cache.offset(1) == 0 && *cache.offset(2) == 0 {
        return 0;
    }
    (*cache.offset(((ZOPFLI_CACHE_LENGTH - 1) * 3) as isize)) as u32 + 3
}





pub unsafe fn ZopfliSublenToCache(
    sublen: *const std::os::raw::c_ushort,
    pos: libc::size_t,
    length: libc::size_t,
    lmc: *mut crate::ffi::ZopfliLongestMatchCache,
) {
    if crate::util::ZOPFLI_CACHE_LENGTH == 0 {
        return;
    }

    let cache = (*lmc)
        .sublen
        .offset((crate::util::ZOPFLI_CACHE_LENGTH * pos * 3) as isize);
    if length < 3 {
        return;
    }

    let mut j = 0;
    let mut bestlength = 0;
    for i in 3..=length {
        if i == length || *sublen.add(i) != *sublen.add(i + 1) {
            *cache.add(j * 3) = (i - 3) as std::os::raw::c_uchar;
            *cache.add(j * 3 + 1) = (*sublen.add(i) % 256) as std::os::raw::c_uchar;
            *cache.add(j * 3 + 2) = ((*sublen.add(i) >> 8) % 256) as std::os::raw::c_uchar;
            bestlength = i;
            j += 1;
            if j >= crate::util::ZOPFLI_CACHE_LENGTH {
                break;
            }
        }
    }
    if j < crate::util::ZOPFLI_CACHE_LENGTH {
        debug_assert!(bestlength == length);
        *cache.add((crate::util::ZOPFLI_CACHE_LENGTH - 1) * 3) = (bestlength - 3) as std::os::raw::c_uchar;
    } else {
        debug_assert!(bestlength <= length);
    }
}



pub unsafe fn ZopfliCacheToSublen(
    lmc: *const ffi::ZopfliLongestMatchCache,
    pos: usize,
    length: usize,
    sublen: *mut c_ushort,
) {
    if ZOPFLI_CACHE_LENGTH == 0 || length < 3 {
        return;
    }

    let maxlength = ZopfliMaxCachedSublen(lmc, pos, length) as usize;
    let mut prevlength = 0;

    let cache_ptr = (*lmc).sublen.add(ZOPFLI_CACHE_LENGTH * pos * 3);
    let sublen = std::slice::from_raw_parts_mut(sublen, length + 2);

    for j in 0..ZOPFLI_CACHE_LENGTH {
        let entry_ptr = cache_ptr.add(j * 3);
        let current_length = *entry_ptr as usize + 3;
        let dist = *entry_ptr.add(1) as u16 + 256 * *entry_ptr.add(2) as u16;

        for i in prevlength..=current_length {
            if i < sublen.len() {
                sublen[i] = dist;
            }
        }

        if current_length == maxlength {
            break;
        }
        prevlength = current_length + 1;
    }
}
