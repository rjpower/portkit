#![no_main]
use libfuzzer_sys::fuzz_target;
use zopfli::zopfli::ZopfliFormat;

fuzz_target!(|data: &[u8]| {
    if data.is_empty() {
        return;
    }

    let value = data[0] % 3;

    let zopfli_format = match value {
        0 => ZopfliFormat::ZOPFLI_FORMAT_GZIP,
        1 => ZopfliFormat::ZOPFLI_FORMAT_ZLIB,
        2 => ZopfliFormat::ZOPFLI_FORMAT_DEFLATE,
        _ => unreachable!(),
    };

    // Assert that the Rust enum's integer representation matches the C enum's implicit value.
    assert_eq!(zopfli_format as u32, value as u32, "ZopfliFormat discriminant mismatch");
});
