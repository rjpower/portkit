use libc::size_t;

use crate::ffi::{
    ZopfliBlockState, ZopfliHash, ZopfliLZ77Store, ZopfliOptions 
};
use crate::hash::{ZopfliAllocHash, ZopfliCleanHash, ZopfliResetHash, ZopfliUpdateHash, ZopfliWarmupHash};
use crate::lz77::{ZopfliFindLongestMatch, ZopfliStoreLitLenDist, ZopfliVerifyLenDist, ZopfliLZ77Greedy, ZopfliCopyLZ77Store, ZopfliCleanLZ77Store, ZopfliInitLZ77Store };
use crate::deflate::ZopfliCalculateBlockSize;
use crate::tree::ZopfliCalculateEntropy;
use crate::symbols::{
    ZopfliGetDistExtraBits, ZopfliGetDistSymbol, ZopfliGetLengthExtraBits, ZopfliGetLengthSymbol,
};
use crate::util::{
    ZOPFLI_LARGE_FLOAT, ZOPFLI_MAX_MATCH, ZOPFLI_MIN_MATCH, ZOPFLI_WINDOW_SIZE, ZOPFLI_NUM_LL, ZOPFLI_NUM_D,
};

use std::os::raw::{c_int, c_uint, c_ushort, c_void};

#[derive(Clone, Copy, Debug)]
struct SymbolStats {
    litlens: [size_t; ZOPFLI_NUM_LL],
    dists: [size_t; ZOPFLI_NUM_D],
    ll_symbols: [f64; ZOPFLI_NUM_LL],
    d_symbols: [f64; ZOPFLI_NUM_D],
}

impl Default for SymbolStats {
    fn default() -> Self {
        Self::new()
    }
}

impl SymbolStats {
    fn new() -> Self {
        SymbolStats {
            litlens: [0; ZOPFLI_NUM_LL],
            dists: [0; ZOPFLI_NUM_D],
            ll_symbols: [0.0; ZOPFLI_NUM_LL],
            d_symbols: [0.0; ZOPFLI_NUM_D],
        }
    }

    fn clear_freqs(&mut self) {
        self.litlens = [0; ZOPFLI_NUM_LL];
        self.dists = [0; ZOPFLI_NUM_D];
    }
}

fn add_weighed_stat_freqs(
    stats1: &SymbolStats,
    w1: f64,
    stats2: &SymbolStats,
    w2: f64,
    result: &mut SymbolStats,
) {
    for i in 0..ZOPFLI_NUM_LL {
        result.litlens[i] = (stats1.litlens[i] as f64 * w1 + stats2.litlens[i] as f64 * w2) as size_t;
    }
    for i in 0..ZOPFLI_NUM_D {
        result.dists[i] = (stats1.dists[i] as f64 * w1 + stats2.dists[i] as f64 * w2) as size_t;
    }
    result.litlens[256] = 1;
}

#[derive(Clone, Copy)]
struct RanState {
    m_w: u32,
    m_z: u32,
}

impl RanState {
    fn new() -> Self {
        RanState { m_w: 1, m_z: 2 }
    }

    fn ran(&mut self) -> u32 {
        self.m_z = 36969 * (self.m_z & 65535) + (self.m_z >> 16);
        self.m_w = 18000 * (self.m_w & 65535) + (self.m_w >> 16);
        (self.m_z << 16).wrapping_add(self.m_w)
    }
}

fn randomize_freqs(state: &mut RanState, freqs: &mut [size_t]) {
    let n = freqs.len();
    for i in 0..n {
        if (state.ran() >> 4) % 3 == 0 {
            freqs[i] = freqs[(state.ran() as usize) % n];
        }
    }
}

fn randomize_stat_freqs(state: &mut RanState, stats: &mut SymbolStats) {
    randomize_freqs(state, &mut stats.litlens);
    randomize_freqs(state, &mut stats.dists);
    stats.litlens[256] = 1;
}

fn calculate_statistics(stats: &mut SymbolStats) {
    ZopfliCalculateEntropy(stats.litlens.as_ptr(), ZOPFLI_NUM_LL, stats.ll_symbols.as_mut_ptr());
    ZopfliCalculateEntropy(stats.dists.as_ptr(), ZOPFLI_NUM_D, stats.d_symbols.as_mut_ptr());
}

