#![no_main]
use libfuzzer_sys::fuzz_target;

use std::mem::MaybeUninit;
use std::slice::from_raw_parts;

use zopfli::ffi;
use zopfli::hash;
use zopfli::util::{ZOPFLI_WINDOW_SIZE, ZOPFLI_HASH_SIZE};

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    data: Vec<u8>,
    pos: u16,
    end: u16,
}

fuzz_target!(|input: FuzzInput| {
    let data = input.data;
    if data.is_empty() {
        return;
    }

    let pos = input.pos as usize % data.len();
    let end = input.end as usize % data.len();
    let (pos, end) = if pos > end { (end, pos) } else { (pos, end) };

    unsafe {
        let mut c_hash = MaybeUninit::uninit();
        ffi::ZopfliAllocHash(ZOPFLI_WINDOW_SIZE, c_hash.as_mut_ptr());
        let mut c_hash = c_hash.assume_init();
        ffi::ZopfliResetHash(ZOPFLI_WINDOW_SIZE, &mut c_hash);


        let mut rust_hash = MaybeUninit::uninit();
        ffi::ZopfliAllocHash(ZOPFLI_WINDOW_SIZE, rust_hash.as_mut_ptr());
        let mut rust_hash = rust_hash.assume_init();
        hash::ZopfliResetHash(ZOPFLI_WINDOW_SIZE, &mut rust_hash);

        // The hash state needs to be warmed up before it can be used.
        // The C implementation does this by calling ZopfliUpdateHash in a loop.
        if pos > 0 {
            for i in 0..pos {
                ffi::ZopfliUpdateHash(data.as_ptr(), i, end, &mut c_hash);
                hash::ZopfliUpdateHash(data.as_ptr(), i, end, &mut rust_hash);
            }
        }

        ffi::ZopfliUpdateHash(data.as_ptr(), pos, end, &mut c_hash);
        hash::ZopfliUpdateHash(data.as_ptr(), pos, end, &mut rust_hash);

        assert_eq!(c_hash.val, rust_hash.val);
        assert_eq!(c_hash.val2, rust_hash.val2);

        let c_head = from_raw_parts(c_hash.head, ZOPFLI_HASH_SIZE);
        let rust_head = from_raw_parts(rust_hash.head, ZOPFLI_HASH_SIZE);
        assert_eq!(c_head, rust_head);

        let c_prev = from_raw_parts(c_hash.prev, ZOPFLI_WINDOW_SIZE as usize);
        let rust_prev = from_raw_parts(rust_hash.prev, ZOPFLI_WINDOW_SIZE as usize);
        assert_eq!(c_prev, rust_prev);

        let c_hashval = from_raw_parts(c_hash.hashval, ZOPFLI_WINDOW_SIZE as usize);
        let rust_hashval = from_raw_parts(rust_hash.hashval, ZOPFLI_WINDOW_SIZE as usize);
        assert_eq!(c_hashval, rust_hashval);

        let c_head2 = from_raw_parts(c_hash.head2, ZOPFLI_HASH_SIZE);
        let rust_head2 = from_raw_parts(rust_hash.head2, ZOPFLI_HASH_SIZE);
        assert_eq!(c_head2, rust_head2);

        let c_prev2 = from_raw_parts(c_hash.prev2, ZOPFLI_WINDOW_SIZE as usize);
        let rust_prev2 = from_raw_parts(rust_hash.prev2, ZOPFLI_WINDOW_SIZE as usize);
        assert_eq!(c_prev2, rust_prev2);

        let c_hashval2 = from_raw_parts(c_hash.hashval2, ZOPFLI_WINDOW_SIZE as usize);
        let rust_hashval2 = from_raw_parts(rust_hash.hashval2, ZOPFLI_WINDOW_SIZE as usize);
        assert_eq!(c_hashval2, rust_hashval2);

        let c_same = from_raw_parts(c_hash.same, ZOPFLI_WINDOW_SIZE as usize);
        let rust_same = from_raw_parts(rust_hash.same, ZOPFLI_WINDOW_SIZE as usize);
        assert_eq!(c_same, rust_same);

        ffi::ZopfliCleanHash(&mut c_hash);
        ffi::ZopfliCleanHash(&mut rust_hash);
    }
});