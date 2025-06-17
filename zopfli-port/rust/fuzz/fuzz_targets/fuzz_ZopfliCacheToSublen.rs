#![no_main]
use libfuzzer_sys::fuzz_target;
use zopfli::cache::{ZopfliCacheToSublen, ZopfliInitCache, ZopfliSublenToCache};
use zopfli::ffi;
use zopfli::util::ZOPFLI_MAX_MATCH;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    pos: u16,
    length: u16,
    sublen: Vec<u16>,
}

fuzz_target!(|input: FuzzInput| {
    let mut input = input;
    if input.length > ZOPFLI_MAX_MATCH as u16 {
        input.length = ZOPFLI_MAX_MATCH as u16;
    }
    if input.sublen.len() < (input.length + 2) as usize {
        input
            .sublen
            .resize((input.length + 2) as usize, 0);
    }
    let blocksize = (input.pos as usize)
        .checked_add(1)
        .and_then(|v| v.checked_add(ZOPFLI_MAX_MATCH as usize))
        .unwrap_or(u16::MAX as usize)
        .max(1);

    unsafe {
        let mut c_lmc: ffi::ZopfliLongestMatchCache = std::mem::zeroed();
        let mut rust_lmc: ffi::ZopfliLongestMatchCache = std::mem::zeroed();

        ZopfliInitCache(blocksize, &mut c_lmc);
        ZopfliInitCache(blocksize, &mut rust_lmc);

        ZopfliSublenToCache(
            input.sublen.as_ptr(),
            input.pos as usize,
            input.length as usize,
            &mut c_lmc,
        );
        ZopfliSublenToCache(
            input.sublen.as_ptr(),
            input.pos as usize,
            input.length as usize,
            &mut rust_lmc,
        );

        let mut c_sublen = vec![0; (input.length + 2) as usize];
        let mut rust_sublen = vec![0; (input.length + 2) as usize];

        ffi::ZopfliCacheToSublen(
            &c_lmc,
            input.pos as usize,
            input.length as usize,
            c_sublen.as_mut_ptr(),
        );
        ZopfliCacheToSublen(
            &rust_lmc,
            input.pos as usize,
            input.length as usize,
            rust_sublen.as_mut_ptr(),
        );

        assert_eq!(c_sublen, rust_sublen);

        zopfli::cache::ZopfliCleanCache(&mut c_lmc);
        zopfli::cache::ZopfliCleanCache(&mut rust_lmc);
    }
});
