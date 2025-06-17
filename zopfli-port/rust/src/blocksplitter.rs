use std::ptr;

use libc::{c_uchar, c_void, size_t};

use crate::deflate::ZopfliCalculateBlockSizeAutoType;
use crate::ffi;
use crate::ffi::ZopfliLZ77Store;
use crate::util;
use crate::lz77::{ZopfliInitLZ77Store, ZopfliCleanLZ77Store, ZopfliInitBlockState, ZopfliCleanBlockState, ZopfliLZ77Greedy};
use crate::hash::{ZopfliAllocHash, ZopfliCleanHash};

type FindMinimumFun = unsafe extern "C" fn(size_t, *mut c_void) -> f64;

// TODO(J-F-C): `FindMinimum` is defined in `blocksplitter.c` but there's a reference to it in `squeeze.c` as well
// See https://github.com/google/zopfli/blob/1c32b695738ce7a812804e2a912b79a756d79079/src/zopfli/squeeze.c#L248
// and https://github.com/google/zopfli/blob/1c32b695738ce7a812804e2a912b79a756d79079/src/zopfli/blocksplitter.c#L43
#[no_mangle]
pub extern "C" fn FindMinimum(
    f: Option<FindMinimumFun>,
    context: *mut c_void,
    start: size_t,
    end: size_t,
    smallest: *mut f64,
) -> size_t {
    let f = f.unwrap();
    if end - start < 1024 {
        let mut best = util::ZOPFLI_LARGE_FLOAT;
        let mut result = start;
        for i in start..end {
            let v = unsafe { f(i, context) };
            if v < best {
                best = v;
                result = i;
            }
        }
        unsafe {
            *smallest = best;
        }
        result
    } else {
        const NUM: usize = 9;
        let mut p = [0; NUM];
        let mut vp = [0.0; NUM];
        let mut besti;
        let mut best;
        let mut lastbest = util::ZOPFLI_LARGE_FLOAT;
        let mut pos = start;

        let mut current_start = start;
        let mut current_end = end;

        loop {
            if current_end - current_start <= NUM {
                break;
            }

            for i in 0..NUM {
                p[i] = current_start + (i + 1) * ((current_end - current_start) / (NUM + 1));
                vp[i] = unsafe { f(p[i], context) };
            }

            besti = 0;
            best = vp[0];
            for i in 1..NUM {
                if vp[i] < best {
                    best = vp[i];
                    besti = i;
                }
            }

            if best > lastbest {
                break;
            }

            current_start = if besti == 0 {
                current_start
            } else {
                p[besti - 1]
            };
            current_end = if besti == NUM - 1 {
                current_end
            } else {
                p[besti + 1]
            };

            pos = p[besti];
            lastbest = best;
        }
        unsafe {
            *smallest = lastbest;
        }
        pos
    }
}

unsafe fn EstimateCost(lz77: &ZopfliLZ77Store, lstart: size_t, lend: size_t) -> f64 {
    ZopfliCalculateBlockSizeAutoType(lz77, lstart, lend)
}

#[repr(C)]
struct SplitCostContext<'a> {
    lz77: &'a ZopfliLZ77Store,
    start: size_t,
    end: size_t,
}

unsafe extern "C" fn SplitCost(i: size_t, context: *mut c_void) -> f64 {
    let c = &*(context as *const SplitCostContext);
    EstimateCost(c.lz77, c.start, i) + EstimateCost(c.lz77, i, c.end)
}

fn AddSorted(value: size_t, out: &mut Vec<size_t>) {
    out.push(value);
    out.sort_unstable();
}

unsafe fn PrintBlockSplitPoints(
    lz77: &ZopfliLZ77Store,
    lz77splitpoints: &Vec<size_t>,
) {
    let mut splitpoints: Vec<size_t> = Vec::new();
    let mut pos: size_t = 0;

    if !lz77splitpoints.is_empty() {
        let lz77_litlens = std::slice::from_raw_parts(lz77.litlens, lz77.size);
        let lz77_dists = std::slice::from_raw_parts(lz77.dists, lz77.size);
        let mut current_split_point = 0;

        for i in 0..lz77.size {
            let length = if lz77_dists[i] == 0 {
                1
            } else {
                lz77_litlens[i] as size_t
            };
            if current_split_point < lz77splitpoints.len() && lz77splitpoints[current_split_point] == i {
                splitpoints.push(pos);
                current_split_point += 1;
            }
            pos += length;
        }
    }

    assert_eq!(splitpoints.len(), lz77splitpoints.len());

    eprint!("block split points: ");
    for point in &splitpoints {
        eprint!("{} ", point);
    }
    eprint!("(hex:");
    for point in &splitpoints {
        eprint!(" {:x}", point);
    }
    eprintln!(")");
}

