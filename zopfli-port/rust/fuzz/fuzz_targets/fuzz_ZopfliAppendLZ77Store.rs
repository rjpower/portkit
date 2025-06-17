#![no_main]

use libfuzzer_sys::fuzz_target;

use arbitrary::{Arbitrary, Unstructured};

#[derive(Clone, Debug)]
struct FuzzInput {
    litlens: Vec<u16>,
    dists: Vec<u16>,
    data: Vec<u8>,
}

impl<'a> Arbitrary<'a> for FuzzInput {
    fn arbitrary(u: &mut Unstructured<'a>) -> arbitrary::Result<Self> {
        let mut litlens = Vec::<u16>::arbitrary(u)?;
        for l in &mut litlens {
            *l %= 259;
            if *l == 0 && u.arbitrary()? {
                // To avoid too many literal 0s.
                *l = 1;
            }
        }
        let mut dists = Vec::new();
        for _ in 0..litlens.len() {
            dists.push(u.arbitrary()?);
        }

        let data = Vec::<u8>::arbitrary(u)?;

        Ok(FuzzInput {
            litlens,
            dists,
            data,
        })
    }
}

unsafe fn init_store_with_data(store: *mut zopfli::ffi::ZopfliLZ77Store, input: &FuzzInput) {
    let size = input.litlens.len();
    zopfli::ffi::ZopfliInitLZ77Store(input.data.as_ptr(), store);

    for i in 0..size {
        let length = input.litlens[i];
        let dist = input.dists[i];

        // This is a bit of a hack. The C code expects pos to be valid.
        // We'll just make sure pos is within the bounds of data.
        let pos = if input.data.is_empty() {
            0
        } else {
            i % input.data.len()
        };

        zopfli::ffi::ZopfliStoreLitLenDist(length, dist, pos, store);
    }
}

unsafe fn compare_stores(rust: *const zopfli::ffi::ZopfliLZ77Store, c: *const zopfli::ffi::ZopfliLZ77Store) {
    assert_eq!((*rust).size, (*c).size);
    let size = (*rust).size;
    if size == 0 {
        return;
    }
    let rust_litlens = std::slice::from_raw_parts((*rust).litlens, size);
    let c_litlens = std::slice::from_raw_parts((*c).litlens, size);
    assert_eq!(rust_litlens, c_litlens);

    let rust_dists = std::slice::from_raw_parts((*rust).dists, size);
    let c_dists = std::slice::from_raw_parts((*c).dists, size);
    assert_eq!(rust_dists, c_dists);

    let rust_pos = std::slice::from_raw_parts((*rust).pos, size);
    let c_pos = std::slice::from_raw_parts((*c).pos, size);
    assert_eq!(rust_pos, c_pos);
}

fuzz_target!(|input: FuzzInput| {
    if input.litlens.len() != input.dists.len() {
        return;
    }

    let mut rust_store = std::mem::MaybeUninit::<zopfli::ffi::ZopfliLZ77Store>::uninit();
    let mut c_store = std::mem::MaybeUninit::<zopfli::ffi::ZopfliLZ77Store>::uninit();

    let mut rust_target = std::mem::MaybeUninit::<zopfli::ffi::ZopfliLZ77Store>::uninit();
    let mut c_target = std::mem::MaybeUninit::<zopfli::ffi::ZopfliLZ77Store>::uninit();

    unsafe {
        init_store_with_data(rust_store.as_mut_ptr(), &input);
        init_store_with_data(c_store.as_mut_ptr(), &input);

        // We use fresh stores for the targets.
        zopfli::lz77::ZopfliInitLZ77Store(std::ptr::null(), rust_target.as_mut_ptr());
        zopfli::ffi::ZopfliInitLZ77Store(std::ptr::null(), c_target.as_mut_ptr());

        zopfli::lz77::ZopfliAppendLZ77Store(rust_store.as_ptr(), rust_target.as_mut_ptr());
        zopfli::ffi::ZopfliAppendLZ77Store(c_store.as_ptr(), c_target.as_mut_ptr());

        compare_stores(rust_target.as_ptr(), c_target.as_ptr());

        zopfli::lz77::ZopfliCleanLZ77Store(rust_store.as_mut_ptr());
        zopfli::ffi::ZopfliCleanLZ77Store(c_store.as_mut_ptr());
        zopfli::lz77::ZopfliCleanLZ77Store(rust_target.as_mut_ptr());
        zopfli::ffi::ZopfliCleanLZ77Store(c_target.as_mut_ptr());
    }
});
