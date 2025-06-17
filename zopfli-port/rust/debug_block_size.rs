use std::ptr;
use zopfli::ffi;
use zopfli::deflate;

fn main() {
    let input_data = vec![189u8, 189, 43, 189, 189, 77, 77, 77, 77, 0, 77, 189, 77, 77, 77, 77, 0, 77, 255, 189, 189, 255, 255, 255, 189, 121, 121, 121, 121, 121, 121, 121, 121, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 189, 189, 255, 189, 189, 189, 189, 121, 121, 121];
    
    let options = ffi::ZopfliOptions {
        verbose: 0,
        verbose_more: 0,
        numiterations: 1,
        blocksplitting: 1,
        blocksplittinglast: 0,
        blocksplittingmax: 3,
    };

    unsafe {
        // Create the LZ77 store using the actual algorithm
        let mut lz77: ffi::ZopfliLZ77Store = std::mem::zeroed();
        ffi::ZopfliInitLZ77Store(input_data.as_ptr(), &mut lz77);
        
        // Fill it with realistic data using the actual compression process
        let mut s: ffi::ZopfliBlockState = std::mem::zeroed();
        ffi::ZopfliInitBlockState(&options, 0, 54, 1, &mut s);
        ffi::ZopfliLZ77Optimal(&mut s, input_data.as_ptr(), 0, 54, options.numiterations, &mut lz77);
        
        if lz77.size > 0 {
            println!("LZ77 store size: {}", lz77.size);
            
            // Test btype=1 specifically  
            let result_rust = deflate::ZopfliCalculateBlockSize(&lz77, 0, lz77.size, 1);
            let result_c = ffi::ZopfliCalculateBlockSize(&lz77, 0, lz77.size, 1);
            
            println!("btype=1: rust={}, c={}, diff={}", 
                result_rust, result_c, result_rust - result_c);
                
            // Also test the components
            let mut ll_lengths: [u32; 288] = [0; 288];
            let mut d_lengths: [u32; 32] = [0; 32];
            
            deflate::GetFixedTree(ll_lengths.as_mut_ptr(), d_lengths.as_mut_ptr());
            let rust_symbol_size = deflate::CalculateBlockSymbolSize(
                ll_lengths.as_ptr(), d_lengths.as_ptr(), &lz77, 0, lz77.size);
                
            ffi::GetFixedTree(ll_lengths.as_mut_ptr(), d_lengths.as_mut_ptr());
            let c_symbol_size = ffi::CalculateBlockSymbolSize(
                ll_lengths.as_ptr(), d_lengths.as_ptr(), &lz77, 0, lz77.size);
                
            println!("Symbol size: rust={}, c={}, diff={}", 
                rust_symbol_size, c_symbol_size, rust_symbol_size as i64 - c_symbol_size as i64);
        }
        
        ffi::ZopfliCleanBlockState(&mut s);
        ffi::ZopfliCleanLZ77Store(&mut lz77);
    }
}