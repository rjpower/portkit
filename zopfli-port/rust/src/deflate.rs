use crate::ffi::{
    self, ZopfliBlockState,
    ZopfliLZ77Store, ZopfliOptions,
};
use crate::symbols::{
    ZopfliGetDistExtraBits, ZopfliGetDistSymbolExtraBits, ZopfliGetLengthExtraBits,
    ZopfliGetLengthSymbolExtraBits, ZopfliGetDistSymbol, ZopfliGetLengthSymbol, ZopfliGetDistExtraBitsValue, ZopfliGetLengthExtraBitsValue,
};
use crate::util::{ZOPFLI_APPEND_DATA, ZOPFLI_MAX_MATCH, ZOPFLI_NUM_D, ZOPFLI_NUM_LL};
use crate::lz77::ZopfliLZ77GetByteRange;
use libc::{c_double, c_int, c_uchar, c_uint, size_t, free};
use std::ptr;

pub unsafe fn AddBit(
    bit: c_int,
    bp: *mut c_uchar,
    out: *mut *mut c_uchar,
    outsize: *mut size_t,
) {
    let bp = unsafe { &mut *bp };
    let out = unsafe { &mut *out };
    let outsize = unsafe { &mut *outsize };

    if *bp == 0 {
        ZOPFLI_APPEND_DATA(0u8, out, outsize);
    }
    let out_slice = unsafe { std::slice::from_raw_parts_mut(*out, *outsize) };
    out_slice[*outsize - 1] |= (bit as u8) << *bp;
    *bp = (*bp + 1) & 7;
}

pub unsafe fn AddBits(
    symbol: c_uint,
    length: c_uint,
    bp: *mut c_uchar,
    out: *mut *mut c_uchar,
    outsize: *mut size_t,
) {
    let bp = &mut *bp;
    let out = &mut *out;
    let outsize = &mut *outsize;

    for i in 0..length {
        let bit = (symbol >> i) & 1;
        if *bp == 0 {
            crate::util::ZOPFLI_APPEND_DATA(0, out, outsize);
        }
        let out_slice = std::slice::from_raw_parts_mut(*out, *outsize);
        out_slice[*outsize - 1] |= (bit as u8) << *bp;
        *bp = (*bp + 1) & 7;
    }
}

pub unsafe fn AddHuffmanBits(
    symbol: c_uint,
    length: c_uint,
    bp: *mut c_uchar,
    out: *mut *mut c_uchar,
    outsize: *mut size_t,
) {
    let bp = unsafe { &mut *bp };
    let out = unsafe { &mut *out };
    let outsize = unsafe { &mut *outsize };

    for i in 0..length {
        let bit = (symbol >> (length - i - 1)) & 1;
        if *bp == 0 {
            ZOPFLI_APPEND_DATA(0, out, outsize);
        }
        let out_slice = unsafe { std::slice::from_raw_parts_mut(*out, *outsize) };
        out_slice[*outsize - 1] |= (bit as u8) << *bp;
        *bp = (*bp + 1) & 7;
    }
}

pub unsafe fn AddDynamicTree(
    ll_lengths: *const c_uint,
    d_lengths: *const c_uint,
    bp: *mut c_uchar,
    out: *mut *mut c_uchar,
    outsize: *mut usize,
) {
    let mut best = 0;
    let mut bestsize = 0;

    for i in 0..8 {
        let size = EncodeTree(
            ll_lengths,
            d_lengths,
            i & 1,
            i & 2,
            i & 4,
            ptr::null_mut(),
            ptr::null_mut(),
            ptr::null_mut(),
        );
        if bestsize == 0 || size < bestsize {
            bestsize = size;
            best = i;
        }
    }

    EncodeTree(
        ll_lengths,
        d_lengths,
        best & 1,
        best & 2,
        best & 4,
        bp,
        out,
        outsize,
    );
}

pub unsafe fn AddLZ77Data(
    lz77: *const ZopfliLZ77Store,
    lstart: usize,
    lend: size_t,
    expected_data_size: size_t,
    ll_symbols: *const c_uint,
    ll_lengths: *const c_uint,
    d_symbols: *const c_uint,
    d_lengths: *const c_uint,
    bp: *mut c_uchar,
    out: *mut *mut c_uchar,
    outsize: *mut size_t,
) {
    let lz77 = &*lz77;
    let ll_symbols = std::slice::from_raw_parts(ll_symbols, ZOPFLI_NUM_LL);
    let ll_lengths = std::slice::from_raw_parts(ll_lengths, ZOPFLI_NUM_LL);
    let d_symbols = std::slice::from_raw_parts(d_symbols, ZOPFLI_NUM_D);
    let d_lengths = std::slice::from_raw_parts(d_lengths, ZOPFLI_NUM_D);
    
    // Handle empty store case where pointers may be null
    if lz77.size == 0 || lstart >= lend {
        assert!(expected_data_size == 0 || 0 == expected_data_size);
        return;
    }
    
    let dists = std::slice::from_raw_parts(lz77.dists, lz77.size as usize);
    let litlens = std::slice::from_raw_parts(lz77.litlens, lz77.size as usize);

    let mut testlength = 0;
    for i in lstart..lend {
        let dist = dists[i] as c_int;
        let litlen = litlens[i] as c_int;

        if dist == 0 {
            debug_assert!(litlen < 256);
            debug_assert!(ll_lengths[litlen as usize] > 0);
            AddHuffmanBits(
                ll_symbols[litlen as usize],
                ll_lengths[litlen as usize],
                bp,
                out,
                outsize,
            );
            testlength += 1;
        } else {
            let lls = ZopfliGetLengthSymbol(litlen) as usize;
            let ds = ZopfliGetDistSymbol(dist) as usize;
            debug_assert!(litlen >= 3 && litlen <= 288);
            debug_assert!(ll_lengths[lls] > 0);
            debug_assert!(d_lengths[ds] > 0);
            AddHuffmanBits(ll_symbols[lls], ll_lengths[lls], bp, out, outsize);
            AddBits(
                ZopfliGetLengthExtraBitsValue(litlen) as c_uint,
                ZopfliGetLengthExtraBits(litlen) as c_uint,
                bp,
                out,
                outsize,
            );
            AddHuffmanBits(d_symbols[ds], d_lengths[ds], bp, out, outsize);
            AddBits(
                ZopfliGetDistExtraBitsValue(dist) as c_uint,
                ZopfliGetDistExtraBits(dist) as c_uint,
                bp,
                out,
                outsize,
            );
            testlength += litlen as usize;
        }
    }
    assert!(expected_data_size == 0 || testlength == expected_data_size);
}

