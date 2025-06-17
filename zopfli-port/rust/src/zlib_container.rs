use crate::ffi::ZopfliOptions;
use crate::util::ZOPFLI_APPEND_DATA;
use crate::deflate::ZopfliDeflate;
use libc::{c_uchar, size_t};
use std::io::{self, Write};

fn adler32(data: &[u8]) -> u32 {
    const SUMS_OVERFLOW: usize = 5550;
    let mut s1 = 1u32;
    let mut s2 = 0u32;
    
    let mut remaining = data.len();
    let mut pos = 0;
    
    while remaining > 0 {
        let amount = if remaining > SUMS_OVERFLOW { SUMS_OVERFLOW } else { remaining };
        remaining -= amount;
        
        for _ in 0..amount {
            s1 = s1.wrapping_add(data[pos] as u32);
            s2 = s2.wrapping_add(s1);
            pos += 1;
        }
        
        s1 %= 65521;
        s2 %= 65521;
    }
    
    (s2 << 16) | s1
}

pub unsafe fn ZopfliZlibCompress(
    options: *const ZopfliOptions,
    r#in: *const c_uchar,
    insize: size_t,
    out: *mut *mut c_uchar,
    outsize: *mut size_t,
) {
    let mut bitpointer = 0u8;
    let input_slice = std::slice::from_raw_parts(r#in, insize);
    let checksum = adler32(input_slice);
    let cmf = 120u32;  // CM 8, CINFO 7. See zlib spec.
    let flevel = 3u32;
    let fdict = 0u32;
    let mut cmfflg = 256 * cmf + fdict * 32 + flevel * 64;
    let fcheck = 31 - cmfflg % 31;
    cmfflg += fcheck;

    ZOPFLI_APPEND_DATA((cmfflg / 256) as u8, &mut *out, &mut *outsize);
    ZOPFLI_APPEND_DATA((cmfflg % 256) as u8, &mut *out, &mut *outsize);

    ZopfliDeflate(options, 2 /* dynamic block */, 1 /* final */,
                  r#in, insize, &mut bitpointer, out, outsize);

    ZOPFLI_APPEND_DATA(((checksum >> 24) % 256) as u8, &mut *out, &mut *outsize);
    ZOPFLI_APPEND_DATA(((checksum >> 16) % 256) as u8, &mut *out, &mut *outsize);
    ZOPFLI_APPEND_DATA(((checksum >> 8) % 256) as u8, &mut *out, &mut *outsize);
    ZOPFLI_APPEND_DATA((checksum % 256) as u8, &mut *out, &mut *outsize);

    if (*options).verbose != 0 {
        let removed_percent = 100.0 * (insize as f64 - *outsize as f64) / insize as f64;
        eprintln!(
            "Original Size: {}, Zlib: {}, Compression: {:.6}% Removed",
            insize, *outsize, removed_percent
        );
    }
}