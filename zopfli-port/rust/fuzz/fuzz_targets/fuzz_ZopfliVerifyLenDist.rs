#![no_main]
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    if data.len() < 4 {
        return;
    }

    let pos = u16::from_le_bytes([data[0], data[1]]) as usize;
    let length = data[2] as u16;
    let dist = data[3] as u16;

    let datasize = data.len();

    // Pre-conditions to avoid trivial assertion failures.
    // The goal is to find inputs that should pass but cause a crash.
    if pos >= datasize || length == 0 || dist == 0 || pos < dist as usize {
        return;
    }

    if pos + (length as usize) > datasize {
        return;
    }

    // Check if the data matches, which is the main assertion inside ZopfliVerifyLenDist.
    // If it doesn't match, the C function will abort and the Rust function will panic,
    // which is the expected behavior. We only want to proceed if the data *does* match,
    // to ensure that no *other* unexpected crashes occur.
    let mut matching = true;
    for i in 0..length as usize {
        if data[pos - dist as usize + i] != data[pos + i] {
            matching = false;
            break;
        }
    }

    if matching {
        // Call C implementation
        unsafe {
            zopfli::ffi::ZopfliVerifyLenDist(
                data.as_ptr(),
                datasize,
                pos,
                dist,
                length,
            );
        }

        // Call Rust implementation
        zopfli::lz77::ZopfliVerifyLenDist(
            data,
            pos,
            dist,
            length,
        );
    }
});
