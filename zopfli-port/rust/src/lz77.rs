use crate::ffi::ZopfliLZ77Store;
use crate::cache::ZopfliCleanCache;

pub fn ZopfliVerifyLenDist(data: &[u8], pos: usize, dist: u16, length: u16) {
    let datasize = data.len();
    let length = length as usize;
    let dist = dist as usize;

    assert!(pos + length <= datasize);

    for i in 0..length {
        assert_eq!(data[pos - dist + i], data[pos + i]);
    }
}

pub fn ZopfliInitLZ77Store(data: *const u8, store: *mut ZopfliLZ77Store) {
    unsafe {
        (*store).size = 0;
        (*store).litlens = std::ptr::null_mut();
        (*store).dists = std::ptr::null_mut();
        (*store).pos = std::ptr::null_mut();
        (*store).data = data;
        (*store).ll_symbol = std::ptr::null_mut();
        (*store).d_symbol = std::ptr::null_mut();
        (*store).ll_counts = std::ptr::null_mut();
        (*store).d_counts = std::ptr::null_mut();
    }
}

pub unsafe fn ZopfliCleanLZ77Store(store: *mut ZopfliLZ77Store) {
    libc::free((*store).litlens as *mut libc::c_void);
    libc::free((*store).dists as *mut libc::c_void);
    libc::free((*store).pos as *mut libc::c_void);
    libc::free((*store).ll_symbol as *mut libc::c_void);
    libc::free((*store).d_symbol as *mut libc::c_void);
    libc::free((*store).ll_counts as *mut libc::c_void);
    libc::free((*store).d_counts as *mut libc::c_void);
}

pub unsafe fn ZopfliLZ77GetByteRange(
    lz77: *const ZopfliLZ77Store,
    lstart: usize,
    lend: usize,
) -> usize {
    if lstart == lend {
        return 0;
    }
    let l = lend - 1;
    let store = &*lz77;
    let size = store.size;
    if size == 0 {
        return 0;
    }

    let pos = std::slice::from_raw_parts(store.pos, size);
    let dists = std::slice::from_raw_parts(store.dists, size);
    let litlens = std::slice::from_raw_parts(store.litlens, size);

    let last_symbol_len = if dists[l] == 0 { 1 } else { litlens[l] as usize };

    pos[l] + last_symbol_len - pos[lstart]
}

use crate::util::{ZOPFLI_NUM_D, ZOPFLI_NUM_LL};

pub fn ZopfliLZ77GetHistogramAt(
    lz77: &ZopfliLZ77Store,
    lpos: usize,
    ll_counts: *mut usize,
    d_counts: *mut usize,
) {
    assert!(lpos < lz77.size);
    let ll_counts_slice = unsafe { std::slice::from_raw_parts_mut(ll_counts, ZOPFLI_NUM_LL as usize) };
    let d_counts_slice = unsafe { std::slice::from_raw_parts_mut(d_counts, ZOPFLI_NUM_D as usize) };

    // The real histogram is created by using the histogram for this chunk, but
    // all superfluous values of this chunk subtracted.
    let llpos = ZOPFLI_NUM_LL as usize * (lpos / ZOPFLI_NUM_LL as usize);
    let dpos = ZOPFLI_NUM_D as usize * (lpos / ZOPFLI_NUM_D as usize);

    // Copy initial histogram values
    let ll_counts_src = unsafe { std::slice::from_raw_parts(lz77.ll_counts, llpos + ZOPFLI_NUM_LL as usize) };
    let d_counts_src = unsafe { std::slice::from_raw_parts(lz77.d_counts, dpos + ZOPFLI_NUM_D as usize) };
    
    for i in 0..ZOPFLI_NUM_LL as usize {
        ll_counts_slice[i] = ll_counts_src[llpos + i];
    }
    
    for i in 0..ZOPFLI_NUM_D as usize {
        d_counts_slice[i] = d_counts_src[dpos + i];
    }

    // Subtract the symbols that should not be counted
    let ll_symbol = unsafe { std::slice::from_raw_parts(lz77.ll_symbol, lz77.size) };
    let d_symbol = unsafe { std::slice::from_raw_parts(lz77.d_symbol, lz77.size) };
    let dists = unsafe { std::slice::from_raw_parts(lz77.dists, lz77.size) };

    for i in (lpos + 1)..(llpos + ZOPFLI_NUM_LL as usize).min(lz77.size) {
        ll_counts_slice[ll_symbol[i] as usize] -= 1;
    }

    for i in (lpos + 1)..(dpos + ZOPFLI_NUM_D as usize).min(lz77.size) {
        if dists[i] != 0 {
            d_counts_slice[d_symbol[i] as usize] -= 1;
        }
    }
}

