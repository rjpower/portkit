use std::os::raw::{c_int, c_uint, c_ushort};
use super::core;

// Ensure symbols are exported for linking
#[cfg(feature = "rust-chvalid")]
#[used]
static CHVALID_FFI_LINKAGE: () = ();

#[repr(C)]
pub struct xmlChSRange {
    pub low: c_ushort,
    pub high: c_ushort,
}

#[repr(C)]
pub struct xmlChLRange {
    pub low: c_uint,
    pub high: c_uint,
}

#[repr(C)]
pub struct xmlChRangeGroup {
    pub nbShortRange: c_int,
    pub nbLongRange: c_int,
    pub shortRange: *const xmlChSRange,
    pub longRange: *const xmlChLRange,
}

unsafe impl Sync for xmlChRangeGroup {}

fn convert_range_group(rptr: *const xmlChRangeGroup) -> Option<core::ChRangeGroup> {
    if rptr.is_null() {
        return None;
    }
    
    let group = unsafe { &*rptr };
    
    let short_ranges = if group.nbShortRange > 0 && !group.shortRange.is_null() {
        unsafe {
            std::slice::from_raw_parts(
                group.shortRange as *const core::ChSRange,
                group.nbShortRange as usize
            )
        }
    } else {
        &[]
    };
    
    let long_ranges = if group.nbLongRange > 0 && !group.longRange.is_null() {
        unsafe {
            std::slice::from_raw_parts(
                group.longRange as *const core::ChLRange,
                group.nbLongRange as usize
            )
        }
    } else {
        &[]
    };
    
    Some(core::ChRangeGroup {
        short_ranges,
        long_ranges,
    })
}

#[no_mangle]
pub extern "C" fn xmlCharInRange(val: c_uint, rptr: *const xmlChRangeGroup) -> c_int {
    if let Some(group) = convert_range_group(rptr) {
        if core::char_in_range(val, &group) { 1 } else { 0 }
    } else {
        0
    }
}

#[no_mangle]
pub extern "C" fn xmlIsBaseChar(ch: c_uint) -> c_int {
    if core::is_base_char(ch) { 1 } else { 0 }
}

#[no_mangle]
pub extern "C" fn xmlIsBlank(ch: c_uint) -> c_int {
    if core::is_blank(ch) { 1 } else { 0 }
}

#[no_mangle]
pub extern "C" fn xmlIsChar(ch: c_uint) -> c_int {
    if core::is_char(ch) { 1 } else { 0 }
}

#[no_mangle]
pub extern "C" fn xmlIsCombining(ch: c_uint) -> c_int {
    if core::is_combining(ch) { 1 } else { 0 }
}

#[no_mangle]
pub extern "C" fn xmlIsDigit(ch: c_uint) -> c_int {
    if core::is_digit(ch) { 1 } else { 0 }
}

#[no_mangle]
pub extern "C" fn xmlIsExtender(ch: c_uint) -> c_int {
    if core::is_extender(ch) { 1 } else { 0 }
}

#[no_mangle]
pub extern "C" fn xmlIsIdeographic(ch: c_uint) -> c_int {
    if core::is_ideographic(ch) { 1 } else { 0 }
}

#[no_mangle]
pub extern "C" fn xmlIsPubidChar(ch: c_uint) -> c_int {
    if core::is_pubid_char(ch) { 1 } else { 0 }
}

#[no_mangle]
pub static xmlIsPubidChar_tab: [u8; 256] = super::ranges::XML_IS_PUBID_CHAR_TAB;

static XML_IS_BASE_CHAR_SRNG_FFI: &[xmlChSRange] = unsafe {
    std::mem::transmute(super::ranges::XML_IS_BASE_CHAR_GROUP.short_ranges)
};

