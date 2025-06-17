use std::os::raw::{c_double, c_int, c_uchar, c_uint, c_ushort};
use libc::size_t;

#[repr(C)]
#[derive(Debug, Default)]
pub struct ZopfliLZ77Store {
    pub litlens: *mut c_ushort,
    pub dists: *mut c_ushort,
    pub size: size_t,
    pub data: *const c_uchar,
    pub pos: *mut size_t,
    pub ll_symbol: *mut c_ushort,
    pub d_symbol: *mut c_ushort,
    pub ll_counts: *mut size_t,
    pub d_counts: *mut size_t,
}


#[repr(C)]
pub struct ZopfliLongestMatchCache {
    pub length: *mut c_ushort,
    pub dist: *mut c_ushort,
    pub sublen: *mut c_uchar,
}


#[repr(C)]
#[derive(PartialEq, Debug, Copy, Clone)]
pub struct ZopfliOptions {
    pub verbose: c_int,
    pub verbose_more: c_int,
    pub numiterations: c_int,
    pub blocksplitting: c_int,
    pub blocksplittinglast: c_int,
    pub blocksplittingmax: c_int,
}


pub type ZopfliFormat = c_uint;

#[repr(C)]
pub struct ZopfliHash {
    pub head: *mut ::std::os::raw::c_int,
    pub prev: *mut ::std::os::raw::c_ushort,
    pub hashval: *mut ::std::os::raw::c_int,
    pub val: ::std::os::raw::c_int,
    pub head2: *mut ::std::os::raw::c_int,
    pub prev2: *mut ::std::os::raw::c_ushort,
    pub hashval2: *mut ::std::os::raw::c_int,
    pub val2: ::std::os::raw::c_int,
    pub same: *mut ::std::os::raw::c_ushort,
}


#[repr(C)]
#[derive(Debug, Copy, Clone)]
pub struct ZopfliBlockState {
    pub options: *const ZopfliOptions,
    pub lmc: *mut ZopfliLongestMatchCache,
    pub blockstart: size_t,
    pub blockend: size_t,
}