pub unsafe fn ZopfliCalculateBlockSize(
    lz77: *const ZopfliLZ77Store,
    lstart: size_t,
    lend: size_t,
    btype: c_int,
) -> c_double {
    let mut ll_lengths: [c_uint; ZOPFLI_NUM_LL] = [0; ZOPFLI_NUM_LL];
    let mut d_lengths: [c_uint; ZOPFLI_NUM_D] = [0; ZOPFLI_NUM_D];

    let mut result = 3.0; /* bfinal and btype bits */

    if btype == 0 {
        let length = ZopfliLZ77GetByteRange(lz77, lstart, lend);
        let rem = length % 65535;
        let blocks = length / 65535 + if rem > 0 { 1 } else { 0 };
        /* An uncompressed block must actually be split into multiple blocks if it's
        larger than 65535 bytes long. Eeach block header is 5 bytes: 3 bits,
        padding, LEN and NLEN (potential less padding for first one ignored). */
        return (blocks * 5 * 8 + length * 8) as c_double;
    } else if btype == 1 {
        GetFixedTree(ll_lengths.as_mut_ptr(), d_lengths.as_mut_ptr());
        result += CalculateBlockSymbolSize(ll_lengths.as_ptr(), d_lengths.as_ptr(), lz77, lstart, lend) as c_double;
    } else {
        result += GetDynamicLengths(lz77, lstart, lend, ll_lengths.as_mut_ptr(), d_lengths.as_mut_ptr());
    }

    result
}

pub unsafe fn CalculateBlockSymbolSizeSmall(
    ll_lengths: *const c_uint,
    d_lengths: *const c_uint,
    lz77: *const ZopfliLZ77Store,
    lstart: size_t,
    lend: size_t,
) -> size_t {
    let lz77 = &*lz77;
    let ll_lengths = std::slice::from_raw_parts(ll_lengths, ZOPFLI_NUM_LL);
    let d_lengths = std::slice::from_raw_parts(d_lengths, ZOPFLI_NUM_D);
    
    // Handle empty store case where pointers may be null
    if lz77.size == 0 || lstart >= lend {
        return ll_lengths[256] as size_t; /* end symbol */
    }
    
    let litlens = std::slice::from_raw_parts(lz77.litlens, lz77.size as usize);
    let dists = std::slice::from_raw_parts(lz77.dists, lz77.size as usize);

    let mut result = 0;
    for i in lstart..lend {
        debug_assert!(i < lz77.size as usize);
        debug_assert!((litlens[i] as c_int) < 259);
        if dists[i] == 0 {
            result += ll_lengths[litlens[i] as usize] as size_t;
        } else {
            let ll_symbol = ZopfliGetLengthSymbol(litlens[i] as c_int) as usize;
            let d_symbol = ZopfliGetDistSymbol(dists[i] as c_int) as usize;
            result += ll_lengths[ll_symbol] as size_t;
            result += d_lengths[d_symbol] as size_t;
            result += ZopfliGetLengthSymbolExtraBits(ll_symbol as c_int) as size_t;
            result += ZopfliGetDistSymbolExtraBits(d_symbol as c_int) as size_t;
        }
    }
    result += ll_lengths[256] as size_t; /*end symbol*/
    result
}