pub fn ZopfliLZ77GetHistogram(
    lz77: *const ZopfliLZ77Store,
    lstart: usize,
    lend: usize,
    ll_counts: *mut usize,
    d_counts: *mut usize,
) {
    let lz77 = unsafe { &*lz77 };
    let ll_counts = unsafe { std::slice::from_raw_parts_mut(ll_counts, ZOPFLI_NUM_LL as usize) };
    let d_counts = unsafe { std::slice::from_raw_parts_mut(d_counts, ZOPFLI_NUM_D as usize) };

    if lstart + (ZOPFLI_NUM_LL as usize) * 3 > lend {
        ll_counts.fill(0);
        d_counts.fill(0);

        // Handle empty store case where pointers may be null
        if lz77.size == 0 || lstart >= lend {
            return;
        }

        let ll_symbol = unsafe { std::slice::from_raw_parts(lz77.ll_symbol, lz77.size) };
        let dists = unsafe { std::slice::from_raw_parts(lz77.dists, lz77.size) };
        let d_symbol = unsafe { std::slice::from_raw_parts(lz77.d_symbol, lz77.size) };

        for i in lstart..lend {
            ll_counts[ll_symbol[i] as usize] += 1;
            if dists[i] != 0 {
                d_counts[d_symbol[i] as usize] += 1;
            }
        }
    } else {
        ZopfliLZ77GetHistogramAt(lz77, lend - 1, ll_counts.as_mut_ptr(), d_counts.as_mut_ptr());
        if lstart > 0 {
            let mut ll_counts2 = [0; ZOPFLI_NUM_LL as usize];
            let mut d_counts2 = [0; ZOPFLI_NUM_D as usize];

            ZopfliLZ77GetHistogramAt(
                lz77,
                lstart - 1,
                ll_counts2.as_mut_ptr(),
                d_counts2.as_mut_ptr(),
            );

            for i in 0..ZOPFLI_NUM_LL as usize {
                ll_counts[i] -= ll_counts2[i];
            }
            for i in 0..ZOPFLI_NUM_D as usize {
                d_counts[i] -= d_counts2[i];
            }
        }
    }
}

unsafe fn zopfli_append_data<T: Copy>(value: T, data: &mut *mut T, size: &mut usize) {
    if *size == 0 || (*size & (*size - 1)) == 0 {
        let new_size = if *size == 0 { 1 } else { *size * 2 };
        let new_data = libc::realloc(*data as *mut libc::c_void, new_size * std::mem::size_of::<T>()) as *mut T;
        if new_data.is_null() {
            panic!("out of memory");
        }
        *data = new_data;
    }
    *(*data).add(*size) = value;
    *size += 1;
}