#[no_mangle]
pub static xmlIsBaseCharGroup: xmlChRangeGroup = xmlChRangeGroup {
    nbShortRange: super::ranges::XML_IS_BASE_CHAR_GROUP.short_ranges.len() as c_int,
    nbLongRange: super::ranges::XML_IS_BASE_CHAR_GROUP.long_ranges.len() as c_int,
    shortRange: XML_IS_BASE_CHAR_SRNG_FFI.as_ptr(),
    longRange: std::ptr::null(),
};

static XML_IS_CHAR_SRNG_FFI: &[xmlChSRange] = unsafe {
    std::mem::transmute(super::ranges::XML_IS_CHAR_GROUP.short_ranges)
};

static XML_IS_CHAR_LRNG_FFI: &[xmlChLRange] = unsafe {
    std::mem::transmute(super::ranges::XML_IS_CHAR_GROUP.long_ranges)
};

#[no_mangle]
pub static xmlIsCharGroup: xmlChRangeGroup = xmlChRangeGroup {
    nbShortRange: super::ranges::XML_IS_CHAR_GROUP.short_ranges.len() as c_int,
    nbLongRange: super::ranges::XML_IS_CHAR_GROUP.long_ranges.len() as c_int,
    shortRange: XML_IS_CHAR_SRNG_FFI.as_ptr(),
    longRange: XML_IS_CHAR_LRNG_FFI.as_ptr(),
};

static XML_IS_COMBINING_SRNG_FFI: &[xmlChSRange] = unsafe {
    std::mem::transmute(super::ranges::XML_IS_COMBINING_GROUP.short_ranges)
};

#[no_mangle]
pub static xmlIsCombiningGroup: xmlChRangeGroup = xmlChRangeGroup {
    nbShortRange: super::ranges::XML_IS_COMBINING_GROUP.short_ranges.len() as c_int,
    nbLongRange: super::ranges::XML_IS_COMBINING_GROUP.long_ranges.len() as c_int,
    shortRange: XML_IS_COMBINING_SRNG_FFI.as_ptr(),
    longRange: std::ptr::null(),
};

static XML_IS_DIGIT_SRNG_FFI: &[xmlChSRange] = unsafe {
    std::mem::transmute(super::ranges::XML_IS_DIGIT_GROUP.short_ranges)
};

#[no_mangle]
pub static xmlIsDigitGroup: xmlChRangeGroup = xmlChRangeGroup {
    nbShortRange: super::ranges::XML_IS_DIGIT_GROUP.short_ranges.len() as c_int,
    nbLongRange: super::ranges::XML_IS_DIGIT_GROUP.long_ranges.len() as c_int,
    shortRange: XML_IS_DIGIT_SRNG_FFI.as_ptr(),
    longRange: std::ptr::null(),
};

static XML_IS_EXTENDER_SRNG_FFI: &[xmlChSRange] = unsafe {
    std::mem::transmute(super::ranges::XML_IS_EXTENDER_GROUP.short_ranges)
};

#[no_mangle]
pub static xmlIsExtenderGroup: xmlChRangeGroup = xmlChRangeGroup {
    nbShortRange: super::ranges::XML_IS_EXTENDER_GROUP.short_ranges.len() as c_int,
    nbLongRange: super::ranges::XML_IS_EXTENDER_GROUP.long_ranges.len() as c_int,
    shortRange: XML_IS_EXTENDER_SRNG_FFI.as_ptr(),
    longRange: std::ptr::null(),
};

static XML_IS_IDEOGRAPHIC_SRNG_FFI: &[xmlChSRange] = unsafe {
    std::mem::transmute(super::ranges::XML_IS_IDEOGRAPHIC_GROUP.short_ranges)
};

#[no_mangle]
pub static xmlIsIdeographicGroup: xmlChRangeGroup = xmlChRangeGroup {
    nbShortRange: super::ranges::XML_IS_IDEOGRAPHIC_GROUP.short_ranges.len() as c_int,
    nbLongRange: super::ranges::XML_IS_IDEOGRAPHIC_GROUP.long_ranges.len() as c_int,
    shortRange: XML_IS_IDEOGRAPHIC_SRNG_FFI.as_ptr(),
    longRange: std::ptr::null(),
};