fn FindLargestSplittableBlock(
    lz77size: size_t,
    done: &[u8],
    splitpoints: &Vec<size_t>,
    lstart: &mut size_t,
    lend: &mut size_t,
) -> bool {
    let mut longest = 0;
    let mut found = false;
    let mut last_split = 0;

    for &splitpoint in splitpoints {
        if done[last_split] == 0 && splitpoint - last_split > longest {
            *lstart = last_split;
            *lend = splitpoint;
            found = true;
            longest = splitpoint - last_split;
        }
        last_split = splitpoint;
    }

    if done[last_split] == 0 && lz77size - 1 - last_split > longest {
        *lstart = last_split;
        *lend = lz77size - 1;
        found = true;
    }

    found
}

pub unsafe fn ZopfliBlockSplitLZ77(
    options: *const ffi::ZopfliOptions,
    lz77: *const ffi::ZopfliLZ77Store,
    maxblocks: size_t,
    splitpoints: *mut *mut size_t,
    npoints: *mut size_t,
) {
    let lz77 = &*lz77;
    let options = &*options;

    if lz77.size < 10 {
        *splitpoints = std::ptr::null_mut();
        *npoints = 0;
        return;
    }

    let mut done: Vec<u8> = vec![0; lz77.size];
    let mut c_splitpoints: *mut size_t = std::ptr::null_mut();
    let mut c_splitpoints_size: size_t = 0;
    let mut c_splitpoints_capacity: size_t = 0;

    let mut lstart = 0;
    let mut lend = lz77.size;

    let mut numblocks = 1;

    loop {
        if maxblocks > 0 && numblocks >= maxblocks {
            break;
        }

        let mut c = SplitCostContext {
            lz77,
            start: lstart,
            end: lend,
        };

        assert!(lstart < lend);
        let mut splitcost = 0.0;
        let llpos = FindMinimum(
            Some(SplitCost),
            &mut c as *mut _ as *mut c_void,
            lstart + 1,
            lend,
            &mut splitcost,
        );

        assert!(llpos > lstart);
        assert!(llpos < lend);

        let origcost = EstimateCost(lz77, lstart, lend);

        if splitcost > origcost || llpos == lstart + 1 || llpos == lend {
            done[lstart] = 1;
        } else {
            // Add to C-style array using libc allocation
            if c_splitpoints_size >= c_splitpoints_capacity {
                let new_capacity = if c_splitpoints_capacity == 0 { 1 } else { c_splitpoints_capacity * 2 };
                let new_ptr = if c_splitpoints.is_null() {
                    libc::malloc(new_capacity * std::mem::size_of::<size_t>())
                } else {
                    libc::realloc(c_splitpoints as *mut c_void, new_capacity * std::mem::size_of::<size_t>())
                };
                if new_ptr.is_null() {
                    panic!("Out of memory");
                }
                c_splitpoints = new_ptr as *mut size_t;
                c_splitpoints_capacity = new_capacity;
            }
            
            // Insert in sorted order
            let mut insert_pos = c_splitpoints_size;
            for i in 0..c_splitpoints_size {
                if *c_splitpoints.add(i) > llpos {
                    insert_pos = i;
                    break;
                }
            }
            
            // Shift elements to make room
            if insert_pos < c_splitpoints_size {
                libc::memmove(
                    c_splitpoints.add(insert_pos + 1) as *mut c_void,
                    c_splitpoints.add(insert_pos) as *const c_void,
                    (c_splitpoints_size - insert_pos) * std::mem::size_of::<size_t>(),
                );
            }
            
            *c_splitpoints.add(insert_pos) = llpos;
            c_splitpoints_size += 1;
            numblocks += 1;
        }

        if !FindLargestSplittableBlock(
            lz77.size,
            &done,
            &if c_splitpoints_size > 0 { 
                std::slice::from_raw_parts(c_splitpoints, c_splitpoints_size).to_vec()
            } else { 
                Vec::new() 
            },
            &mut lstart,
            &mut lend,
        ) {
            break;
        }

        if lend - lstart < 10 {
            break;
        }
    }

    if options.verbose > 0 && c_splitpoints_size > 0 {
        let splitpoints_vec = std::slice::from_raw_parts(c_splitpoints, c_splitpoints_size).to_vec();
        PrintBlockSplitPoints(lz77, &splitpoints_vec);
    }

    *npoints = c_splitpoints_size;
    *splitpoints = c_splitpoints;
}

