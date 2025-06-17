use std::ptr;
use zopfli::ffi;
use zopfli::deflate;

fn main() {
    let input_data = vec![189u8, 189, 43, 189, 189, 77, 77, 77, 77, 0, 77, 189, 77, 77, 77, 77, 0, 77, 255, 189, 189, 255, 255, 255, 189, 121, 121, 121, 121, 121, 121, 121, 121, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 189, 189, 255, 189, 189, 189, 189, 121, 121, 121];
    
    let options = ffi::ZopfliOptions {
        verbose: 1,
        verbose_more: 0,
        numiterations: 1,
        blocksplitting: 1,
        blocksplittinglast: 0,
        blocksplittingmax: 3,
    };

    unsafe {
        // Test C version
        let mut c_out: *mut u8 = ptr::null_mut();
        let mut c_outsize: usize = 0;
        let mut c_bp: u8 = 0;
        
        println!("=== C Implementation ===");
        ffi::ZopfliDeflatePart(
            &options,
            2, // btype
            1, // final
            input_data.as_ptr(),
            0, // instart  
            54, // inend
            &mut c_bp,
            &mut c_out,
            &mut c_outsize,
        );
        
        println!("C: bp={}, outsize={}", c_bp, c_outsize);
        if c_outsize > 0 {
            let c_result = std::slice::from_raw_parts(c_out, c_outsize);
            println!("C output: {:?}", &c_result[..c_result.len().min(10)]);
        }
        
        // Test Rust version
        let mut rust_out: *mut u8 = ptr::null_mut();
        let mut rust_outsize: usize = 0;
        let mut rust_bp: u8 = 0;
        
        println!("\n=== Rust Implementation ===");
        deflate::ZopfliDeflatePart(
            &options,
            2, // btype
            1, // final
            input_data.as_ptr(),
            0, // instart
            54, // inend
            &mut rust_bp,
            &mut rust_out,
            &mut rust_outsize,
        );
        
        println!("Rust: bp={}, outsize={}", rust_bp, rust_outsize);
        if rust_outsize > 0 {
            let rust_result = std::slice::from_raw_parts(rust_out, rust_outsize);
            println!("Rust output: {:?}", &rust_result[..rust_result.len().min(10)]);
        }
        
        // Compare
        println!("\n=== Comparison ===");
        println!("BP match: {}", c_bp == rust_bp);
        println!("Size match: {}", c_outsize == rust_outsize);
        
        if c_outsize > 0 && rust_outsize > 0 && c_outsize == rust_outsize {
            let c_result = std::slice::from_raw_parts(c_out, c_outsize);
            let rust_result = std::slice::from_raw_parts(rust_out, rust_outsize);
            println!("Data match: {}", c_result == rust_result);
        }
        
        // Cleanup
        if !c_out.is_null() {
            libc::free(c_out as *mut libc::c_void);
        }
        if !rust_out.is_null() {
            libc::free(rust_out as *mut libc::c_void);
        }
    }
}