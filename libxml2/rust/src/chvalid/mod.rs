//! Rust implementation of chvalid module
//!
//! Character validation for Unicode code points using range tables

pub mod core;
pub mod ffi;
mod ranges;

pub use core::*;