/// Same as CalculateBlockSymbolSize, but with the histogram provided by the caller.
pub unsafe fn CalculateBlockSymbolSizeGivenCounts(
    ll_counts: *const size_t,
    d_counts: *const size_t,
    ll_lengths: *const c_uint,
    d_lengths: *const c_uint,
    lz77: *const ZopfliLZ77Store,
    lstart: size_t,
    lend: size_t,
) -> size_t {
    if lstart + ZOPFLI_NUM_LL as size_t * 3 > lend {
        return CalculateBlockSymbolSizeSmall(ll_lengths, d_lengths, lz77, lstart, lend);
    }

    let mut result = 0;
    let ll_counts = std::slice::from_raw_parts(ll_counts, ZOPFLI_NUM_LL);
    let d_counts = std::slice::from_raw_parts(d_counts, ZOPFLI_NUM_D);
    let ll_lengths = std::slice::from_raw_parts(ll_lengths, ZOPFLI_NUM_LL);
    let d_lengths = std::slice::from_raw_parts(d_lengths, ZOPFLI_NUM_D);

    for i in 0..256 {
        result += ll_lengths[i] as size_t * ll_counts[i];
    }
    for i in 257..286 {
        result += ll_lengths[i] as size_t * ll_counts[i];
        result += ZopfliGetLengthSymbolExtraBits(i as c_int) as size_t * ll_counts[i];
    }
    for i in 0..30 {
        result += d_lengths[i] as size_t * d_counts[i];
        result += ZopfliGetDistSymbolExtraBits(i as c_int) as size_t * d_counts[i];
    }
    result += ll_lengths[256] as size_t; /* end symbol */
    result
}

pub fn AbsDiff(x: size_t, y: size_t) -> size_t {
    x.abs_diff(y)
}

pub fn OptimizeHuffmanForRle(length: c_int, counts: *mut size_t) {
    let mut length = length as usize;
    if length == 0 {
        return;
    }
    
    // Create a slice with the correct size - only 'length' elements
    let counts = unsafe { std::slice::from_raw_parts_mut(counts, length) };

    // Remove trailing zeros
    while length > 0 && counts[length - 1] == 0 {
        length -= 1;
    }
    if length == 0 {
        return;
    }

    let mut good_for_rle = vec![0; length];

    // Mark existing good RLE sequences
    let mut symbol = counts[0];
    let mut stride = 0;
    for i in 0..=length {
        if i == length || (i < length && counts[i] != symbol) {
            if (symbol == 0 && stride >= 5) || (symbol != 0 && stride >= 7) {
                for k in 0..stride {
                    if i > k && (i - k - 1) < good_for_rle.len() {
                        good_for_rle[i - k - 1] = 1;
                    }
                }
            }
            stride = 1;
            if i < length {
                symbol = counts[i];
            }
        } else {
            stride += 1;
        }
    }

    // Optimize population counts for better RLE compression
    let mut stride = 0;
    let mut limit = counts[0];
    let mut sum: size_t = 0;
    for i in 0..=length {
        let should_break = i == length
            || (i < length && good_for_rle[i] != 0)
            || (i < length && AbsDiff(counts[i], limit) >= 4);
            
        if should_break {
            if stride >= 4 || (stride >= 3 && sum == 0) {
                let count = if stride > 0 {
                    // In C: int count = (sum + stride / 2) / stride;
                    // where sum is size_t and stride is int.
                    // Let's replicate the integer promotion and truncation.
                    let temp = sum.wrapping_add((stride / 2) as u64 as size_t);
                    let result = temp / (stride as u64 as size_t);
                    result as c_int
                } else {
                    0
                };

                let count = if sum == 0 {
                    0
                } else {
                    if count < 1 { 1 } else { count }
                };
                for k in 0..stride {
                    if i > k && (i - k - 1) < counts.len() {
                        counts[i - k - 1] = count as size_t;
                    }
                }
            }
            stride = 0;
            sum = 0;
            if i + 3 < length {
                // Use wrapping arithmetic to match C behavior
                limit = counts[i]
                    .wrapping_add(counts[i + 1])
                    .wrapping_add(counts[i + 2])
                    .wrapping_add(counts[i + 3])
                    .wrapping_add(2) / 4;
            } else if i < length {
                limit = counts[i];
            } else {
                limit = 0;
            }
        }
        stride += 1;
        if i < length {
            sum = sum.wrapping_add(counts[i]);
        }
    }
}

pub unsafe fn AddNonCompressedBlock(
    options: *const ZopfliOptions,
    final_: c_int,
    r#in: *const c_uchar,
    instart: size_t,
    inend: size_t,
    bp: *mut c_uchar,
    out: *mut *mut c_uchar,
    outsize: *mut size_t,
) {
    let mut pos = instart;
    let _ = options; // Unused parameter like in C
    let out = unsafe { &mut *out };
    let outsize = unsafe { &mut *outsize };
    
    loop {
        let mut blocksize = 65535;
        let nlen: u16;
        let currentfinal: c_int;

        if pos + blocksize > inend {
            blocksize = inend - pos;
        }
        currentfinal = if pos + blocksize >= inend { 1 } else { 0 };

        nlen = !blocksize as u16;

        AddBit((final_ != 0 && currentfinal != 0) as c_int, bp, &mut (*out) as *mut _, &mut (*outsize) as *mut _);
        // BTYPE 00
        AddBit(0, bp, &mut (*out) as *mut _, &mut (*outsize) as *mut _);
        AddBit(0, bp, &mut (*out) as *mut _, &mut (*outsize) as *mut _);

        // Any bits of input up to the next byte boundary are ignored.
        *bp = 0;

        ZOPFLI_APPEND_DATA((blocksize % 256) as u8, out, outsize);
        ZOPFLI_APPEND_DATA(((blocksize / 256) % 256) as u8, out, outsize);
        ZOPFLI_APPEND_DATA((nlen % 256) as u8, out, outsize);
        ZOPFLI_APPEND_DATA(((nlen / 256) % 256) as u8, out, outsize);

        for i in 0..blocksize {
            let byte = *r#in.add(pos + i);
            ZOPFLI_APPEND_DATA(byte, out, outsize);
        }

        if currentfinal != 0 {
            break;
        }
        pos += blocksize;
    }
}

