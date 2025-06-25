use super::ranges::*;

#[derive(Debug, Clone, Copy)]
pub struct ChSRange {
    pub low: u16,
    pub high: u16,
}

#[derive(Debug, Clone, Copy)]
pub struct ChLRange {
    pub low: u32,
    pub high: u32,
}

pub struct ChRangeGroup {
    pub short_ranges: &'static [ChSRange],
    pub long_ranges: &'static [ChLRange],
}

pub fn char_in_range(val: u32, group: &ChRangeGroup) -> bool {
    if val < 0x10000 {
        if group.short_ranges.is_empty() {
            return false;
        }
        
        let val = val as u16;
        let mut low = 0;
        let mut high = group.short_ranges.len() - 1;
        
        while low <= high {
            let mid = (low + high) / 2;
            let range = &group.short_ranges[mid];
            
            if val < range.low {
                if mid == 0 {
                    break;
                }
                high = mid - 1;
            } else if val > range.high {
                low = mid + 1;
            } else {
                return true;
            }
        }
    } else {
        if group.long_ranges.is_empty() {
            return false;
        }
        
        let mut low = 0;
        let mut high = group.long_ranges.len() - 1;
        
        while low <= high {
            let mid = (low + high) / 2;
            let range = &group.long_ranges[mid];
            
            if val < range.low {
                if mid == 0 {
                    break;
                }
                high = mid - 1;
            } else if val > range.high {
                low = mid + 1;
            } else {
                return true;
            }
        }
    }
    false
}

#[inline]
fn is_base_char_ascii(c: u32) -> bool {
    ((0x41..=0x5a).contains(&c)) ||
    ((0x61..=0x7a).contains(&c)) ||
    ((0xc0..=0xd6).contains(&c)) ||
    ((0xd8..=0xf6).contains(&c)) ||
    (c >= 0xf8)
}

pub fn is_base_char(ch: u32) -> bool {
    if ch < 0x100 {
        is_base_char_ascii(ch)
    } else {
        char_in_range(ch, &XML_IS_BASE_CHAR_GROUP)
    }
}

#[inline]
fn is_blank_ascii(c: u32) -> bool {
    c == 0x20 || (0x9..=0xa).contains(&c) || c == 0xd
}

pub fn is_blank(ch: u32) -> bool {
    if ch < 0x100 {
        is_blank_ascii(ch)
    } else {
        false
    }
}

#[inline]
fn is_char_ascii(c: u32) -> bool {
    (0x9..=0xa).contains(&c) || c == 0xd || c >= 0x20
}

pub fn is_char(ch: u32) -> bool {
    if ch < 0x100 {
        is_char_ascii(ch)
    } else {
        (0x100..=0xd7ff).contains(&ch) ||
        (0xe000..=0xfffd).contains(&ch) ||
        (0x10000..=0x10ffff).contains(&ch)
    }
}

pub fn is_combining(ch: u32) -> bool {
    if ch < 0x100 {
        false
    } else {
        char_in_range(ch, &XML_IS_COMBINING_GROUP)
    }
}

#[inline]
fn is_digit_ascii(c: u32) -> bool {
    (0x30..=0x39).contains(&c)
}

pub fn is_digit(ch: u32) -> bool {
    if ch < 0x100 {
        is_digit_ascii(ch)
    } else {
        char_in_range(ch, &XML_IS_DIGIT_GROUP)
    }
}

#[inline]
fn is_extender_ascii(c: u32) -> bool {
    c == 0xb7
}

pub fn is_extender(ch: u32) -> bool {
    if ch < 0x100 {
        is_extender_ascii(ch)
    } else {
        char_in_range(ch, &XML_IS_EXTENDER_GROUP)
    }
}

pub fn is_ideographic(ch: u32) -> bool {
    if ch < 0x100 {
        false
    } else {
        (0x4e00..=0x9fa5).contains(&ch) ||
        ch == 0x3007 ||
        (0x3021..=0x3029).contains(&ch)
    }
}

pub fn is_pubid_char(ch: u32) -> bool {
    if ch < 0x100 {
        XML_IS_PUBID_CHAR_TAB[ch as usize] != 0
    } else {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_base_char() {
        assert!(is_base_char(b'A' as u32));
        assert!(is_base_char(b'z' as u32));
        assert!(!is_base_char(b'0' as u32));
        assert!(!is_base_char(b' ' as u32));
    }

    #[test]
    fn test_blank() {
        assert!(is_blank(b' ' as u32));
        assert!(is_blank(b'\t' as u32));
        assert!(is_blank(b'\n' as u32));
        assert!(is_blank(b'\r' as u32));
        assert!(!is_blank(b'A' as u32));
    }

    #[test]
    fn test_char() {
        assert!(is_char(b'A' as u32));
        assert!(is_char(b' ' as u32));
        assert!(is_char(b'\t' as u32));
        assert!(is_char(0x100));
        assert!(!is_char(0x8));
    }

    #[test]
    fn test_digit() {
        assert!(is_digit(b'0' as u32));
        assert!(is_digit(b'9' as u32));
        assert!(!is_digit(b'A' as u32));
        assert!(!is_digit(b' ' as u32));
    }

    #[test]
    fn test_pubid_char() {
        assert!(is_pubid_char(b'A' as u32));
        assert!(is_pubid_char(b'0' as u32));
        assert!(is_pubid_char(b' ' as u32));
        assert!(!is_pubid_char(b'"' as u32));
        assert!(!is_pubid_char(0x100));
    }

    #[test]
    fn test_char_in_range() {
        assert!(char_in_range(0x100, &XML_IS_BASE_CHAR_GROUP));
        assert!(char_in_range(0x131, &XML_IS_BASE_CHAR_GROUP));
        assert!(!char_in_range(0x132, &XML_IS_BASE_CHAR_GROUP));
        assert!(!char_in_range(0x133, &XML_IS_BASE_CHAR_GROUP));
    }
}