pub unsafe fn ZopfliStoreLitLenDist(
    length: u16,
    dist: u16,
    pos: usize,
    store: *mut ZopfliLZ77Store,
) {
    let origsize = (*store).size;
    let llstart = crate::util::ZOPFLI_NUM_LL as usize * (origsize / crate::util::ZOPFLI_NUM_LL as usize);
    let dstart = crate::util::ZOPFLI_NUM_D as usize * (origsize / crate::util::ZOPFLI_NUM_D as usize);

    if origsize % crate::util::ZOPFLI_NUM_LL as usize == 0 {
        let mut llsize = origsize;
        for i in 0..crate::util::ZOPFLI_NUM_LL as usize {
            let val = if origsize == 0 {
                0
            } else {
                *(*store).ll_counts.add(origsize - crate::util::ZOPFLI_NUM_LL as usize + i)
            };
            zopfli_append_data(val, &mut (*store).ll_counts, &mut llsize);
        }
    }
    if origsize % crate::util::ZOPFLI_NUM_D as usize == 0 {
        let mut dsize = origsize;
        for i in 0..crate::util::ZOPFLI_NUM_D as usize {
            let val = if origsize == 0 {
                0
            } else {
                *(*store).d_counts.add(origsize - crate::util::ZOPFLI_NUM_D as usize + i)
            };
            zopfli_append_data(val, &mut (*store).d_counts, &mut dsize);
        }
    }

    zopfli_append_data(length, &mut (*store).litlens, &mut (*store).size);
    (*store).size = origsize;
    zopfli_append_data(dist, &mut (*store).dists, &mut (*store).size);
    (*store).size = origsize;
    zopfli_append_data(pos, &mut (*store).pos, &mut (*store).size);

    assert!(length < 259);

    if dist == 0 {
        (*store).size = origsize;
        zopfli_append_data(length, &mut (*store).ll_symbol, &mut (*store).size);
        (*store).size = origsize;
        zopfli_append_data(0, &mut (*store).d_symbol, &mut (*store).size);
        *(*store).ll_counts.add(llstart + length as usize) += 1;
    } else {
        (*store).size = origsize;
        zopfli_append_data(
            crate::symbols::ZopfliGetLengthSymbol(length as i32) as u16,
            &mut (*store).ll_symbol,
            &mut (*store).size,
        );
        (*store).size = origsize;
        zopfli_append_data(
            crate::symbols::ZopfliGetDistSymbol(dist as i32) as u16,
            &mut (*store).d_symbol,
            &mut (*store).size,
        );
        *(*store)
            .ll_counts
            .add(llstart + crate::symbols::ZopfliGetLengthSymbol(length as i32) as usize) += 1;
        *(*store)
            .d_counts
            .add(dstart + crate::symbols::ZopfliGetDistSymbol(dist as i32) as usize) += 1;
    }
}

pub unsafe fn ZopfliAppendLZ77Store(store: *const ZopfliLZ77Store, target: *mut ZopfliLZ77Store) {
    for i in 0..(*store).size {
        ZopfliStoreLitLenDist(
            *(*store).litlens.add(i),
            *(*store).dists.add(i),
            *(*store).pos.add(i),
            target,
        );
    }
}

pub use crate::ffi::ZopfliBlockState;
use crate::ffi;
use std::ptr;
use libc::{c_void, malloc, free};

pub fn CeilDiv(a: usize, b: usize) -> usize {
    (a + b - 1) / b
}

use libc::c_int;
use libc::size_t;

pub unsafe fn ZopfliCleanBlockState(s: *mut ZopfliBlockState) {
    if !(*s).lmc.is_null() {
        ZopfliCleanCache((*s).lmc);
        free((*s).lmc as *mut c_void);
        (*s).lmc = ptr::null_mut();
    }
}

pub unsafe fn ZopfliInitBlockState(
    options: *const ffi::ZopfliOptions,
    blockstart: size_t,
    blockend: size_t,
    add_lmc: c_int,
    s: *mut ffi::ZopfliBlockState,
) {
    (*s).options = options;
    (*s).blockstart = blockstart;
    (*s).blockend = blockend;
    if add_lmc != 0 {
        let lmc =
            libc::malloc(std::mem::size_of::<ffi::ZopfliLongestMatchCache>()) as *mut ffi::ZopfliLongestMatchCache;
        if lmc.is_null() {
            std::process::abort();
        }
        ffi::ZopfliInitCache(blockend - blockstart, lmc);
        (*s).lmc = lmc;
    } else {
        (*s).lmc = ptr::null_mut();
    }
}