use crate::tree::{ZopfliCalculateBitLengths, ZopfliLengthsToSymbols};

pub unsafe fn CalculateBlockSymbolSize(
    ll_lengths: *const c_uint,
    d_lengths: *const c_uint,
    lz77: *const ZopfliLZ77Store,
    lstart: size_t,
    lend: size_t,
) -> size_t {
    if lstart + ZOPFLI_NUM_LL as size_t * 3 > lend {
        CalculateBlockSymbolSizeSmall(ll_lengths, d_lengths, lz77, lstart, lend)
    } else {
        let mut ll_counts: [size_t; ZOPFLI_NUM_LL as usize] = [0; ZOPFLI_NUM_LL as usize];
        let mut d_counts: [size_t; ZOPFLI_NUM_D as usize] = [0; ZOPFLI_NUM_D as usize];
        crate::lz77::ZopfliLZ77GetHistogram(
            lz77,
            lstart,
            lend,
            ll_counts.as_mut_ptr(),
            d_counts.as_mut_ptr(),
        );
        CalculateBlockSymbolSizeGivenCounts(
            ll_counts.as_ptr(),
            d_counts.as_ptr(),
            ll_lengths,
            d_lengths,
            lz77,
            lstart,
            lend,
        )
    }
}

// This is a Rust port of the static C function GetFixedTree
pub fn GetFixedTree(ll_lengths: *mut c_uint, d_lengths: *mut c_uint) {
    let ll_lengths = unsafe { std::slice::from_raw_parts_mut(ll_lengths, crate::util::ZOPFLI_NUM_LL) };
    let d_lengths = unsafe { std::slice::from_raw_parts_mut(d_lengths, crate::util::ZOPFLI_NUM_D) };
    for i in 0..144 {
        ll_lengths[i] = 8;
    }
    for i in 144..256 {
        ll_lengths[i] = 9;
    }
    for i in 256..280 {
        ll_lengths[i] = 7;
    }
    for i in 280..crate::util::ZOPFLI_NUM_LL {
        ll_lengths[i] = 8;
    }
    for i in 0..crate::util::ZOPFLI_NUM_D {
        d_lengths[i] = 5;
    }
}

// This is a Rust port of the static C function GetDynamicLengths
pub unsafe fn GetDynamicLengths(
    lz77: *const crate::ffi::ZopfliLZ77Store,
    lstart: size_t,
    lend: size_t,
    ll_lengths: *mut c_uint,
    d_lengths: *mut c_uint,
) -> c_double {
    let mut ll_counts: [size_t; crate::util::ZOPFLI_NUM_LL as usize] =
        [0; crate::util::ZOPFLI_NUM_LL as usize];
    let mut d_counts: [size_t; crate::util::ZOPFLI_NUM_D as usize] =
        [0; crate::util::ZOPFLI_NUM_D as usize];

    crate::lz77::ZopfliLZ77GetHistogram(
        lz77,
        lstart,
        lend,
        ll_counts.as_mut_ptr(),
        d_counts.as_mut_ptr(),
    );
    ll_counts[256] = 1;  /* End symbol. */
    crate::tree::ZopfliCalculateBitLengths(
        ll_counts.as_ptr(),
        crate::util::ZOPFLI_NUM_LL as size_t,
        15,
        ll_lengths,
    );
    crate::tree::ZopfliCalculateBitLengths(
        d_counts.as_ptr(),
        crate::util::ZOPFLI_NUM_D as size_t,
        15,
        d_lengths,
    );
    PatchDistanceCodesForBuggyDecoders(std::slice::from_raw_parts_mut(d_lengths, ZOPFLI_NUM_D));
    TryOptimizeHuffmanForRle(
        lz77,
        lstart,
        lend,
        ll_counts.as_ptr(),
        d_counts.as_ptr(),
        ll_lengths,
        d_lengths,
    )
}

