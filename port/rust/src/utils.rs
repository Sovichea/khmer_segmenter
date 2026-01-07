
#[cfg(target_arch = "x86_64")]
use std::arch::x86_64::*;

#[allow(unused_unsafe)]
#[inline(always)]
pub unsafe fn fast_str_eq(a: *const u8, b: *const u8, len: usize) -> bool {
    #[cfg(all(target_arch = "x86_64", target_feature = "avx2"))]
    {
        let mut i = 0;
        while i + 32 <= len {
            let va = _mm256_loadu_si256(a.add(i) as *const __m256i);
            let vb = _mm256_loadu_si256(b.add(i) as *const __m256i);
            let cmp = _mm256_cmpeq_epi8(va, vb);
            let mask = _mm256_movemask_epi8(cmp);
            if mask != -1 { return false; }
            i += 32;
        }
        let rem = len - i;
        if rem == 0 { return true; }
        let mut j = 0;
        while j < rem {
            if *a.add(i + j) != *b.add(i + j) { return false; }
            j += 1;
        }
        return true;
    }

    #[cfg(all(target_arch = "x86_64", not(target_feature = "avx2")))]
    {
        let mut i = 0;
        while i + 16 <= len {
             let va = _mm_loadu_si128(a.add(i) as *const __m128i);
             let vb = _mm_loadu_si128(b.add(i) as *const __m128i);
             let cmp = _mm_cmpeq_epi8(va, vb);
             let mask = _mm_movemask_epi8(cmp);
             if mask != 0xFFFF { return false; }
             i += 16;
        }
        let rem = len - i;
        if rem == 0 { return true; }
        let mut j = 0;
        while j < rem {
            if *a.add(i + j) != *b.add(i + j) { return false; }
            j += 1;
        }
        return true;
    }

    #[cfg(not(target_arch = "x86_64"))]
    {
        // SWAR Optimization (8 bytes at a time) for WASM/other
        // WASM supports unaligned loads
        let mut i = 0;
        while i + 8 <= len {
             let va = (a.add(i) as *const u64).read_unaligned();
             let vb = (b.add(i) as *const u64).read_unaligned();
             if va != vb { return false; }
             i += 8;
        }

        while i < len {
            if *a.add(i) != *b.add(i) { return false; }
            i += 1;
        }
        return true;
    }
}

pub fn is_khmer_char(cp: char) -> bool {
    (cp >= '\u{1780}' && cp <= '\u{17FF}') || (cp >= '\u{19E0}' && cp <= '\u{19FF}')
}

pub fn is_digit_cp(cp: char) -> bool {
    // 0-9
    if cp >= '0' && cp <= '9' { return true; }
    // Khmer Digits
    if cp >= '\u{17E0}' && cp <= '\u{17E9}' { return true; }
    false
}

pub fn is_separator_cp(cp: char) -> bool {
    // Khmer Punctuation
    if cp >= '\u{17D4}' && cp <= '\u{17DA}' { return true; }
    // Khmer Currency
    if cp == '\u{17DB}' { return true; }

    // Basic ASCII Punctuation & Space
    if (cp as u32) < 0x80 && (cp.is_ascii_punctuation() || cp.is_ascii_whitespace()) { return true; }
    
    // Additional separators
    if cp == '\u{00A0}' { return true; } // Non-breaking space
    if cp == '\u{02DD}' { return true; } // Double acute accent
    
    // Latin-1 Supplement Punctuation
    if cp == '\u{00AB}' || cp == '\u{00BB}' { return true; }
    
    // General Punctuation (0x2000-0x206F)
    if cp >= '\u{2000}' && cp <= '\u{206F}' { return true; }
    
    // Currency Symbols (0x20A0-0x20CF)
    if cp >= '\u{20A0}' && cp <= '\u{20CF}' { return true; }

    // Latin-1 Currency
    if cp == '\u{00A3}' || cp == '\u{00A5}' { return true; }

    false
}