pub unsafe fn ZopfliCopyLZ77Store(
    source: *const ZopfliLZ77Store,
    dest: *mut ZopfliLZ77Store,
) {
    let source = &*source;
    let dest = &mut *dest;

    let llsize = ZOPFLI_NUM_LL as usize * CeilDiv(source.size as usize, ZOPFLI_NUM_LL as usize);
    let dsize = ZOPFLI_NUM_D as usize * CeilDiv(source.size as usize, ZOPFLI_NUM_D as usize);

    ZopfliCleanLZ77Store(dest);
    ZopfliInitLZ77Store(source.data, dest);

    dest.litlens = malloc(std::mem::size_of::<u16>() * source.size as usize) as *mut u16;
    dest.dists = malloc(std::mem::size_of::<u16>() * source.size as usize) as *mut u16;
    dest.pos = malloc(std::mem::size_of::<usize>() * source.size as usize) as *mut usize;
    dest.ll_symbol = malloc(std::mem::size_of::<u16>() * source.size as usize) as *mut u16;
    dest.d_symbol = malloc(std::mem::size_of::<u16>() * source.size as usize) as *mut u16;
    dest.ll_counts = malloc(std::mem::size_of::<usize>() * llsize) as *mut usize;
    dest.d_counts = malloc(std::mem::size_of::<usize>() * dsize) as *mut usize;

    if dest.litlens.is_null() || dest.dists.is_null() || dest.pos.is_null() || dest.ll_symbol.is_null() || dest.d_symbol.is_null() || dest.ll_counts.is_null() || dest.d_counts.is_null() {
        // The C code calls exit(-1), which is not ideal in Rust.
        // A panic is a bit more rusty, but for identical behavior we should probably abort.
        std::process::abort();
    }

    dest.size = source.size;

    ptr::copy_nonoverlapping(source.litlens, dest.litlens, source.size as usize);
    ptr::copy_nonoverlapping(source.dists, dest.dists, source.size as usize);
    ptr::copy_nonoverlapping(source.pos, dest.pos, source.size as usize);
    ptr::copy_nonoverlapping(source.ll_symbol, dest.ll_symbol, source.size as usize);
    ptr::copy_nonoverlapping(source.d_symbol, dest.d_symbol, source.size as usize);
    ptr::copy_nonoverlapping(source.ll_counts, dest.ll_counts, llsize);
    ptr::copy_nonoverlapping(source.d_counts, dest.d_counts, dsize);
}

use crate::util::{
    ZOPFLI_WINDOW_SIZE, ZOPFLI_WINDOW_MASK, ZOPFLI_MAX_MATCH,
    ZOPFLI_MIN_MATCH, ZOPFLI_MAX_CHAIN_HITS
};
use std::os::raw::{c_uchar, c_ushort};
use libc::c_uint;

unsafe fn TryGetFromLongestMatchCache(
    s: *mut ffi::ZopfliBlockState,
    pos: size_t,
    limit: *mut size_t,
    sublen: *mut c_ushort,
    distance: *mut c_ushort,
    length: *mut c_ushort,
) -> bool {
    let s = &mut *s;
    let lmcpos = pos - s.blockstart;

    let cache_available = !s.lmc.is_null()
        && ((*s.lmc).length.add(lmcpos).read() == 0 || (*s.lmc).dist.add(lmcpos).read() != 0);

    let limit_ok_for_cache = cache_available
        && (*limit == ZOPFLI_MAX_MATCH as usize
            || (*s.lmc).length.add(lmcpos).read() as usize <= *limit
            || (!sublen.is_null()
                && ffi::ZopfliMaxCachedSublen(
                    s.lmc,
                    lmcpos,
                    (*s.lmc).length.add(lmcpos).read() as usize,
                ) as usize
                    >= *limit));

    if !s.lmc.is_null() && limit_ok_for_cache && cache_available {
        if sublen.is_null()
            || (*s.lmc).length.add(lmcpos).read() as u32
                <= ffi::ZopfliMaxCachedSublen(
                    s.lmc,
                    lmcpos,
                    (*s.lmc).length.add(lmcpos).read() as size_t,
                )
        {
            *length = (*s.lmc).length.add(lmcpos).read();
            if *length as usize > *limit {
                *length = *limit as c_ushort;
            }
            if !sublen.is_null() {
                ffi::ZopfliCacheToSublen(s.lmc, lmcpos, *length as size_t, sublen);
                *distance = *sublen.add(*length as usize);
                if *limit == ZOPFLI_MAX_MATCH as usize && *length as usize >= ZOPFLI_MIN_MATCH as usize {
                    assert_eq!(*sublen.add(*length as usize), (*s.lmc).dist.add(lmcpos).read());
                }
            } else {
                *distance = (*s.lmc).dist.add(lmcpos).read();
            }
            return true;
        }
        *limit = (*s.lmc).length.add(lmcpos).read() as size_t;
    }

    false
}