pub unsafe fn AddLZ77Block(
    options: *const crate::ffi::ZopfliOptions,
    btype: c_int,
    final_block: c_int,
    lz77: *const crate::ffi::ZopfliLZ77Store,
    lstart: size_t,
    lend: size_t,
    expected_data_size: size_t,
    bp: *mut c_uchar,
    out: *mut *mut c_uchar,
    outsize: *mut size_t,
) {
    let mut ll_lengths: [c_uint; crate::util::ZOPFLI_NUM_LL as usize] =
        [0; crate::util::ZOPFLI_NUM_LL as usize];
    let mut d_lengths: [c_uint; crate::util::ZOPFLI_NUM_D as usize] =
        [0; crate::util::ZOPFLI_NUM_D as usize];
    let mut ll_symbols: [c_uint; crate::util::ZOPFLI_NUM_LL as usize] =
        [0; crate::util::ZOPFLI_NUM_LL as usize];
    let mut d_symbols: [c_uint; crate::util::ZOPFLI_NUM_D as usize] =
        [0; crate::util::ZOPFLI_NUM_D as usize];

    if btype == 0 {
        let length = ZopfliLZ77GetByteRange(lz77, lstart, lend);
        let pos = if lstart == lend {
            0
        } else {
            (*lz77).pos.add(lstart).read() as size_t
        };
        let end = pos + length;
        AddNonCompressedBlock(
            options,
            final_block,
            (*lz77).data,
            pos,
            end,
            bp,
            out,
            outsize,
        );
        return;
    }

    AddBit(final_block, bp, out, outsize);
    AddBit(btype & 1, bp, out, outsize);
    AddBit((btype & 2) >> 1, bp, out, outsize);

    if btype == 1 {
        /* Fixed block. */
        GetFixedTree(ll_lengths.as_mut_ptr(), d_lengths.as_mut_ptr());
    } else {
        /* Dynamic block. */
        assert_eq!(btype, 2);

        let detect_tree_size = *outsize;
        let _ = GetDynamicLengths(
            lz77,
            lstart,
            lend,
            ll_lengths.as_mut_ptr(),
            d_lengths.as_mut_ptr(),
        );

        AddDynamicTree(ll_lengths.as_ptr(), d_lengths.as_ptr(), bp, out, outsize);
        if (*options).verbose != 0 {
            eprint!("treesize: {}\n", *outsize - detect_tree_size);
        }
    }

    ZopfliLengthsToSymbols(
        ll_lengths.as_ptr(),
        crate::util::ZOPFLI_NUM_LL as size_t,
        15,
        ll_symbols.as_mut_ptr(),
    );
    ZopfliLengthsToSymbols(
        d_lengths.as_ptr(),
        crate::util::ZOPFLI_NUM_D as size_t,
        15,
        d_symbols.as_mut_ptr(),
    );

    let detect_block_size = *outsize;
    AddLZ77Data(
        lz77,
        lstart,
        lend,
        expected_data_size,
        ll_symbols.as_ptr(),
        ll_lengths.as_ptr(),
        d_symbols.as_ptr(),
        d_lengths.as_ptr(),
        bp,
        out,
        outsize,
    );
    /* End symbol. */
    AddHuffmanBits(ll_symbols[256], ll_lengths[256], bp, out, outsize);

    let mut uncompressed_size: size_t = 0;
    for i in lstart..lend {
        uncompressed_size += if (*lz77).dists.add(i).read() == 0 {
            1
        } else {
            (*lz77).litlens.add(i).read() as size_t
        };
    }
    let compressed_size = *outsize - detect_block_size;
    if (*options).verbose != 0 {
        eprint!(
            "compressed block size: {} ({}k) (unc: {})\n",
            compressed_size,
            compressed_size / 1024,
            uncompressed_size
        );
    }
}

pub fn PatchDistanceCodesForBuggyDecoders(d_lengths: &mut [c_uint]) {
    let mut num_dist_codes = 0;
    for i in 0..30 {
        if d_lengths[i] > 0 {
            num_dist_codes += 1;
        }
        if num_dist_codes >= 2 {
            return;
        }
    }

    if num_dist_codes == 0 {
        d_lengths[0] = 1;
        d_lengths[1] = 1;
    } else if num_dist_codes == 1 {
        if d_lengths[0] > 0 {
            d_lengths[1] = 1;
        } else {
            d_lengths[0] = 1;
        }
    }
}

pub unsafe fn CalculateTreeSize(ll_lengths: *const c_uint, d_lengths: *const c_uint) -> usize {
    let mut result = 0;

    for i in 0..8 {
        let size = EncodeTree(
            ll_lengths,
            d_lengths,
            (i & 1) as c_int,
            (i & 2) as c_int,
            (i & 4) as c_int,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            std::ptr::null_mut(),
        );
        if result == 0 || size < result {
            result = size;
        }
    }

    result
}

pub unsafe fn TryOptimizeHuffmanForRle(
    lz77: *const ZopfliLZ77Store,
    lstart: size_t,
    lend: size_t,
    ll_counts: *const size_t,
    d_counts: *const size_t,
    ll_lengths: *mut c_uint,
    d_lengths: *mut c_uint,
) -> c_double {
    let mut ll_counts2 = [0; ZOPFLI_NUM_LL];
    let mut d_counts2 = [0; crate::util::ZOPFLI_NUM_D];
    let mut ll_lengths2 = [0; ZOPFLI_NUM_LL];
    let mut d_lengths2 = [0; crate::util::ZOPFLI_NUM_D];

    let treesize = CalculateTreeSize(ll_lengths, d_lengths) as f64;
    let datasize = CalculateBlockSymbolSizeGivenCounts(
        ll_counts,
        d_counts,
        ll_lengths,
        d_lengths,
        lz77,
        lstart,
        lend,
    ) as f64;

    let ll_counts_slice = std::slice::from_raw_parts(ll_counts, ZOPFLI_NUM_LL);
    ll_counts2.copy_from_slice(ll_counts_slice);
    let d_counts_slice = std::slice::from_raw_parts(d_counts, ZOPFLI_NUM_D);
    d_counts2.copy_from_slice(d_counts_slice);

    OptimizeHuffmanForRle(ZOPFLI_NUM_LL as c_int, ll_counts2.as_mut_ptr());
    OptimizeHuffmanForRle(crate::util::ZOPFLI_NUM_D as c_int, d_counts2.as_mut_ptr());

    crate::tree::ZopfliCalculateBitLengths(
        ll_counts2.as_ptr(),
        ZOPFLI_NUM_LL as size_t,
        15,
        ll_lengths2.as_mut_ptr(),
    );
    crate::tree::ZopfliCalculateBitLengths(
        d_counts2.as_ptr(),
        crate::util::ZOPFLI_NUM_D as size_t,
        15,
        d_lengths2.as_mut_ptr(),
    );
    PatchDistanceCodesForBuggyDecoders(&mut d_lengths2);

    let treesize2 = CalculateTreeSize(ll_lengths2.as_ptr(), d_lengths2.as_ptr()) as f64;
    let datasize2 = CalculateBlockSymbolSizeGivenCounts(
        ll_counts,
        d_counts,
        ll_lengths2.as_ptr(),
        d_lengths2.as_ptr(),
        lz77,
        lstart,
        lend,
    ) as f64;

    if treesize2 + datasize2 < treesize + datasize {
        let ll_lengths_slice = std::slice::from_raw_parts_mut(ll_lengths, ZOPFLI_NUM_LL);
        ll_lengths_slice.copy_from_slice(&ll_lengths2);
        let d_lengths_slice = std::slice::from_raw_parts_mut(d_lengths, crate::util::ZOPFLI_NUM_D);
        d_lengths_slice.copy_from_slice(&d_lengths2);
        return treesize2 + datasize2;
    }
    treesize + datasize
}

