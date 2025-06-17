fn main() {
    use cc::Build;
    use std::path::Path;
    use std::fs;
    
    println!("cargo:rerun-if-changed=../src/zopfli/symbols.h");
    println!("cargo:rerun-if-changed=../src/zopfli/util.c");
    println!("cargo:rerun-if-changed=../src/zopfli/util.h");
    println!("cargo:rerun-if-changed=../src/zopfli/tree.c");
    println!("cargo:rerun-if-changed=../src/zopfli/tree.h");
    println!("cargo:rerun-if-changed=../src/zopfli/katajainen.c");
    println!("cargo:rerun-if-changed=../src/zopfli/katajainen.h");
    println!("cargo:rerun-if-changed=../src/zopfli/zopfli.h");
    println!("cargo:rerun-if-changed=../src/zopfli/hash.c");
    println!("cargo:rerun-if-changed=../src/zopfli/hash.h");
    println!("cargo:rerun-if-changed=../src/zopfli/cache.c");
    println!("cargo:rerun-if-changed=../src/zopfli/cache.h");
    println!("cargo:rerun-if-changed=../src/zopfli/lz77.c");
    println!("cargo:rerun-if-changed=../src/zopfli/lz77.h");
    println!("cargo:rerun-if-changed=../src/zopfli/squeeze.c");
    println!("cargo:rerun-if-changed=../src/zopfli/squeeze.h");
    println!("cargo:rerun-if-changed=../src/zopfli/deflate.c");
    println!("cargo:rerun-if-changed=../src/zopfli/deflate.h");
    println!("cargo:rerun-if-changed=../src/zopfli/blocksplitter.c");
    println!("cargo:rerun-if-changed=../src/zopfli/blocksplitter.h");

    // write a symbols.c file that contains the inline functions from symbols.h
    let symbols_c = Path::new("../src/zopfli/symbols.c");
    let symbols_h = Path::new("../src/zopfli/symbols.h");
    let symbols_c_text = fs::read_to_string(symbols_h).unwrap().replace("static ", "");
    fs::write(symbols_c, symbols_c_text).unwrap();
    
    Build::new()
        .flag("-Wno-unused-function")
        .file("../src/zopfli/util.c")
        .file("../src/zopfli/tree.c")
        .file("../src/zopfli/katajainen.c")
        .file("../src/zopfli/hash.c")
        .file("../src/zopfli/cache.c")
        .file("../src/zopfli/lz77.c")
        .file("../src/zopfli/squeeze.c")
        .file("../src/zopfli/deflate.c")
        .file("../src/zopfli/blocksplitter.c")
        .file("../src/zopfli/gzip_container.c")
        .file("../src/zopfli/zlib_container.c")
        .file("../src/zopfli/zopfli_lib.c")
        .file("../src/zopfli/symbols.c")
        .include("../src/zopfli")
        .compile("zopfli_c");
}