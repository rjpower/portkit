#![no_main]
use libfuzzer_sys::fuzz_target;
use libc::size_t;

use zopfli::ffi;
use zopfli::hash;

#[derive(Debug, arbitrary::Arbitrary)]
struct FuzzInput {
    window_size: u16,  // Use u16 to keep window sizes reasonable
}

fuzz_target!(|input: FuzzInput| {
    // Keep window size reasonable to avoid excessive memory allocation
    let window_size = (input.window_size as size_t).max(1).min(65536);
    
    // Create hash structures
    let mut c_hash = ffi::ZopfliHash {
        head: std::ptr::null_mut(),
        prev: std::ptr::null_mut(),
        hashval: std::ptr::null_mut(),
        val: 0,
        head2: std::ptr::null_mut(),
        prev2: std::ptr::null_mut(),
        hashval2: std::ptr::null_mut(),
        val2: 0,
        same: std::ptr::null_mut(),
    };
    
    let mut rust_hash = ffi::ZopfliHash {
        head: std::ptr::null_mut(),
        prev: std::ptr::null_mut(),
        hashval: std::ptr::null_mut(),
        val: 0,
        head2: std::ptr::null_mut(),
        prev2: std::ptr::null_mut(),
        hashval2: std::ptr::null_mut(),
        val2: 0,
        same: std::ptr::null_mut(),
    };
    
    unsafe {
        // Call both C and Rust implementations
        ffi::ZopfliAllocHash(window_size, &mut c_hash);
        hash::ZopfliAllocHash(window_size, &mut rust_hash);
        
        // Verify that both allocated the same pointers (non-null where expected)
        assert_eq!(c_hash.head.is_null(), rust_hash.head.is_null());
        assert_eq!(c_hash.prev.is_null(), rust_hash.prev.is_null());
        assert_eq!(c_hash.hashval.is_null(), rust_hash.hashval.is_null());
        assert_eq!(c_hash.same.is_null(), rust_hash.same.is_null());
        assert_eq!(c_hash.head2.is_null(), rust_hash.head2.is_null());
        assert_eq!(c_hash.prev2.is_null(), rust_hash.prev2.is_null());
        assert_eq!(c_hash.hashval2.is_null(), rust_hash.hashval2.is_null());
        
        // Both should have allocated non-null pointers for the main arrays
        assert!(!c_hash.head.is_null());
        assert!(!c_hash.prev.is_null());
        assert!(!c_hash.hashval.is_null());
        assert!(!rust_hash.head.is_null());
        assert!(!rust_hash.prev.is_null());
        assert!(!rust_hash.hashval.is_null());
        
        // Clean up memory
        if !c_hash.head.is_null() {
            libc::free(c_hash.head as *mut libc::c_void);
        }
        if !c_hash.prev.is_null() {
            libc::free(c_hash.prev as *mut libc::c_void);
        }
        if !c_hash.hashval.is_null() {
            libc::free(c_hash.hashval as *mut libc::c_void);
        }
        if !c_hash.same.is_null() {
            libc::free(c_hash.same as *mut libc::c_void);
        }
        if !c_hash.head2.is_null() {
            libc::free(c_hash.head2 as *mut libc::c_void);
        }
        if !c_hash.prev2.is_null() {
            libc::free(c_hash.prev2 as *mut libc::c_void);
        }
        if !c_hash.hashval2.is_null() {
            libc::free(c_hash.hashval2 as *mut libc::c_void);
        }
        
        if !rust_hash.head.is_null() {
            libc::free(rust_hash.head as *mut libc::c_void);
        }
        if !rust_hash.prev.is_null() {
            libc::free(rust_hash.prev as *mut libc::c_void);
        }
        if !rust_hash.hashval.is_null() {
            libc::free(rust_hash.hashval as *mut libc::c_void);
        }
        if !rust_hash.same.is_null() {
            libc::free(rust_hash.same as *mut libc::c_void);
        }
        if !rust_hash.head2.is_null() {
            libc::free(rust_hash.head2 as *mut libc::c_void);
        }
        if !rust_hash.prev2.is_null() {
            libc::free(rust_hash.prev2 as *mut libc::c_void);
        }
        if !rust_hash.hashval2.is_null() {
            libc::free(rust_hash.hashval2 as *mut libc::c_void);
        }
    }
});