pub unsafe fn ZopfliCalculateBlockSizeAutoType(
    lz77: *const ZopfliLZ77Store,
    lstart: size_t,
    lend: size_t,
) -> c_double {
    let uncompressedcost = ZopfliCalculateBlockSize(lz77, lstart, lend, 0);
    /* Don't do the expensive fixed cost calculation for larger blocks that are
    unlikely to use it. */
    let fixedcost = if (*lz77).size > 1000 {
        uncompressedcost
    } else {
        ZopfliCalculateBlockSize(lz77, lstart, lend, 1)
    };
    let dyncost = ZopfliCalculateBlockSize(lz77, lstart, lend, 2);

    if uncompressedcost < fixedcost && uncompressedcost < dyncost {
        uncompressedcost
    } else if fixedcost < dyncost {
        fixedcost
    } else {
        dyncost
    }
}

pub unsafe fn AddLZ77BlockAutoType(
    options: *const ZopfliOptions,
    final_block: c_int,
    lz77: *const ZopfliLZ77Store,
    lstart: size_t,
    lend: size_t,
    expected_data_size: size_t,
    bp: *mut c_uchar,
    out: *mut *mut c_uchar,
    outsize: *mut size_t,
) {
    let lz77_ref = &*lz77;

    let uncompressedcost = ZopfliCalculateBlockSize(lz77, lstart, lend, 0);
    let mut fixedcost = ZopfliCalculateBlockSize(lz77, lstart, lend, 1);
    let dyncost = ZopfliCalculateBlockSize(lz77, lstart, lend, 2);

    /* Whether to perform the expensive calculation of creating an optimal block
    with fixed huffman tree to check if smaller. Only do this for small blocks or
    blocks which already are pretty good with fixed huffman tree. */
    let expensivefixed = (lz77_ref.size < 1000) || fixedcost <= dyncost * 1.1;

    let mut fixedstore_owner: ZopfliLZ77Store = std::mem::zeroed();

    if lstart == lend {
        /* Smallest empty block is represented by fixed block */
        AddBits(final_block as u32, 1, bp, out, outsize);
        AddBits(1, 2, bp, out, outsize); // btype 01
        AddBits(0, 7, bp, out, outsize); // end symbol has code 0000000
        return;
    }

    crate::ffi::ZopfliInitLZ77Store(lz77_ref.data, &mut fixedstore_owner);

    if expensivefixed {
        let instart = lz77_ref.pos.add(lstart).read();
        let inend = instart + ZopfliLZ77GetByteRange(lz77_ref, lstart, lend);
        
        let mut s: ZopfliBlockState = std::mem::zeroed();
        crate::ffi::ZopfliInitBlockState(options, instart, inend, 1, &mut s);
        crate::ffi::ZopfliLZ77OptimalFixed(&mut s, lz77_ref.data, instart, inend, &mut fixedstore_owner);
        fixedcost = ZopfliCalculateBlockSize(&fixedstore_owner, 0, fixedstore_owner.size, 1);
        crate::ffi::ZopfliCleanBlockState(&mut s);
    }

    if uncompressedcost < fixedcost && uncompressedcost < dyncost {
        AddLZ77Block(options, 0, final_block, lz77, lstart, lend, expected_data_size, bp, out, outsize);
    } else if fixedcost < dyncost {
        if expensivefixed {
            AddLZ77Block(options, 1, final_block, &fixedstore_owner, 0, fixedstore_owner.size, expected_data_size, bp, out, outsize);
        } else {
            AddLZ77Block(options, 1, final_block, lz77, lstart, lend, expected_data_size, bp, out, outsize);
        }
    } else {
        AddLZ77Block(options, 2, final_block, lz77, lstart, lend, expected_data_size, bp, out, outsize);
    }

    crate::ffi::ZopfliCleanLZ77Store(&mut fixedstore_owner);
}