unsafe fn StoreInLongestMatchCache(
    s: *mut ffi::ZopfliBlockState,
    pos: size_t,
    limit: size_t,
    sublen: *const c_ushort,
    distance: c_ushort,
    length: c_ushort,
) {
    let s = &mut *s;
    if s.lmc.is_null() {
        return;
    }

    let lmcpos = pos - s.blockstart;

    let cache_available = (*s.lmc).length.add(lmcpos).read() == 0 || (*s.lmc).dist.add(lmcpos).read() != 0;

    if limit == ZOPFLI_MAX_MATCH as usize && !sublen.is_null() && !cache_available {
        assert!((*s.lmc).length.add(lmcpos).read() == 1 && (*s.lmc).dist.add(lmcpos).read() == 0);
        (*s.lmc).dist.add(lmcpos).write(if (length as usize) < ZOPFLI_MIN_MATCH as usize { 0 } else { distance });
        (*s.lmc).length.add(lmcpos).write(if (length as usize) < ZOPFLI_MIN_MATCH as usize { 0 } else { length });
        assert!(!((*s.lmc).length.add(lmcpos).read() == 1 && (*s.lmc).dist.add(lmcpos).read() == 0));
        ffi::ZopfliSublenToCache(sublen, lmcpos, length as size_t, s.lmc);
    }
}

unsafe fn GetMatch(
    scan: *const c_uchar,
    match_: *const c_uchar,
    end: *const c_uchar,
    safe_end: *const c_uchar,
) -> *const c_uchar {
    let mut scan_ptr = scan;
    let mut match_ptr = match_;

    if std::mem::size_of::<usize>() == 8 {
        while (scan_ptr as usize) < (safe_end as usize)
            && std::ptr::read_unaligned(scan_ptr as *const usize)
                == std::ptr::read_unaligned(match_ptr as *const usize)
        {
            scan_ptr = scan_ptr.add(8);
            match_ptr = match_ptr.add(8);
        }
    } else if std::mem::size_of::<u32>() == 4 {
        while (scan_ptr as usize) < (safe_end as usize)
            && std::ptr::read_unaligned(scan_ptr as *const u32)
                == std::ptr::read_unaligned(match_ptr as *const u32)
        {
            scan_ptr = scan_ptr.add(4);
            match_ptr = match_ptr.add(4);
        }
    } else {
        while (scan_ptr as usize) < (safe_end as usize)
            && *scan_ptr == *match_ptr
            && *scan_ptr.add(1) == *match_ptr.add(1)
            && *scan_ptr.add(2) == *match_ptr.add(2)
            && *scan_ptr.add(3) == *match_ptr.add(3)
            && *scan_ptr.add(4) == *match_ptr.add(4)
            && *scan_ptr.add(5) == *match_ptr.add(5)
            && *scan_ptr.add(6) == *match_ptr.add(6)
            && *scan_ptr.add(7) == *match_ptr.add(7)
        {
            scan_ptr = scan_ptr.add(8);
            match_ptr = match_ptr.add(8);
        }
    }

    while (scan_ptr as usize) < (end as usize) && *scan_ptr == *match_ptr {
        scan_ptr = scan_ptr.add(1);
        match_ptr = match_ptr.add(1);
    }

    scan_ptr
}

