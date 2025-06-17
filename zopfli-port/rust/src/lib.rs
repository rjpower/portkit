#![allow(non_snake_case)]
#![allow(dead_code)]
#![allow(unused_variables)]
#![allow(unused_imports)]
#![allow(non_camel_case_types)]

pub mod lz77;
pub mod ffi;
pub mod symbols;

pub mod cache;

pub mod tree;

pub mod blocksplitter;

pub mod katajainen;

pub mod zopfli;

pub mod hash;
pub mod util;

pub mod deflate;

pub mod squeeze;

pub mod zlib_container;

pub mod gzip_container;

pub mod zopfli_lib;
