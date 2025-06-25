//! Chimera build of libxml2 - mixed C/Rust implementation
//! 
//! This library provides a gradual migration path from C to Rust.
//! Modules can be implemented in either C or Rust, controlled by feature flags.

#![allow(non_upper_case_globals)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(improper_ctypes)]
#![allow(dead_code)]
#![allow(unused_variables)]
#![allow(unused_imports)]

// Bindgen-generated FFI bindings
pub mod static_bindings {
    include!(concat!(env!("OUT_DIR"), "/static_bindings.rs"));
}

// Dynamic bindings for baseline testing
pub mod dynamic_bindings {
    include!(concat!(env!("OUT_DIR"), "/dynamic_bindings.rs"));
}

// C baseline dynamic library loader for differential testing
pub mod libxml2_dynload;

// Re-export all bindings by default
// Rust implementations will override these when their features are enabled
pub use static_bindings::*;

// Conditionally include Rust implementations
#[cfg(feature = "rust-xmlstring")]
pub mod xmlstring;

#[cfg(feature = "rust-chvalid")]
pub mod chvalid;

#[cfg(feature = "rust-dict")]
pub mod dict;

#[cfg(feature = "rust-hash")]
pub mod hash;

#[cfg(feature = "rust-list")]
pub mod list;

#[cfg(feature = "rust-buf")]
pub mod buf;

#[cfg(feature = "rust-xmlmemory")]
pub mod xmlmemory;

#[cfg(feature = "rust-error")]
pub mod error;

#[cfg(feature = "rust-threads")]
pub mod threads;

#[cfg(feature = "rust-encoding")]
pub mod encoding;

#[cfg(feature = "rust-xmlio")]
pub mod xmlio;

#[cfg(feature = "rust-uri")]
pub mod uri;

#[cfg(feature = "rust-entities")]
pub mod entities;

#[cfg(feature = "rust-tree")]
pub mod tree;

#[cfg(feature = "rust-xmlsave")]
pub mod xmlsave;

#[cfg(feature = "rust-parser-internals")]
pub mod parser_internals;

#[cfg(feature = "rust-parser")]
pub mod parser;

#[cfg(feature = "rust-sax2")]
pub mod sax2;

#[cfg(feature = "rust-xpath")]
pub mod xpath;

#[cfg(feature = "rust-pattern")]
pub mod pattern;

#[cfg(feature = "rust-xpointer")]
pub mod xpointer;

#[cfg(feature = "rust-valid")]
pub mod valid;

#[cfg(feature = "rust-xmlregexp")]
pub mod xmlregexp;

#[cfg(feature = "rust-xmlschemas")]
pub mod xmlschemas;

#[cfg(feature = "rust-relaxng")]
pub mod relaxng;

#[cfg(feature = "rust-schematron")]
pub mod schematron;

#[cfg(feature = "rust-htmlparser")]
pub mod htmlparser;

#[cfg(feature = "rust-htmltree")]
pub mod htmltree;

#[cfg(feature = "rust-xmlreader")]
pub mod xmlreader;

#[cfg(feature = "rust-xmlwriter")]
pub mod xmlwriter;

#[cfg(feature = "rust-c14n")]
pub mod c14n;

// Re-export Rust implementations when enabled
#[cfg(feature = "rust-xmlstring")]
pub use xmlstring::*;

#[cfg(feature = "rust-chvalid")]
pub use chvalid::*;

#[cfg(feature = "rust-dict")]
pub use dict::*;

#[cfg(feature = "rust-hash")]
pub use hash::*;

#[cfg(feature = "rust-list")]
pub use list::*;

#[cfg(feature = "rust-buf")]
pub use buf::*;

#[cfg(feature = "rust-xmlmemory")]
pub use xmlmemory::*;

#[cfg(feature = "rust-error")]
pub use error::*;

#[cfg(feature = "rust-threads")]
pub use threads::*;

#[cfg(feature = "rust-encoding")]
pub use encoding::*;

#[cfg(feature = "rust-xmlio")]
pub use xmlio::*;

#[cfg(feature = "rust-uri")]
pub use uri::*;

#[cfg(feature = "rust-entities")]
pub use entities::*;

#[cfg(feature = "rust-tree")]
pub use tree::*;

#[cfg(feature = "rust-xmlsave")]
pub use xmlsave::*;

#[cfg(feature = "rust-parser-internals")]
pub use parser_internals::*;

#[cfg(feature = "rust-parser")]
pub use parser::*;

#[cfg(feature = "rust-sax2")]
pub use sax2::*;

#[cfg(feature = "rust-xpath")]
pub use xpath::*;

#[cfg(feature = "rust-pattern")]
pub use pattern::*;

#[cfg(feature = "rust-xpointer")]
pub use xpointer::*;

#[cfg(feature = "rust-valid")]
pub use valid::*;

#[cfg(feature = "rust-xmlregexp")]
pub use xmlregexp::*;

#[cfg(feature = "rust-xmlschemas")]
pub use xmlschemas::*;

#[cfg(feature = "rust-relaxng")]
pub use relaxng::*;

#[cfg(feature = "rust-schematron")]
pub use schematron::*;

#[cfg(feature = "rust-htmlparser")]
pub use htmlparser::*;

#[cfg(feature = "rust-htmltree")]
pub use htmltree::*;

#[cfg(feature = "rust-xmlreader")]
pub use xmlreader::*;

#[cfg(feature = "rust-xmlwriter")]
pub use xmlwriter::*;

#[cfg(feature = "rust-c14n")]
pub use c14n::*;

// Initialization function if needed
pub fn init_chimera() {
    // Any global initialization required
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_bindings_available() {
        // Verify bindings were generated successfully
        // This will be expanded by module-specific tests
    }
}