pub unsafe fn ZopfliFindLongestMatch(
    s: *mut ffi::ZopfliBlockState,
    h: *const ffi::ZopfliHash,
    array: *const c_uchar,
    pos: size_t,
    size: size_t,
    limit: size_t,
    sublen: *mut c_ushort,
    distance: *mut c_ushort,
    length: *mut c_ushort,
) {
    let hpos = (pos & ZOPFLI_WINDOW_MASK as usize) as c_ushort;
    let mut bestdist: c_ushort = 0;
    let mut bestlength: c_ushort = 1;

    let mut limit = limit;
    let mut chain_counter = ZOPFLI_MAX_CHAIN_HITS;

    let mut dist;

    let mut hhead = (*h).head;
    let mut hprev = (*h).prev;
    let mut hhashval = (*h).hashval;
    let mut hval = (*h).val;

    if TryGetFromLongestMatchCache(s, pos, &mut limit, sublen, distance, length) {
        assert!(pos + *length as usize <= size);
        return;
    }

    assert!(limit <= ZOPFLI_MAX_MATCH as usize);
    assert!(limit >= ZOPFLI_MIN_MATCH as usize);
    assert!(pos < size);

    if size - pos < ZOPFLI_MIN_MATCH as usize {
        *length = 0;
        *distance = 0;
        return;
    }

    if pos + limit > size {
        limit = size - pos;
    }
    let arrayend = array.add(pos).add(limit);
    let arrayend_safe = arrayend.sub(8);

    assert!((hval as u32) < 65536);

    let pp = *hhead.add(hval as usize) as c_ushort;
    let mut p = *hprev.add(pp as usize);

    assert_eq!(pp, hpos);

    dist = if p < pp { pp - p } else { (ZOPFLI_WINDOW_SIZE as c_ushort - p) + pp };

    while (dist as usize) < ZOPFLI_WINDOW_SIZE {
        let mut currentlength: c_ushort = 0;

        assert!((p as usize) < ZOPFLI_WINDOW_SIZE);
        assert_eq!(*hhashval.add(p as usize), hval);
        assert_eq!(*hhashval.add(p as usize), hval);

        if dist > 0 {
            assert!(pos < size);
            assert!(dist as usize <= pos);
            let mut scan = array.add(pos);
            let mut match_ = array.add(pos - dist as usize);

            if pos + bestlength as usize >= size
                || *scan.add(bestlength as usize) == *match_.add(bestlength as usize)
            {
                let same0 = *(*h).same.add(pos & ZOPFLI_WINDOW_MASK as usize);
                if same0 > 2 && *scan == *match_ {
                    let same1 = *(*h).same.add((pos - dist as usize) & ZOPFLI_WINDOW_MASK as usize);
                    let mut same = if same0 < same1 { same0 } else { same1 };
                    if same as usize > limit {
                        same = limit as c_ushort;
                    }
                    scan = scan.add(same as usize);
                    match_ = match_.add(same as usize);
                }

                let scan_end = GetMatch(scan, match_, arrayend, arrayend_safe);
                currentlength = (scan_end as usize - (array.add(pos) as usize)) as c_ushort;
            }

            if currentlength > bestlength {
                if !sublen.is_null() {
                    for j in (bestlength + 1)..=currentlength {
                        *sublen.add(j as usize) = dist;
                    }
                }
                bestdist = dist;
                bestlength = currentlength;
                if currentlength as usize >= limit {
                    break;
                }
            }
        }

        if hhead != (*h).head2
            && bestlength as u16 >= *(*h).same.add(hpos as usize)
            && (*h).val2 == *(*h).hashval2.add(p as usize)
        {
            hhead = (*h).head2;
            hprev = (*h).prev2;
            hhashval = (*h).hashval2;
            hval = (*h).val2;
        }

        let pp_new = p;
        p = *hprev.add(p as usize);
        if p == pp_new {
            break;
        }

        dist += if p < pp_new { pp_new - p } else { (ZOPFLI_WINDOW_SIZE as c_ushort - p) + pp_new };
        
        chain_counter -= 1;
        if chain_counter <= 0 {
            break;
        }
    }

    StoreInLongestMatchCache(s, pos, limit, sublen, bestdist, bestlength);

    assert!(bestlength as usize <= limit);

    *distance = bestdist;
    *length = bestlength;
    assert!(pos + *length as usize <= size);
}