pub unsafe fn EncodeTree(
    ll_lengths: *const c_uint,
    d_lengths: *const c_uint,
    use_16: c_int,
    use_17: c_int,
    use_18: c_int,
    bp: *mut c_uchar,
    out: *mut *mut c_uchar,
    outsize: *mut usize,
) -> usize {
    let order: [c_uint; 19] = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15];
    let size_only = out.is_null();
    let mut result_size = 0;

    let mut clcounts: [usize; 19] = [0; 19];

    let mut hlit = 29;
    while hlit > 0 && *ll_lengths.offset(257 + hlit - 1) == 0 {
        hlit -= 1;
    }
    let mut hdist = 29;
    while hdist > 0 && *d_lengths.offset(1 + hdist - 1) == 0 {
        hdist -= 1;
    }
    let hlit2 = hlit + 257;

    let lld_total = hlit2 + hdist + 1;

    let mut rle: Vec<c_uint> = Vec::new();
    let mut rle_bits: Vec<c_uint> = Vec::new();

    let mut i = 0;
    while i < lld_total {
        let symbol = if i < hlit2 {
            *ll_lengths.offset(i as isize)
        } else {
            *d_lengths.offset((i - hlit2) as isize)
        } as u8;
        let mut count = 1;
        if use_16 != 0 || (symbol == 0 && (use_17 != 0 || use_18 != 0)) {
            let mut j = i + 1;
            while j < lld_total {
                let next_symbol = if j < hlit2 {
                    *ll_lengths.offset(j as isize)
                } else {
                    *d_lengths.offset((j - hlit2) as isize)
                } as u8;
                if symbol != next_symbol {
                    break;
                }
                count += 1;
                j += 1;
            }
        }
        i += count;

        if symbol == 0 && count >= 3 {
            if use_18 != 0 {
                while count >= 11 {
                    let count2 = if count > 138 { 138 } else { count };
                    if !size_only {
                        rle.push(18);
                        rle_bits.push((count2 - 11) as c_uint);
                    }
                    clcounts[18] += 1;
                    count -= count2;
                }
            }
            if use_17 != 0 {
                while count >= 3 {
                    let count2 = if count > 10 { 10 } else { count };
                    if !size_only {
                        rle.push(17);
                        rle_bits.push((count2 - 3) as c_uint);
                    }
                    clcounts[17] += 1;
                    count -= count2;
                }
            }
        }

        if use_16 != 0 && count >= 4 {
            count -= 1;
            clcounts[symbol as usize] += 1;
            if !size_only {
                rle.push(symbol as c_uint);
                rle_bits.push(0);
            }
            while count >= 3 {
                let count2 = if count > 6 { 6 } else { count };
                if !size_only {
                    rle.push(16);
                    rle_bits.push((count2 - 3) as c_uint);
                }
                clcounts[16] += 1;
                count -= count2;
            }
        }

        clcounts[symbol as usize] += count as usize;
        let mut n = count;
        while n > 0 {
            if !size_only {
                rle.push(symbol as c_uint);
                rle_bits.push(0);
            }
            n -= 1;
        }
    }

    let mut clcl: [c_uint; 19] = [0; 19];
    ZopfliCalculateBitLengths(clcounts.as_ptr(), 19, 7, clcl.as_mut_ptr());

    let mut clsymbols: [c_uint; 19] = [0; 19];
    if !size_only {
        ZopfliLengthsToSymbols(clcl.as_ptr(), 19, 7, clsymbols.as_mut_ptr());
    }

    let mut hclen = 15;
    while hclen > 0 && clcounts[order[(hclen + 4 - 1) as usize] as usize] == 0 {
        hclen -= 1;
    }

    if !size_only {
        AddBits(hlit as c_uint, 5, bp, out, outsize);
        AddBits(hdist as c_uint, 5, bp, out, outsize);
        AddBits(hclen as c_uint, 4, bp, out, outsize);

        for i in 0..(hclen + 4) {
            AddBits(clcl[order[i as usize] as usize], 3, bp, out, outsize);
        }

        for i in 0..rle.len() {
            let symbol = clsymbols[rle[i] as usize];
            AddHuffmanBits(symbol, clcl[rle[i] as usize], bp, out, outsize);
            if rle[i] == 16 {
                AddBits(rle_bits[i], 2, bp, out, outsize);
            } else if rle[i] == 17 {
                AddBits(rle_bits[i], 3, bp, out, outsize);
            } else if rle[i] == 18 {
                AddBits(rle_bits[i], 7, bp, out, outsize);
            }
        }
    }

    result_size += 14;
    result_size += (hclen as usize + 4) * 3;
    for i in 0..19 {
        result_size += (clcl[i] * clcounts[i] as c_uint) as usize;
    }
    result_size += clcounts[16] * 2;
    result_size += clcounts[17] * 3;
    result_size += clcounts[18] * 7;

    result_size
}

