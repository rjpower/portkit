#![no_main]

use libfuzzer_sys::fuzz_target;
use std::os::raw::{c_uchar, c_ushort};
use libc::size_t;
use arbitrary::{Arbitrary, Unstructured};
use zopfli::ffi;
use zopfli::util::{ZOPFLI_MAX_MATCH, ZOPFLI_MIN_MATCH, ZOPFLI_WINDOW_SIZE};

#[derive(Debug, Clone)]
pub struct FuzzInput {
    pub array: Vec<u8>,
    pub pos: usize,
    pub size: usize,
    pub limit: usize,
    pub hash_val: i32,
    pub hash_head: Vec<i32>,
    pub hash_prev: Vec<u16>,
    pub hash_hashval: Vec<i32>,
}

impl<'a> Arbitrary<'a> for FuzzInput {
    fn arbitrary(u: &mut Unstructured<'a>) -> arbitrary::Result<Self> {
        let array_size = u.int_in_range(ZOPFLI_MIN_MATCH..=1024)?;
        let array = u.bytes(array_size).map(|b| b.to_vec())?;
        
        let size = array.len();
        let pos = if size > ZOPFLI_MIN_MATCH {
            u.int_in_range(0..=size - ZOPFLI_MIN_MATCH)?
        } else {
            0
        };

        let limit = u.int_in_range(ZOPFLI_MIN_MATCH..=ZOPFLI_MAX_MATCH)?;

        let hash_val = u.int_in_range(0..=65535-1)?;
        let mut hash_head = Vec::with_capacity(65536);
        for _ in 0..65536 {
            hash_head.push(u.arbitrary()?);
        }
        let mut hash_prev = Vec::with_capacity(ZOPFLI_WINDOW_SIZE);
        for _ in 0..ZOPFLI_WINDOW_SIZE {
            hash_prev.push(u.arbitrary()?);
        }
        let mut hash_hashval = Vec::with_capacity(ZOPFLI_WINDOW_SIZE);
        for _ in 0..ZOPFLI_WINDOW_SIZE {
            hash_hashval.push(u.arbitrary()?);
        }

        // Ensure valid chain: hash head points to current position
        let hpos = pos & (ZOPFLI_WINDOW_SIZE - 1);
        hash_head[hash_val as usize] = hpos as i32;
        
        // Make hash_prev point to itself to break chains (safer for fuzzing)
        for i in 0..ZOPFLI_WINDOW_SIZE {
            hash_prev[i] = i as u16;
        }

        Ok(FuzzInput {
            array,
            pos,
            size,
            limit,
            hash_val,
            hash_head,
            hash_prev,
            hash_hashval,
        })
    }
}

fuzz_target!(|input: FuzzInput| {
    let mut c_s = ffi::ZopfliBlockState {
        options: std::ptr::null(),
        lmc: std::ptr::null_mut(),
        blockstart: 0,
        blockend: input.size,
    };
    let mut rust_s = ffi::ZopfliBlockState {
        options: std::ptr::null(),
        lmc: std::ptr::null_mut(),
        blockstart: 0,
        blockend: input.size,
    };

    let mut c_hash_head = input.hash_head.clone();
    let mut c_hash_prev = input.hash_prev.clone();
    let mut c_hash_hashval = input.hash_hashval.clone();
    let mut rust_hash_head = input.hash_head.clone();
    let mut rust_hash_prev = input.hash_prev.clone();
    let mut rust_hash_hashval = input.hash_hashval.clone();

    let mut c_same = vec![0u16; ZOPFLI_WINDOW_SIZE];
    let mut rust_same = vec![0u16; ZOPFLI_WINDOW_SIZE];
    
    let c_h = ffi::ZopfliHash {
        head: c_hash_head.as_mut_ptr(),
        prev: c_hash_prev.as_mut_ptr(),
        hashval: c_hash_hashval.as_mut_ptr(),
        val: input.hash_val,
        head2: std::ptr::null_mut(),
        prev2: std::ptr::null_mut(),
        hashval2: std::ptr::null_mut(),
        val2: 0,
        same: c_same.as_mut_ptr(),
    };
    let rust_h = ffi::ZopfliHash {
        head: rust_hash_head.as_mut_ptr(),
        prev: rust_hash_prev.as_mut_ptr(),
        hashval: rust_hash_hashval.as_mut_ptr(),
        val: input.hash_val,
        head2: std::ptr::null_mut(),
        prev2: std::ptr::null_mut(),
        hashval2: std::ptr::null_mut(),
        val2: 0,
        same: rust_same.as_mut_ptr(),
    };

    let mut c_sublen = [0u16; 259];
    let mut rust_sublen = [0u16; 259];
    let mut c_distance = 0u16;
    let mut rust_distance = 0u16;
    let mut c_length = 0u16;
    let mut rust_length = 0u16;
    
    unsafe {
        ffi::ZopfliFindLongestMatch(
            &mut c_s,
            &c_h,
            input.array.as_ptr() as *const c_uchar,
            input.pos as size_t,
            input.size as size_t,
            input.limit as size_t,
            c_sublen.as_mut_ptr() as *mut c_ushort,
            &mut c_distance,
            &mut c_length,
        );
    }

    unsafe {
        zopfli::lz77::ZopfliFindLongestMatch(
            &mut rust_s,
            &rust_h,
            input.array.as_ptr() as *const c_uchar,
            input.pos as size_t,
            input.size as size_t,
            input.limit as size_t,
            rust_sublen.as_mut_ptr() as *mut c_ushort,
            &mut rust_distance,
            &mut rust_length,
        );
    }
    
    assert_eq!(c_distance, rust_distance, "distances differ");
    assert_eq!(c_length, rust_length, "lengths differ");
    assert_eq!(c_sublen.as_ref(), rust_sublen.as_ref(), "sublens differ");
});