unsafe fn get_statistics(store: *const ZopfliLZ77Store, stats: &mut SymbolStats) {
    if (*store).size > 0 {
        let store_slice = std::slice::from_raw_parts((*store).litlens, (*store).size);
        let dists_slice = std::slice::from_raw_parts((*store).dists, (*store).size);
        for i in 0..(*store).size {
            if dists_slice[i] == 0 {
                stats.litlens[store_slice[i] as usize] += 1;
            } else {
                stats.litlens[ZopfliGetLengthSymbol(store_slice[i] as c_int) as usize] += 1;
                stats.dists[ZopfliGetDistSymbol(dists_slice[i] as c_int) as usize] += 1;
            }
        }
    }
    stats.litlens[256] = 1;

    calculate_statistics(stats);
}

type CostModelFun = unsafe extern "C" fn(litlen: c_uint, dist: c_uint, context: *mut c_void) -> f64;

#[no_mangle]
pub unsafe extern "C" fn GetCostFixed(litlen: c_uint, dist: c_uint, _unused: *mut c_void) -> f64 {
    if dist == 0 {
        if litlen <= 143 {
            8.0
        } else {
            9.0
        }
    } else {
        let dbits = ZopfliGetDistExtraBits(dist as c_int);
        let lbits = ZopfliGetLengthExtraBits(litlen as c_int);
        let lsym = ZopfliGetLengthSymbol(litlen as c_int);
        let mut cost = 0;
        if lsym <= 279 {
            cost += 7;
        } else {
            cost += 8;
        }
        cost += 5;
        (cost + dbits + lbits) as f64
    }
}

unsafe extern "C" fn get_cost_stat(litlen: u32, dist: u32, context: *mut c_void) -> f64 {
    let stats = &*(context as *const SymbolStats);
    if dist == 0 {
        stats.ll_symbols[litlen as usize]
    } else {
        let lsym = ZopfliGetLengthSymbol(litlen as i32);
        let lbits = ZopfliGetLengthExtraBits(litlen as i32);
        let dsym = ZopfliGetDistSymbol(dist as i32);
        let dbits = ZopfliGetDistExtraBits(dist as i32);
        lbits as f64 + dbits as f64 + stats.ll_symbols[lsym as usize] + stats.d_symbols[dsym as usize]
    }
}

unsafe fn GetCostModelMinCost(costmodel: CostModelFun, costcontext: *mut c_void) -> f64 {
    let mut mincost;
    let mut bestlength = 0;
    let mut bestdist = 0;

    static DSMBOLS: [c_int; 30] = [
        1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025,
        1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577,
    ];

    mincost = ZOPFLI_LARGE_FLOAT as f64;
    for i in 3..259 {
        let c = costmodel(i, 1, costcontext);
        if c < mincost {
            bestlength = i;
            mincost = c;
        }
    }

    mincost = ZOPFLI_LARGE_FLOAT as f64;
    for &dsymbol in &DSMBOLS {
        let c = costmodel(3, dsymbol as u32, costcontext);
        if c < mincost {
            bestdist = dsymbol as u32;
            mincost = c;
        }
    }

    costmodel(bestlength, bestdist, costcontext)
}

