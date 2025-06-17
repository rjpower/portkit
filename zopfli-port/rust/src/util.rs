pub const ZOPFLI_MAX_MATCH: usize = 258;
pub const ZOPFLI_MIN_MATCH: usize = 3;

/* Number of distinct literal/length and distance symbols in DEFLATE */
pub const ZOPFLI_NUM_LL: usize = 288;
pub const ZOPFLI_NUM_D: usize = 32;

/*
The window size for deflate. Must be a power of two. This should be 32768, the
maximum possible by the deflate spec. Anything less hurts compression more than
speed.
*/
pub const ZOPFLI_WINDOW_SIZE: usize = 32768;

/*
The window mask used to wrap indices into the window. This is why the
window size must be a power of two.
*/
pub const ZOPFLI_WINDOW_MASK: usize = ZOPFLI_WINDOW_SIZE - 1;

/*
A block structure of huge, non-smart, blocks to divide the input into, to allow
operating on huge files without exceeding memory, such as the 1GB wiki9 corpus.
The whole compression algorithm, including the smarter block splitting, will
be executed independently on each huge block.
Dividing into huge blocks hurts compression, but not much relative to the size.
Set it to 0 to disable master blocks.
*/
pub const ZOPFLI_MASTER_BLOCK_SIZE: usize = 1000000;

/*
Used to initialize costs for example
*/
pub const ZOPFLI_LARGE_FLOAT: f64 = 1e30;

/*
For longest match cache. max 256. Uses huge amounts of memory but makes it
faster. Uses this many times three bytes per single byte of the input data.
This is so because longest match finding has to find the exact distance
that belongs to each length for the best lz77 strategy.
Good values: e.g. 5, 8.
*/
pub const ZOPFLI_CACHE_LENGTH: usize = 8;

/*
limit the max hash chain hits for this hash value. This has an effect only
on files where the hash value is the same very often. On these files, this
gives worse compression (the value should ideally be 32768, which is the
ZOPFLI_WINDOW_SIZE, while zlib uses 4096 even for best level), but makes it
faster on some specific files.
Good value: e.g. 8192.
*/
pub const ZOPFLI_MAX_CHAIN_HITS: usize = 8192;

/*
Whether to use the longest match cache for ZopfliFindLongestMatch. This cache
consumes a lot of memory but speeds it up. No effect on compression size.
*/
pub const ZOPFLI_LONGEST_MATCH_CACHE: bool = true;

/*
Enable to remember amount of successive identical bytes in the hash chain for
finding longest match
required for ZOPFLI_HASH_SAME_HASH and ZOPFLI_SHORTCUT_LONG_REPETITIONS
This has no effect on the compression result, and enabling it increases speed.
*/
pub const ZOPFLI_HASH_SAME: bool = true;

/*
Switch to a faster hash based on the info from ZOPFLI_HASH_SAME once the
best length so far is long enough. This is way faster for files with lots of
identical bytes, on which the compressor is otherwise too slow. Regular files
are unaffected or maybe a tiny bit slower.
This has no effect on the compression result, only on speed.
*/
pub const ZOPFLI_HASH_SAME_HASH: bool = true;

/*
Enable this, to avoid slowness for files which are a repetition of the same
character more than a multiple of ZOPFLI_MAX_MATCH times. This should not affect
the compression result.
*/
pub const ZOPFLI_SHORTCUT_LONG_REPETITIONS: bool = true;

/*
Whether to use lazy matching in the greedy LZ77 implementation. This gives a
better result of ZopfliLZ77Greedy, but the effect this has on the optimal LZ77
varies from file to file.
*/
pub const ZOPFLI_LAZY_MATCHING: bool = true;

// #ifdef __cplusplus /* C++ cannot assign void* from malloc to *data */
// #define ZOPFLI_APPEND_DATA(/* T */ value, /* T** */ data, /* size_t* */ size) {\
//   if (!((*size) & ((*size) - 1))) {\
//     /*double alloc size if it's a power of two*/\
//     void** data_void = reinterpret_cast<void**>(data);\
//     *data_void = (*size) == 0 ? malloc(sizeof(**data))\
//                               : realloc((*data), (*size) * 2 * sizeof(**data));\
//   }\
//   (*data)[(*size)] = (value);\
//   (*size)++;\
// }

pub unsafe fn ZOPFLI_APPEND_DATA<T: Copy>(value: T, data: &mut *mut T, size: &mut usize) {
    if *size == 0 || (*size & (*size - 1)) == 0 {
        let new_capacity = if *size == 0 { 1 } else { *size * 2 };
        let new_data = if *size == 0 {
            libc::malloc(new_capacity * std::mem::size_of::<T>())
        } else {
            libc::realloc(*data as *mut libc::c_void, new_capacity * std::mem::size_of::<T>())
        };

        if new_data.is_null() {
            panic!("Out of memory");
        }
        *data = new_data as *mut T;
    }

    std::ptr::write((*data).add(*size), value);
    *size += 1;
}
use crate::ffi;

impl Default for ffi::ZopfliOptions {
    fn default() -> Self {
        ffi::ZopfliOptions {
            verbose: 0,
            verbose_more: 0,
            numiterations: 15,
            blocksplitting: 1,
            blocksplittinglast: 0,
            blocksplittingmax: 15,
        }
    }
}

pub unsafe fn ZopfliInitOptions(options: *mut ffi::ZopfliOptions) {
    if options.is_null() {
        return;
    }
    *options = ffi::ZopfliOptions::default();
}
pub const HASH_SHIFT: i32 = 5;
pub const HASH_MASK: i32 = 32767;
pub const ZOPFLI_HASH_SIZE: usize = 65536;