pub unsafe fn ZopfliDeflate(
    options: *const ZopfliOptions,
    btype: c_int,
    final_block: c_int,
    r#in: *const c_uchar,
    insize: size_t,
    bp: *mut c_uchar,
    out: *mut *mut c_uchar,
    outsize: *mut size_t,
) {
    let offset = *outsize;
    
    if crate::util::ZOPFLI_MASTER_BLOCK_SIZE == 0 {
        ZopfliDeflatePart(options, btype, final_block, r#in, 0, insize, bp, out, outsize);
    } else {
        let mut i = 0;
        loop {
            let masterfinal = i + crate::util::ZOPFLI_MASTER_BLOCK_SIZE >= insize;
            let final2 = (final_block != 0) && masterfinal;
            let size = if masterfinal { insize - i } else { crate::util::ZOPFLI_MASTER_BLOCK_SIZE };
            
            ZopfliDeflatePart(
                options,
                btype,
                if final2 { 1 } else { 0 },
                r#in,
                i,
                i + size,
                bp,
                out,
                outsize,
            );
            i += size;
            
            if i >= insize {
                break;
            }
        }
    }
    
    if (*options).verbose != 0 {
        let removed_percent = 100.0 * (insize as f64 - (*outsize - offset) as f64) / insize as f64;
        eprintln!(
            "Original Size: {}, Deflate: {}, Compression: {:.6}% Removed",
            insize,
            *outsize - offset,
            removed_percent
        );
    }
}

pub unsafe fn ZopfliDeflatePart(
    options: *const ZopfliOptions,
    btype: c_int,
    final_block: c_int,
    r#in: *const c_uchar,
    instart: size_t,
    inend: size_t,
    bp: *mut c_uchar,
    out: *mut *mut c_uchar,
    outsize: *mut size_t,
) {
    let mut splitpoints_uncompressed: *mut size_t = std::ptr::null_mut();
    let mut npoints = 0;
    let mut splitpoints: *mut size_t = std::ptr::null_mut();
    let mut totalcost = 0.0;
    let mut lz77: ZopfliLZ77Store = std::mem::zeroed();

    if btype == 0 {
        AddNonCompressedBlock(options, final_block, r#in, instart, inend, bp, out, outsize);
        return;
    } else if btype == 1 {
        let mut store: ZopfliLZ77Store = std::mem::zeroed();
        let mut s: ZopfliBlockState = std::mem::zeroed();
        ffi::ZopfliInitLZ77Store(r#in, &mut store);
        ffi::ZopfliInitBlockState(options, instart, inend, 1, &mut s);

        ffi::ZopfliLZ77OptimalFixed(&mut s, r#in, instart, inend, &mut store);
        AddLZ77Block(options, btype, final_block, &store, 0, store.size, 0, bp, out, outsize);

        ffi::ZopfliCleanBlockState(&mut s);
        ffi::ZopfliCleanLZ77Store(&mut store);
        return;
    }

    if (*options).blocksplitting != 0 {
        ffi::ZopfliBlockSplit(
            options,
            r#in,
            instart,
            inend,
            (*options).blocksplittingmax as size_t,
            &mut splitpoints_uncompressed,
            &mut npoints,
        );
        splitpoints = libc::malloc(std::mem::size_of::<size_t>() * npoints as usize) as *mut size_t;
    }

    ffi::ZopfliInitLZ77Store(r#in, &mut lz77);

    for i in 0..=npoints {
        let start = if i == 0 { instart } else { *splitpoints_uncompressed.add(i - 1) };
        let end = if i == npoints { inend } else { *splitpoints_uncompressed.add(i) };
        let mut s: ZopfliBlockState = std::mem::zeroed();
        let mut store: ZopfliLZ77Store = std::mem::zeroed();
        ffi::ZopfliInitLZ77Store(r#in, &mut store);
        ffi::ZopfliInitBlockState(options, start, end, 1, &mut s);
        ffi::ZopfliLZ77Optimal(&mut s, r#in, start, end, (*options).numiterations, &mut store);
        totalcost += ZopfliCalculateBlockSizeAutoType(&store, 0, store.size);

        ffi::ZopfliAppendLZ77Store(&store, &mut lz77);
        if i < npoints {
            *splitpoints.add(i) = lz77.size;
        }

        ffi::ZopfliCleanBlockState(&mut s);
        ffi::ZopfliCleanLZ77Store(&mut store);
    }

    if (*options).blocksplitting != 0 && npoints > 1 {
        let mut splitpoints2: *mut size_t = std::ptr::null_mut();
        let mut npoints2 = 0;
        let mut totalcost2 = 0.0;

        ffi::ZopfliBlockSplitLZ77(
            options,
            &lz77,
            (*options).blocksplittingmax as size_t,
            &mut splitpoints2,
            &mut npoints2,
        );

        for i in 0..=npoints2 {
            let start = if i == 0 { 0 } else { *splitpoints2.add(i - 1) };
            let end = if i == npoints2 { lz77.size } else { *splitpoints2.add(i) };
            totalcost2 += ZopfliCalculateBlockSizeAutoType(&lz77, start, end);
        }

        if totalcost2 < totalcost {
            libc::free(splitpoints as *mut libc::c_void);
            splitpoints = splitpoints2;
            npoints = npoints2;
        } else {
            libc::free(splitpoints2 as *mut libc::c_void);
        }
    }

    for i in 0..=npoints {
        let start = if i == 0 { 0 } else { *splitpoints.add(i - 1) };
        let end = if i == npoints { lz77.size } else { *splitpoints.add(i) };
        AddLZ77BlockAutoType(
            options, 
            (i == npoints && final_block != 0) as c_int,
            &lz77, 
            start, 
            end, 
            0,
            bp, 
            out, 
            outsize
        );
    }

    ffi::ZopfliCleanLZ77Store(&mut lz77);
    libc::free(splitpoints as *mut libc::c_void);
    libc::free(splitpoints_uncompressed as *mut libc::c_void);
}