unsafe fn GetBestLengths(
    s: *mut ZopfliBlockState,
    r#in: *const u8,
    instart: size_t,
    inend: size_t,
    costmodel: CostModelFun,
    costcontext: *mut c_void,
    length_array: *mut c_ushort,
    h: *mut ZopfliHash,
    costs: *mut f32,
) -> f64 {
    let blocksize = inend - instart;
    let windowstart = if instart > ZOPFLI_WINDOW_SIZE {
        instart - ZOPFLI_WINDOW_SIZE
    } else {
        0
    };

    if instart == inend {
        return 0.0;
    }

    ZopfliResetHash(ZOPFLI_WINDOW_SIZE, h);
    ZopfliWarmupHash(r#in, windowstart, inend, h);
    for i in windowstart..instart {
        ZopfliUpdateHash(r#in, i, inend, h);
    }

    let costs_slice = std::slice::from_raw_parts_mut(costs, blocksize + 1);
    costs_slice[1..].fill(ZOPFLI_LARGE_FLOAT as f32);
    costs_slice[0] = 0.0;

    let length_array_slice = std::slice::from_raw_parts_mut(length_array, blocksize + 1);
    length_array_slice[0] = 0;

    let mincost = GetCostModelMinCost(costmodel, costcontext);

    for i in instart..inend {
        let j = i - instart;
        ZopfliUpdateHash(r#in, i, inend, h);

        let mut sublen: [u16; 259] = [0; 259];
        let mut dist: u16 = 0;
        let mut leng: u16 = 0;
        ZopfliFindLongestMatch(
            s,
            h,
            r#in,
            i,
            inend,
            ZOPFLI_MAX_MATCH as size_t,
            sublen.as_mut_ptr(),
            &mut dist,
            &mut leng,
        );

        if i + 1 <= inend {
            let new_cost = costmodel(*r#in.add(i) as c_uint, 0, costcontext) + costs_slice[j] as f64;
            if new_cost < costs_slice[j + 1] as f64 {
                costs_slice[j + 1] = new_cost as f32;
                length_array_slice[j + 1] = 1;
            }
        }

        let kend = std::cmp::min(leng as size_t, inend - i);
        let mincostaddcostj = mincost + costs_slice[j] as f64;

        for k in 3..=kend {
            if costs_slice[j + k] as f64 <= mincostaddcostj {
                continue;
            }

            let new_cost = costmodel(k as c_uint, sublen[k] as c_uint, costcontext) + costs_slice[j] as f64;
            if new_cost < costs_slice[j + k] as f64 {
                costs_slice[j + k] = new_cost as f32;
                length_array_slice[j + k] = k as c_ushort;
            }
        }
    }
    costs_slice[blocksize] as f64
}

unsafe fn TraceBackwards(size: size_t, length_array: *const c_ushort, path: &mut Vec<c_ushort>) {
    let length_array_slice = std::slice::from_raw_parts(length_array, size + 1);
    let mut index = size;
    if size == 0 {
        return;
    }
    loop {
        let length = length_array_slice[index];
        path.push(length);
        assert!(length as size_t <= index);
        assert!(length <= ZOPFLI_MAX_MATCH as c_ushort);
        assert!(length != 0);
        index -= length as size_t;
        if index == 0 {
            break;
        }
    }
    path.reverse();
}

unsafe fn zopfli_verify_len_dist_wrapper(
    data: *const u8,
    datasize: size_t,
    pos: size_t,
    dist: c_ushort,
    length: c_ushort,
) {
    let data_slice = std::slice::from_raw_parts(data, datasize);
    ZopfliVerifyLenDist(data_slice, pos, dist, length);
}

unsafe fn FollowPath(
    s: *mut ZopfliBlockState,
    r#in: *const u8,
    instart: size_t,
    inend: size_t,
    path: &[c_ushort],
    store: *mut ZopfliLZ77Store,
    h: *mut ZopfliHash,
) {
    let windowstart = if instart > ZOPFLI_WINDOW_SIZE {
        instart - ZOPFLI_WINDOW_SIZE
    } else {
        0
    };

    if instart == inend {
        return;
    }

    ZopfliResetHash(ZOPFLI_WINDOW_SIZE, h);
    ZopfliWarmupHash(r#in, windowstart, inend, h);
    for i in windowstart..instart {
        ZopfliUpdateHash(r#in, i, inend, h);
    }

    let mut pos = instart;
    for &length in path {
        ZopfliUpdateHash(r#in, pos, inend, h);

        if length >= ZOPFLI_MIN_MATCH as c_ushort {
            let mut dummy_length: u16 = 0;
            let mut dist: u16 = 0;
            ZopfliFindLongestMatch(
                s,
                h,
                r#in,
                pos,
                inend,
                length as size_t,
                std::ptr::null_mut(),
                &mut dist,
                &mut dummy_length,
            );
            zopfli_verify_len_dist_wrapper(r#in, inend, pos, dist, length);
            ZopfliStoreLitLenDist(length, dist, pos, store);
        } else {
            ZopfliStoreLitLenDist(*r#in.add(pos) as c_ushort, 0, pos, store);
        }

        for j in 1..length {
            ZopfliUpdateHash(r#in, pos + j as size_t, inend, h);
        }
        pos += length as size_t;
    }
}

unsafe fn LZ77OptimalRun(
    s: *mut ZopfliBlockState,
    r#in: *const u8,
    instart: size_t,
    inend: size_t,
    path: &mut Vec<c_ushort>,
    length_array: *mut c_ushort,
    costmodel: CostModelFun,
    costcontext: *mut c_void,
    store: *mut ZopfliLZ77Store,
    h: *mut ZopfliHash,
    costs: *mut f32,
) -> f64 {
    let cost = GetBestLengths(
        s,
        r#in,
        instart,
        inend,
        costmodel,
        costcontext,
        length_array,
        h,
        costs,
    );
    path.clear();
    TraceBackwards(inend - instart, length_array, path);
    FollowPath(s, r#in, instart, inend, path, store, h);
    cost
}

pub unsafe fn ZopfliLZ77Optimal(
    s: *mut ZopfliBlockState,
    in_data: *const u8,
    instart: size_t,
    inend: size_t,
    numiterations: c_int,
    store: *mut ZopfliLZ77Store,
) {
    if inend - instart == 0 {
        return;
    }
    let blocksize = inend - instart;
    let mut length_array = vec![0u16; blocksize + 1];
    let mut path: Vec<c_ushort> = vec![0; blocksize + 1];
    let mut currentstore: ZopfliLZ77Store = std::mem::zeroed();
    let mut h = Box::new(std::mem::zeroed::<ZopfliHash>());

    let mut stats = SymbolStats::new();
    let mut beststats = SymbolStats::new();
    let mut laststats;

    let mut costs = vec![0.0f32; blocksize + 1];
    let mut bestcost = ZOPFLI_LARGE_FLOAT;
    let mut lastcost = 0.0;

    let mut ran_state = RanState::new();
    let mut lastrandomstep = -1;

    ZopfliInitLZ77Store(in_data, &mut currentstore);
    ZopfliAllocHash(ZOPFLI_WINDOW_SIZE, &mut *h);

    ZopfliLZ77Greedy(s, in_data, instart, inend, &mut currentstore, &mut *h);
    get_statistics(&currentstore, &mut stats);
    calculate_statistics(&mut stats);

    for i in 0..numiterations {
        ZopfliCleanLZ77Store(&mut currentstore);
        ZopfliInitLZ77Store(in_data, &mut currentstore);
        LZ77OptimalRun(
            s,
            in_data,
            instart,
            inend,
            &mut path,
            length_array.as_mut_ptr(),
            get_cost_stat,
            &mut stats as *mut _ as *mut c_void,
            &mut currentstore,
            &mut *h,
            costs.as_mut_ptr(),
        );
        let cost = ZopfliCalculateBlockSize(&currentstore, 0, currentstore.size, 2);

        if (*(*s).options).verbose_more != 0 || ((*(*s).options).verbose != 0 && cost < bestcost) {
            eprintln!("Iteration {}: {} bit", i, cost as c_int);
        }

        if cost < bestcost {
            ZopfliCopyLZ77Store(&currentstore, store);
            beststats = stats;
            bestcost = cost;
        }
        laststats = stats;
        stats.clear_freqs();
        get_statistics(&currentstore, &mut stats);

        if lastrandomstep != -1 {
            let mut new_stats = SymbolStats::new();
            add_weighed_stat_freqs(&stats, 1.0, &laststats, 0.5, &mut new_stats);
            stats = new_stats;
            calculate_statistics(&mut stats);
        }
        if i > 5 && cost == lastcost {
            stats = beststats;
            randomize_stat_freqs(&mut ran_state, &mut stats);
            calculate_statistics(&mut stats);
            lastrandomstep = i;
        }
        lastcost = cost;
    }
    ZopfliCleanLZ77Store(&mut currentstore);
    ZopfliCleanHash(&mut *h);
}


pub unsafe fn ZopfliLZ77OptimalFixed(
    s: *mut ZopfliBlockState,
    r#in: *const u8,
    instart: size_t,
    inend: size_t,
    store: *mut ZopfliLZ77Store,
) {
    let blocksize = inend - instart;
    let mut length_array = vec![0u16; blocksize + 1];
    let mut path: Vec<c_ushort> = Vec::new();
    let mut hash = std::mem::zeroed();
    let mut costs = vec![0.0f32; blocksize + 1];

    ZopfliAllocHash(ZOPFLI_WINDOW_SIZE, &mut hash);

    (*s).blockstart = instart;
    (*s).blockend = inend;

    LZ77OptimalRun(
        s,
        r#in,
        instart,
        inend,
        &mut path,
        length_array.as_mut_ptr(),
        GetCostFixed,
        std::ptr::null_mut(),
        store,
        &mut hash,
        costs.as_mut_ptr(),
    );

    ZopfliCleanHash(&mut hash);
}