pub fn is_valid_single_base_char(cp: char) -> bool {
    // Consonants: 0x1780 - 0x17A2
    if cp >= '\u{1780}' && cp <= '\u{17A2}' { return true; }
    // Independent Vowels: 0x17A3 - 0x17B3
    if cp >= '\u{17A3}' && cp <= '\u{17B3}' { return true; }
    false
}

pub fn get_khmer_cluster_length(text: &str) -> usize {
    let mut chars = text.chars();
    let first = match chars.next() {
        Some(c) => c,
        None => return 0,
    };

    // Must start with Base or Indep Vowel
    if !((first >= '\u{1780}' && first <= '\u{17B3}')) {
        // If it's a coeng/vowel at start, invalid but consume 1 char
        return first.len_utf8();
    }

    let mut len = first.len_utf8();
    let mut iter = text[len..].chars();
    
    while let Some(next_cp) = iter.next() {
        // Coeng (0x17D2) handling
        if next_cp == '\u{17D2}' {
             // Check next next
             let next_len = next_cp.len_utf8();
             let mut lookahead = iter.clone();
             if let Some(sub_cp) = lookahead.next() {
                 if sub_cp >= '\u{1780}' && sub_cp <= '\u{17A2}' {
                     len += next_len + sub_cp.len_utf8();
                     iter.next(); // consume sub_cp
                     continue;
                 }
             }
             break; // Trailing coeng or invalid
        }

        // Vowels/Signs
        // 0x17B6 - 0x17D1, 0x17D3, 0x17DD
        if (next_cp >= '\u{17B6}' && next_cp <= '\u{17D1}') || next_cp == '\u{17D3}' || next_cp == '\u{17DD}' {
            len += next_cp.len_utf8();
            continue;
        }

        break;
    }
    
    len
}

pub fn get_number_length(text: &str) -> usize {
    let mut chars = text.chars();
    let first = match chars.next() {
        Some(c) => c,
        None => return 0,
    };
    
    if !is_digit_cp(first) { return 0; }
    
    let mut len = first.len_utf8();
    let mut iter = text[len..].chars();
    
    while let Some(next_cp) = iter.next() {
        if is_digit_cp(next_cp) {
            len += next_cp.len_utf8();
            continue;
        }
        
        // Separators: , . Space
        if next_cp == ',' || next_cp == '.' {
            let next_len = next_cp.len_utf8();
            let mut lookahead = iter.clone();
             if let Some(f_cp) = lookahead.next() {
                 if is_digit_cp(f_cp) {
                     len += next_len + f_cp.len_utf8();
                     iter.next(); // consume digit
                     continue;
                 }
             }
        }
        break;
    }
    len
}



pub fn is_acronym_start(text: &str) -> bool {
    let mut chars = text.chars();
    let first = match chars.next() {
        Some(c) => c,
        None => return false,
    };
    
    // Must start with Khmer Consonant or Independent Vowel
    if !((first >= '\u{1780}' && first <= '\u{17B3}')) { return false; }
    
    let cluster_bytes = get_khmer_cluster_length(text);
    if cluster_bytes == 0 { return false; }
    
    if let Some(c) = text[cluster_bytes..].chars().next() {
        if c == '.' { return true; }
    }
    
    false
}

pub fn get_acronym_length(text: &str) -> usize {
    let mut len = 0;
    let mut rest = text;
    
    loop {
        let mut chars = rest.chars();
        let first = match chars.next() {
            Some(c) => c,
            None => break,
        };
        
        if !((first >= '\u{1780}' && first <= '\u{17B3}')) { break; }
        
        let cluster_bytes = get_khmer_cluster_length(rest);
        if cluster_bytes == 0 { break; }
        
        if let Some(c) = rest[cluster_bytes..].chars().next() {
            if c == '.' {
                let dot_len = c.len_utf8();
                len += cluster_bytes + dot_len;
                rest = &rest[cluster_bytes+dot_len..];
                continue;
            }
        }
        break;
    }
    
    len
}

pub fn djb2_hash(str: &[u8]) -> u32 {
    let mut hash: u32 = 5381;
    for &c in str {
        hash = (hash << 5).wrapping_add(hash).wrapping_add(c as u32);
    }
    hash
}
