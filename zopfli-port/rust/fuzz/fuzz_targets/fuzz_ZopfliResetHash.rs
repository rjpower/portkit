#![no_main]
use libfuzzer_sys::fuzz_target;
use std::mem::MaybeUninit;
use libc::size_t;

use zopfli::ffi;
use zopfli::hash;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    window_size: u16, // Use u16 to limit size to reasonable values
}

fuzz_target!(|input: FuzzInput| {
    // Limit window_size to reasonable values to avoid excessive memory allocation
    let window_size = (input.window_size as size_t).max(1).min(65536);
    
    // Create two ZopfliHash structures
    let mut c_hash = MaybeUninit::<ffi::ZopfliHash>::uninit();
    let mut rust_hash = MaybeUninit::<ffi::ZopfliHash>::uninit();
    
    unsafe {
        // Initialize both structures with ZopfliAllocHash first
        hash::ZopfliAllocHash(window_size, c_hash.as_mut_ptr());
        hash::ZopfliAllocHash(window_size, rust_hash.as_mut_ptr());
        
        let c_hash_ptr = c_hash.as_mut_ptr();
        let rust_hash_ptr = rust_hash.as_mut_ptr();
        
        // Test ZopfliResetHash
        ffi::ZopfliResetHash(window_size, c_hash_ptr);  // C version
        hash::ZopfliResetHash(window_size, rust_hash_ptr);  // Rust version
        
        // Compare the results
        let c_hash_ref = &*c_hash_ptr;
        let rust_hash_ref = &*rust_hash_ptr;
        
        // Compare val fields
        assert_eq!(c_hash_ref.val, rust_hash_ref.val);
        assert_eq!(c_hash_ref.val2, rust_hash_ref.val2);
        
        // Compare head arrays
        for i in 0..65536 {
            let c_head = *c_hash_ref.head.add(i);
            let rust_head = *rust_hash_ref.head.add(i);
            assert_eq!(c_head, rust_head);
        }
        
        // Compare prev and hashval arrays
        for i in 0..window_size {
            let c_prev = *c_hash_ref.prev.add(i);
            let rust_prev = *rust_hash_ref.prev.add(i);
            assert_eq!(c_prev, rust_prev);
            
            let c_hashval = *c_hash_ref.hashval.add(i);
            let rust_hashval = *rust_hash_ref.hashval.add(i);
            assert_eq!(c_hashval, rust_hashval);
        }
        
        // Compare same array if it exists
        if !c_hash_ref.same.is_null() && !rust_hash_ref.same.is_null() {
            for i in 0..window_size {
                let c_same = *c_hash_ref.same.add(i);
                let rust_same = *rust_hash_ref.same.add(i);
                assert_eq!(c_same, rust_same);
            }
        }
        
        // Compare head2 arrays if they exist
        if !c_hash_ref.head2.is_null() && !rust_hash_ref.head2.is_null() {
            for i in 0..65536 {
                let c_head2 = *c_hash_ref.head2.add(i);
                let rust_head2 = *rust_hash_ref.head2.add(i);
                assert_eq!(c_head2, rust_head2);
            }
        }
        
        // Compare prev2 and hashval2 arrays if they exist
        if !c_hash_ref.prev2.is_null() && !rust_hash_ref.prev2.is_null() &&
           !c_hash_ref.hashval2.is_null() && !rust_hash_ref.hashval2.is_null() {
            for i in 0..window_size {
                let c_prev2 = *c_hash_ref.prev2.add(i);
                let rust_prev2 = *rust_hash_ref.prev2.add(i);
                assert_eq!(c_prev2, rust_prev2);
                
                let c_hashval2 = *c_hash_ref.hashval2.add(i);
                let rust_hashval2 = *rust_hash_ref.hashval2.add(i);
                assert_eq!(c_hashval2, rust_hashval2);
            }
        }
        
        // Clean up memory (assuming there's a cleanup function available or doing manual cleanup)
        libc::free(c_hash_ref.head as *mut libc::c_void);
        libc::free(c_hash_ref.prev as *mut libc::c_void);
        libc::free(c_hash_ref.hashval as *mut libc::c_void);
        libc::free(rust_hash_ref.head as *mut libc::c_void);
        libc::free(rust_hash_ref.prev as *mut libc::c_void);
        libc::free(rust_hash_ref.hashval as *mut libc::c_void);
        
        if !c_hash_ref.same.is_null() {
            libc::free(c_hash_ref.same as *mut libc::c_void);
        }
        if !rust_hash_ref.same.is_null() {
            libc::free(rust_hash_ref.same as *mut libc::c_void);
        }
        
        if !c_hash_ref.head2.is_null() {
            libc::free(c_hash_ref.head2 as *mut libc::c_void);
        }
        if !rust_hash_ref.head2.is_null() {
            libc::free(rust_hash_ref.head2 as *mut libc::c_void);
        }
        
        if !c_hash_ref.prev2.is_null() {
            libc::free(c_hash_ref.prev2 as *mut libc::c_void);
        }
        if !rust_hash_ref.prev2.is_null() {
            libc::free(rust_hash_ref.prev2 as *mut libc::c_void);
        }
        
        if !c_hash_ref.hashval2.is_null() {
            libc::free(c_hash_ref.hashval2 as *mut libc::c_void);
        }
        if !rust_hash_ref.hashval2.is_null() {
            libc::free(rust_hash_ref.hashval2 as *mut libc::c_void);
        }
    }
});