pub unsafe fn ZopfliBlockSplit(
    options: *const ffi::ZopfliOptions,
    input: *const c_uchar,
    instart: size_t,
    inend: size_t,
    maxblocks: size_t,
    splitpoints: *mut *mut size_t,
    npoints: *mut size_t,
) {
    let mut pos: size_t;
    let mut s = std::mem::MaybeUninit::<ffi::ZopfliBlockState>::uninit();
    let mut lz77splitpoints: *mut size_t = std::ptr::null_mut();
    let mut nlz77points: size_t = 0;
    let mut store = std::mem::MaybeUninit::<ffi::ZopfliLZ77Store>::uninit();
    let mut hash = std::mem::MaybeUninit::<ffi::ZopfliHash>::uninit();
    
    let s = s.as_mut_ptr();
    let store = store.as_mut_ptr();
    let hash = hash.as_mut_ptr();

    ZopfliInitLZ77Store(input, store);
    ZopfliInitBlockState(options, instart, inend, 0, s);
    ZopfliAllocHash(util::ZOPFLI_WINDOW_SIZE, hash);

    *npoints = 0;
    *splitpoints = std::ptr::null_mut();

    // Unintuitively, Using a simple LZ77 method here instead of ZopfliLZ77Optimal
    // results in better blocks.
    ZopfliLZ77Greedy(s, input, instart, inend, store, hash);

    ZopfliBlockSplitLZ77(options, store, maxblocks, &mut lz77splitpoints, &mut nlz77points);

    // Convert LZ77 positions to positions in the uncompressed input.
    pos = instart;
    if nlz77points > 0 {
        let store_ref = &*store;
        let litlens = std::slice::from_raw_parts(store_ref.litlens, store_ref.size);
        let dists = std::slice::from_raw_parts(store_ref.dists, store_ref.size);
        let lz77splitpoints_slice = std::slice::from_raw_parts(lz77splitpoints, nlz77points);
        
        for i in 0..store_ref.size {
            let length = if dists[i] == 0 { 1 } else { litlens[i] as size_t };
            if *npoints < nlz77points && lz77splitpoints_slice[*npoints] == i {
                util::ZOPFLI_APPEND_DATA(pos, &mut *splitpoints, &mut *npoints);
                if *npoints == nlz77points {
                    break;
                }
            }
            pos += length;
        }
    }
    assert_eq!(*npoints, nlz77points);

    libc::free(lz77splitpoints as *mut c_void);
    ZopfliCleanBlockState(s);
    ZopfliCleanLZ77Store(store);
    ZopfliCleanHash(hash);
}

pub fn ZopfliBlockSplitSimple(
    _in: *const c_uchar,
    instart: size_t,
    inend: size_t,
    blocksize: size_t,
    splitpoints: *mut *mut size_t,
    npoints: *mut size_t,
) {
    // The C function is "simple" and doesn't actually use the input data,
    // so we don't need to construct a slice for it.
    // We just need to honor the instart, inend, and blocksize parameters.

    // A more Rusty way to do this without unsafe code in a loop.
    let mut points = Vec::new();
    let mut i = instart;
    while i < inend {
        points.push(i);
        i += blocksize;
    }

    // Now, give ownership of the data to the C code.
    unsafe {
        // Leaking the memory, so C code is responsible for freeing it.
        points.shrink_to_fit();
        let (ptr, len) = (points.as_mut_ptr(), points.len());
        std::mem::forget(points);
        *splitpoints = ptr;
        *npoints = len;
    }
}