fn GetLengthScore(length: i32, distance: i32) -> i32 {
    /*
    At 1024, the distance uses 9+ extra bits and this seems to be the sweet spot
    on tested files.
    */
    if distance > 1024 {
        length - 1
    } else {
        length
    }
}

pub unsafe fn ZopfliLZ77Greedy(
    s: *mut ffi::ZopfliBlockState,
    r#in: *const c_uchar,
    instart: size_t,
    inend: size_t,
    store: *mut ffi::ZopfliLZ77Store,
    h: *mut ffi::ZopfliHash,
) {
    let in_slice = std::slice::from_raw_parts(r#in, inend);
    let mut i = instart;
    let mut leng: c_ushort;
    let mut dist: c_ushort;
    let mut lengthscore: i32;
    let windowstart = if instart > ZOPFLI_WINDOW_SIZE {
        instart - ZOPFLI_WINDOW_SIZE
    } else {
        0
    };
    let mut dummysublen = [0u16; 259];

    let mut prev_length = 0;
    let mut prev_match = 0;
    let mut prevlengthscore;
    let mut match_available = false;

    if instart == inend {
        return;
    }

    ffi::ZopfliResetHash(ZOPFLI_WINDOW_SIZE, h);
    ffi::ZopfliWarmupHash(r#in, windowstart, inend, h);
    for j in windowstart..instart {
        ffi::ZopfliUpdateHash(r#in, j, inend, h);
    }

    while i < inend {
        ffi::ZopfliUpdateHash(r#in, i, inend, h);

        leng = 0;
        dist = 0;
        ZopfliFindLongestMatch(
            s,
            h,
            r#in,
            i,
            inend,
            ZOPFLI_MAX_MATCH as size_t,
            dummysublen.as_mut_ptr(),
            &mut dist,
            &mut leng,
        );
        lengthscore = GetLengthScore(leng as i32, dist as i32);

        if crate::util::ZOPFLI_LAZY_MATCHING {
            prevlengthscore = GetLengthScore(prev_length as i32, prev_match as i32);
            if match_available {
                match_available = false;
                if lengthscore > prevlengthscore + 1 {
                    ZopfliStoreLitLenDist((in_slice[i - 1]) as u16, 0, i - 1, store);
                    if lengthscore >= ZOPFLI_MIN_MATCH as i32 && (leng as usize) < ZOPFLI_MAX_MATCH {
                        match_available = true;
                        prev_length = leng;
                        prev_match = dist;
                        i += 1;
                        continue;
                    }
                } else {
                    leng = prev_length;
                    dist = prev_match;
                    ZopfliVerifyLenDist(in_slice, i - 1, dist, leng);
                    ZopfliStoreLitLenDist(leng, dist, i - 1, store);
                    for j in 2..leng as usize {
                        assert!(i < inend);
                        i += 1;
                        ffi::ZopfliUpdateHash(r#in, i, inend, h);
                    }
                    i += 1;
                    continue;
                }
            } else if lengthscore >= ZOPFLI_MIN_MATCH as i32 && (leng as usize) < ZOPFLI_MAX_MATCH {
                match_available = true;
                prev_length = leng;
                prev_match = dist;
                i += 1;
                continue;
            }
        }

        if lengthscore >= ZOPFLI_MIN_MATCH as i32 {
            ZopfliVerifyLenDist(in_slice, i, dist, leng);
            ZopfliStoreLitLenDist(leng, dist, i, store);
        } else {
            leng = 1;
            ZopfliStoreLitLenDist((in_slice[i]) as u16, 0, i, store);
        }
        for j in 1..leng as usize {
            assert!(i < inend);
            i += 1;
            ffi::ZopfliUpdateHash(r#in, i, inend, h);
        }
        i += 1;
    }
}
