
use std::os::raw::{c_int, c_ushort};
use libc::{malloc, size_t};
use crate::util::{ZOPFLI_HASH_SAME, ZOPFLI_HASH_SAME_HASH};
use crate::ffi::ZopfliHash;

pub unsafe fn ZopfliAllocHash(window_size: size_t, h: *mut ZopfliHash) {
    if h.is_null() {
        return;
    }
    
    // Allocate main hash arrays
    (*h).head = malloc(std::mem::size_of::<c_int>() * 65536) as *mut c_int;
    (*h).prev = malloc(std::mem::size_of::<c_ushort>() * window_size) as *mut c_ushort;
    (*h).hashval = malloc(std::mem::size_of::<c_int>() * window_size) as *mut c_int;

    // Conditionally allocate same array
    if ZOPFLI_HASH_SAME {
        (*h).same = malloc(std::mem::size_of::<c_ushort>() * window_size) as *mut c_ushort;
    } else {
        (*h).same = std::ptr::null_mut();
    }

    // Conditionally allocate second hash arrays
    if ZOPFLI_HASH_SAME_HASH {
        (*h).head2 = malloc(std::mem::size_of::<c_int>() * 65536) as *mut c_int;
        (*h).prev2 = malloc(std::mem::size_of::<c_ushort>() * window_size) as *mut c_ushort;
        (*h).hashval2 = malloc(std::mem::size_of::<c_int>() * window_size) as *mut c_int;
    } else {
        (*h).head2 = std::ptr::null_mut();
        (*h).prev2 = std::ptr::null_mut();
        (*h).hashval2 = std::ptr::null_mut();
    }
}

pub unsafe fn ZopfliResetHash(window_size: size_t, h: *mut ZopfliHash) {
    if h.is_null() {
        return;
    }

    // Reset val to 0
    (*h).val = 0;
    
    // Initialize head array with -1 (no head so far)
    for i in 0..65536 {
        *(*h).head.add(i) = -1;
    }
    
    // Initialize prev and hashval arrays
    for i in 0..window_size {
        *(*h).prev.add(i) = i as c_ushort;  // If prev[j] == j, then prev[j] is uninitialized
        *(*h).hashval.add(i) = -1;
    }

    // Conditionally initialize same array
    if ZOPFLI_HASH_SAME && !(*h).same.is_null() {
        for i in 0..window_size {
            *(*h).same.add(i) = 0;
        }
    }

    // Conditionally initialize second hash arrays
    if ZOPFLI_HASH_SAME_HASH {
        (*h).val2 = 0;
        
        if !(*h).head2.is_null() {
            for i in 0..65536 {
                *(*h).head2.add(i) = -1;
            }
        }
        
        if !(*h).prev2.is_null() && !(*h).hashval2.is_null() {
            for i in 0..window_size {
                *(*h).prev2.add(i) = i as c_ushort;
                *(*h).hashval2.add(i) = -1;
            }
        }
    }
}

use crate::util::{HASH_MASK, HASH_SHIFT, ZOPFLI_MIN_MATCH, ZOPFLI_WINDOW_MASK, ZOPFLI_WINDOW_SIZE};
use std::os::raw::c_uchar;
use std::slice::from_raw_parts_mut;
pub unsafe fn ZopfliCleanHash(h: *mut ZopfliHash) {
    if h.is_null() {
        return;
    }

    libc::free((*h).head as *mut libc::c_void);
    libc::free((*h).prev as *mut libc::c_void);
    libc::free((*h).hashval as *mut libc::c_void);

    if ZOPFLI_HASH_SAME_HASH {
        libc::free((*h).head2 as *mut libc::c_void);
        libc::free((*h).prev2 as *mut libc::c_void);
        libc::free((*h).hashval2 as *mut libc::c_void);
    }

    if ZOPFLI_HASH_SAME {
        libc::free((*h).same as *mut libc::c_void);
    }
}

#[inline]
unsafe fn UpdateHashValue(h: *mut ZopfliHash, value: u8) {
    (*h).val = (((*h).val << HASH_SHIFT) ^ value as c_int) & HASH_MASK;
}

pub unsafe fn ZopfliUpdateHash(
    array: *const c_uchar,
    pos: size_t,
    end: size_t,
    h: *mut ZopfliHash,
) {
    let hpos = (pos & ZOPFLI_WINDOW_MASK) as usize;

    let value = if pos + ZOPFLI_MIN_MATCH <= end {
        *array.add(pos + ZOPFLI_MIN_MATCH - 1)
    } else {
        0
    };
    UpdateHashValue(h, value);
    let h_hashval = from_raw_parts_mut((*h).hashval, ZOPFLI_WINDOW_SIZE as usize);
    h_hashval[hpos] = (*h).val;

    let h_head = from_raw_parts_mut((*h).head, 65536);
    let h_prev = from_raw_parts_mut((*h).prev, ZOPFLI_WINDOW_SIZE as usize);
    if h_head[(*h).val as usize] != -1 && h_hashval[h_head[(*h).val as usize] as usize] == (*h).val {
        h_prev[hpos] = h_head[(*h).val as usize] as u16;
    } else {
        h_prev[hpos] = hpos as u16;
    }
    h_head[(*h).val as usize] = hpos as i32;

    let h_same = from_raw_parts_mut((*h).same, ZOPFLI_WINDOW_SIZE as usize);

    let mut amount = if pos > 0 && h_same[(pos - 1) & ZOPFLI_WINDOW_MASK as usize] > 1 {
        (h_same[(pos - 1) & ZOPFLI_WINDOW_MASK as usize] - 1) as usize
    } else {
        0
    };

    while pos + amount + 1 < end
        && *array.add(pos) == *array.add(pos + amount + 1)
        && amount < u16::MAX as usize
    {
        amount += 1;
    }
    h_same[hpos] = amount as u16;

    (*h).val2 = (((h_same[hpos].wrapping_sub(ZOPFLI_MIN_MATCH as u16)) & 255) as c_int) ^ (*h).val;
    let h_hashval2 = from_raw_parts_mut((*h).hashval2, ZOPFLI_WINDOW_SIZE as usize);
    h_hashval2[hpos] = (*h).val2;
    let h_head2 = from_raw_parts_mut((*h).head2, 65536);
    let h_prev2 = from_raw_parts_mut((*h).prev2, ZOPFLI_WINDOW_SIZE as usize);
    if h_head2[(*h).val2 as usize] != -1
        && h_hashval2[h_head2[(*h).val2 as usize] as usize] == (*h).val2
    {
        h_prev2[hpos] = h_head2[(*h).val2 as usize] as u16;
    } else {
        h_prev2[hpos] = hpos as u16;
    }
    h_head2[(*h).val2 as usize] = hpos as i32;
}

pub unsafe fn ZopfliWarmupHash(
    array: *const ::std::os::raw::c_uchar,
    pos: usize,
    end: usize,
    h: *mut ZopfliHash,
) {
    let array = std::slice::from_raw_parts(array, end);

    UpdateHashValue(h, array[pos]);
    if pos + 1 < end {
        UpdateHashValue(h, array[pos + 1]);
    }
}