extern "C" {
    pub fn AddDynamicTree(
        ll_lengths: *const ::std::os::raw::c_uint,
        d_lengths: *const ::std::os::raw::c_uint,
        bp: *mut ::std::os::raw::c_uchar,
        out: *mut *mut ::std::os::raw::c_uchar,
        outsize: *mut usize,
    );
    pub fn ZopfliVerifyLenDist(
        data: *const ::std::os::raw::c_uchar,
        datasize: usize,
        pos: usize,
        dist: ::std::os::raw::c_ushort,
        length: ::std::os::raw::c_ushort,
    );
    pub fn ZopfliGetDistExtraBits(dist: c_int) -> c_int;
    pub fn ZopfliGetDistExtraBitsValue(dist: c_int) -> c_int;
    pub fn ZopfliGetDistSymbol(dist: c_int) -> c_int;
    pub fn ZopfliGetLengthExtraBits(l: c_int) -> c_int;
    pub fn ZopfliGetLengthExtraBitsValue(l: c_int) -> c_int;
    pub fn ZopfliGetLengthSymbol(l: c_int) -> c_int;
    pub fn ZopfliGetLengthSymbolExtraBits(s: c_int) -> c_int;
    pub fn ZopfliGetDistSymbolExtraBits(s: c_int) -> c_int;
    pub fn ZopfliCalculateBitLengths(
        count: *const usize,
        n: usize,
        maxbits: c_int,
        bitlengths: *mut c_uint,
    );
    pub fn ZopfliBlockSplit(
        options: *const ZopfliOptions,
        input: *const c_uchar,
        instart: size_t,
        inend: size_t,
        maxblocks: size_t,
        splitpoints: *mut *mut size_t,
        npoints: *mut size_t,
    );
    pub fn ZopfliBlockSplitSimple(
        in_data: *const c_uchar,
        instart: size_t,
        inend: size_t,
        blocksize: size_t,
        splitpoints: *mut *mut size_t,
        npoints: *mut size_t,
    );
    pub fn ZopfliBlockSplitLZ77(
        options: *const ZopfliOptions,
        lz77: *const ZopfliLZ77Store,
        maxblocks: size_t,
        splitpoints: *mut *mut size_t,
        npoints: *mut size_t,
    );
    pub fn ZopfliLengthsToSymbols(
        lengths: *const c_uint,
        n: size_t,
        maxbits: c_uint,
        symbols: *mut c_uint,
    );
    pub fn PatchDistanceCodesForBuggyDecoders(d_lengths: *mut c_uint);
    pub fn CalculateTreeSize(ll_lengths: *const c_uint, d_lengths: *const c_uint) -> size_t;
    pub fn TryOptimizeHuffmanForRle(
        lz77: *const ZopfliLZ77Store,
        lstart: size_t,
        lend: size_t,
        ll_counts: *const size_t,
        d_counts: *const size_t,
        ll_lengths: *mut c_uint,
        d_lengths: *mut c_uint,
    ) -> c_double;
    pub fn ZopfliCalculateEntropy(count: *const size_t, n: size_t, bitlengths: *mut c_double);
    pub fn ZopfliInitOptions(options: *mut ZopfliOptions);
    pub fn ZopfliCleanLZ77Store(store: *mut ZopfliLZ77Store);
    pub fn ZopfliInitLZ77Store(data: *const u8, store: *mut ZopfliLZ77Store);
    pub fn ZopfliLZ77GetByteRange(
        lz77: *const ZopfliLZ77Store,
        lstart: size_t,
        lend: size_t,
    ) -> size_t;
    pub fn ZopfliLZ77GetHistogram(
        lz77: *const ZopfliLZ77Store,
        lstart: size_t,
        lend: size_t,
        ll_counts: *mut size_t,
        d_counts: *mut size_t,
    );
    pub fn ZopfliStoreLitLenDist(
        length: u16,
        dist: u16,
        pos: usize,
        store: *mut ZopfliLZ77Store,
    );
    pub fn ZopfliAppendLZ77Store(
        store: *const ZopfliLZ77Store,
        target: *mut ZopfliLZ77Store,
    );
    pub fn ZopfliCalculateBlockSize(
        lz77: *const ZopfliLZ77Store,
        lstart: size_t,
        lend: size_t,
        btype: c_int,
    ) -> c_double;
    pub fn ZopfliInitCache(blocksize: size_t, lmc: *mut ZopfliLongestMatchCache);
    pub fn ZopfliCleanCache(lmc: *mut ZopfliLongestMatchCache);
    pub fn ZopfliMaxCachedSublen(lmc: *const ZopfliLongestMatchCache, pos: size_t, length: size_t) -> ::std::os::raw::c_uint;
    pub fn ZopfliLengthLimitedCodeLengths(
        count: *const size_t,
        n: size_t,
        maxbits: c_int,
        bitlengths: *mut c_uint,
    ) -> c_int;
    pub fn AddBit(
        bit: c_int,
        bp: *mut c_uchar,
        out: *mut *mut c_uchar,
        outsize: *mut size_t,
    );
    pub fn AddBits(
        symbol: c_uint,
        length: c_uint,
        bp: *mut c_uchar,
        out: *mut *mut c_uchar,
        outsize: *mut size_t,
    );
    pub fn AddHuffmanBits(
        symbol: c_uint,
        length: c_uint,
        bp: *mut c_uchar,
        out: *mut *mut c_uchar,
        outsize: *mut size_t,
    );
    pub fn AddLZ77Data(
        lz77: *const ZopfliLZ77Store,
        lstart: size_t,
        lend: size_t,
        expected_data_size: size_t,
        ll_symbols: *const c_uint,
        ll_lengths: *const c_uint,
        d_symbols: *const c_uint,
        d_lengths: *const c_uint,
        bp: *mut c_uchar,
        out: *mut *mut c_uchar,
        outsize: *mut size_t,
    );
    pub fn AddNonCompressedBlock(
        options: *const ZopfliOptions,
        final_: c_int,
        r#in: *const c_uchar,
        instart: size_t,
        inend: size_t,
        bp: *mut c_uchar,
        out: *mut *mut c_uchar,
        outsize: *mut size_t,
    );
    pub fn OptimizeHuffmanForRle(length: c_int, counts: *mut size_t);
    pub fn CalculateBlockSymbolSizeSmall(
        ll_lengths: *const c_uint,
        d_lengths: *const c_uint,
        lz77: *const ZopfliLZ77Store,

        lstart: size_t,
        lend: size_t,
    ) -> size_t;
    pub fn ZopfliAllocHash(window_size: size_t, h: *mut ZopfliHash);
    pub fn ZopfliResetHash(window_size: size_t, h: *mut ZopfliHash);
    pub fn ZopfliCleanHash(h: *mut ZopfliHash);
    pub fn UpdateHashValue(h: *mut ZopfliHash, value: u8);
    pub fn ZopfliUpdateHash(
        array: *const ::std::os::raw::c_uchar,
        pos: size_t,
        end: size_t,
        h: *mut ZopfliHash,
    );
    pub fn ZopfliCopyLZ77Store(source: *const ZopfliLZ77Store, dest: *mut ZopfliLZ77Store);
    pub fn CalculateBlockSymbolSizeGivenCounts(
        ll_counts: *const size_t,
        d_counts: *const size_t,
        ll_lengths: *const c_uint,
        d_lengths: *const c_uint,
        lz77: *const ZopfliLZ77Store,
        lstart: size_t,
        lend: size_t,
    ) -> size_t;
    pub fn ZopfliSublenToCache(
        sublen: *const c_ushort,
        pos: size_t,
        length: size_t,
        lmc: *mut ZopfliLongestMatchCache,
    );
    pub fn ZopfliWarmupHash(
        array: *const ::std::os::raw::c_uchar,
        pos: usize,
        end: usize,
        h: *mut ZopfliHash,
    );
    pub fn ZopfliCacheToSublen(
        lmc: *const ZopfliLongestMatchCache,
        pos: size_t,
        length: size_t,
        sublen: *mut c_ushort,
    );
    pub fn EncodeTree(
        ll_lengths: *const ::std::os::raw::c_uint,
        d_lengths: *const ::std::os::raw::c_uint,
        use_16: ::std::os::raw::c_int,
        use_17: ::std::os::raw::c_int,
        use_18: ::std::os::raw::c_int,
        bp: *mut ::std::os::raw::c_uchar,
        out: *mut *mut ::std::os::raw::c_uchar,
        outsize: *mut usize,
    ) -> usize;
    pub fn ZopfliInitBlockState(
        options: *const ZopfliOptions,
        blockstart: size_t,
        blockend: size_t,
        add_lmc: c_int,
        s: *mut ZopfliBlockState,
    );
    pub fn ZopfliCleanBlockState(s: *mut ZopfliBlockState);
    pub fn AddLZ77Block(
        options: *const ZopfliOptions,
        btype: c_int,
        final_block: c_int,
        lz77: *const ZopfliLZ77Store,
        lstart: size_t,
        lend: size_t,
        expected_data_size: size_t,
        bp: *mut c_uchar,
        out: *mut *mut c_uchar,
        outsize: *mut size_t,
    );
    pub fn ZopfliLZ77Greedy(
        s: *mut ZopfliBlockState,
        r#in: *const c_uchar,
        instart: size_t,
        inend: size_t,
        store: *mut ZopfliLZ77Store,
        h: *mut ZopfliHash,
    );
    pub fn ZopfliFindLongestMatch(
        s: *mut ZopfliBlockState,
        h: *const ZopfliHash,
        array: *const c_uchar,
        pos: size_t,
        size: size_t,
        limit: size_t,
        sublen: *mut c_ushort,
        distance: *mut c_ushort,
        length: *mut c_ushort,
    );
    pub fn ZopfliLZ77GetHistogramAt(
        lz77: *const ZopfliLZ77Store,
        lpos: size_t,
        ll_counts: *mut size_t,
        d_counts: *mut size_t,
    );
    pub fn GetFixedTree(ll_lengths: *mut c_uint, d_lengths: *mut c_uint);
    pub fn GetDynamicLengths(
        lz77: *const ZopfliLZ77Store,
        lstart: size_t,
        lend: size_t,
        ll_lengths: *mut c_uint,
        d_lengths: *mut c_uint,
    ) -> c_double;
    pub fn CalculateBlockSymbolSize(
        ll_lengths: *const c_uint,
        d_lengths: *const c_uint,
        lz77: *const ZopfliLZ77Store,
        lstart: size_t,
        lend: size_t,
    ) -> size_t;
    pub fn ZopfliLZ77Optimal(
        s: *mut ZopfliBlockState,
        in_data: *const u8,
        instart: size_t,
        inend: size_t,
        numiterations: c_int,
        store: *mut ZopfliLZ77Store,
    );
    pub fn ZopfliLZ77OptimalFixed(
        s: *mut ZopfliBlockState,
        r#in: *const c_uchar,
        instart: size_t,
        inend: size_t,
        store: *mut ZopfliLZ77Store,
    );
    pub fn ZopfliCalculateBlockSizeAutoType(
        lz77: *const ZopfliLZ77Store,
        lstart: size_t,
        lend: size_t,
    ) -> c_double;
    pub fn AddLZ77BlockAutoType(
        options: *const ZopfliOptions,
        final_block: c_int,
        lz77: *const ZopfliLZ77Store,
        lstart: size_t,
        lend: size_t,
        expected_data_size: size_t,
        bp: *mut c_uchar,
        out: *mut *mut c_uchar,
        outsize: *mut size_t,
    );
    pub fn AbsDiff(x: size_t, y: size_t) -> size_t;
    pub fn ZopfliDeflate(
        options: *const ZopfliOptions,
        btype: c_int,
        final_: c_int,
        r#in: *const c_uchar,
        insize: size_t,
        bp: *mut c_uchar,
        out: *mut *mut c_uchar,
        outsize: *mut size_t,
    );
    pub fn ZopfliDeflatePart(
        options: *const ZopfliOptions,
        btype: c_int,
        final_: c_int,
        r#in: *const c_uchar,
        instart: size_t,
        inend: size_t,
        bp: *mut c_uchar,
        out: *mut *mut c_uchar,
        outsize: *mut size_t,
    );
    pub fn ZopfliZlibCompress(
        options: *const ZopfliOptions,
        r#in: *const c_uchar,
        insize: size_t,
        out: *mut *mut c_uchar,
        outsize: *mut size_t,
    );
    pub fn ZopfliGzipCompress(
        options: *const ZopfliOptions,
        r#in: *const c_uchar,
        insize: size_t,
        out: *mut *mut c_uchar,
        outsize: *mut size_t,
    );
    pub fn ZopfliCompress(
        options: *const ZopfliOptions,
        output_type: ZopfliFormat,
        r#in: *const c_uchar,
        insize: size_t,
        out: *mut *mut c_uchar,
        outsize: *mut size_t,
    );
}
