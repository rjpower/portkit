use crate::ffi::{ZopfliOptions};
use crate::zopfli::ZopfliFormat;
use crate::gzip_container::ZopfliGzipCompress;
use crate::zlib_container::ZopfliZlibCompress;
use crate::deflate::ZopfliDeflate;
use std::os::raw::{c_uchar, c_int};
use libc::size_t;
use std::ptr;

pub fn ZopfliCompress(
    options: &ZopfliOptions,
    output_type: ZopfliFormat,
    input: &[u8],
    out: &mut Vec<u8>,
) {
    let mut c_out: *mut c_uchar = ptr::null_mut();
    let mut c_outsize: size_t = 0;
    
    unsafe {
        match output_type {
            ZopfliFormat::ZOPFLI_FORMAT_GZIP => {
                ZopfliGzipCompress(
                    options,
                    input.as_ptr(),
                    input.len(),
                    &mut c_out,
                    &mut c_outsize,
                );
            }
            ZopfliFormat::ZOPFLI_FORMAT_ZLIB => {
                ZopfliZlibCompress(
                    options,
                    input.as_ptr(),
                    input.len(),
                    &mut c_out,
                    &mut c_outsize,
                );
            }
            ZopfliFormat::ZOPFLI_FORMAT_DEFLATE => {
                let mut bp = 0u8;
                ZopfliDeflate(
                    options,
                    2, // Dynamic block
                    1, // Final
                    input.as_ptr(),
                    input.len(),
                    &mut bp,
                    &mut c_out,
                    &mut c_outsize,
                );
            }
        }
        
        if !c_out.is_null() && c_outsize > 0 {
            let result_slice = std::slice::from_raw_parts(c_out, c_outsize);
            out.extend_from_slice(result_slice);
            libc::free(c_out as *mut libc::c_void);
        }
    }
}