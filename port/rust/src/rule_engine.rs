use crate::utils;

pub struct RuleEngine;

impl RuleEngine {
    pub fn new() -> Self {
        RuleEngine
    }

    pub fn apply(&self, text: &str, segments: &mut Vec<(usize, usize)>) {
        let mut i = 0;
        while i < segments.len() {
            // Get current segment string slice
            let (start, end) = segments[i];
            let seg = &text[start..end];
            let chars: Vec<char> = seg.chars().collect();
            let len = chars.len();
            let mut rule_applied = false;

            // Rule 0: "Ahsda Exception Keep"
            // txt[3] == 0xE1 && txt[4] == 0x9F && txt[5] == 0x8F (U+17CF Ahsda)
            // txt[0,1,2] check
            if len == 2 { // 2 chars (Rust chars)
                 if chars[1] == '\u{17CF}' {
                     if chars[0] == '\u{1780}' || chars[0] == '\u{178A}' { // KA or DA
                         i += 1;
                         continue;
                     }
                 }
            }

            // Rule 1: "Prefix OR Merge" (U+17A2)
            if len == 1 && chars[0] == '\u{17A2}' {
                if i + 1 < segments.len() {
                    let (_, next_end) = segments[i+1];
                    let next_seg = &text[segments[i+1].0..next_end];
                    if !is_separator(next_seg) {
                        // Merge: extend current end to next end
                        segments[i].1 = next_end;
                        segments.remove(i+1);
                        rule_applied = true;
                    }
                }
            }
            
            if rule_applied { continue; }

            // Rule 2 & 4: Suffix Checks (Signs Merge Left)
            // C code checked specific bytes for suffix.
            // if (txt[0]...txt[2] is KA-QA [0x80-0xA2]) check suffix
            // suffix[0].. is U+17CB, 17CD, 17CE, 17CC
            if len == 2 {
                 if chars[0] >= '\u{1780}' && chars[0] <= '\u{17A2}' {
                     let s = chars[1];
                     if s == '\u{17CB}' || s == '\u{17CE}' || s == '\u{17CF}' || s == '\u{17CC}' { // 8B, 8E, 8F, 8C
                         if i > 0 {
                             // Merge current into previous
                             let (_, curr_end) = segments[i];
                             segments[i-1].1 = curr_end;
                             segments.remove(i);
                             i -= 1;
                             rule_applied = true;
                         }
                     }
                 }
            }

            if rule_applied { continue; }

            // Rule 3: Samyok Sannya (Merge Next)
            // U+17D0 (90)
            if len == 2 {
                if chars[0] >= '\u{1780}' && chars[0] <= '\u{17A2}' {
                    if chars[1] == '\u{17D0}' {
                        if i + 1 < segments.len() {
                            let (_, next_end) = segments[i+1];
                            segments[i].1 = next_end;
                            segments.remove(i+1);
                            rule_applied = true;
                        }
                    }
                }
            }

             if rule_applied { continue; }

            // Rule 5: Invalid Single Consonant Cleanup
            if is_invalid_single(seg) {
                let p_sep = if i > 0 { 
                    let (p_start, p_end) = segments[i-1];
                    is_separator(&text[p_start..p_end]) 
                } else { 
                    true 
                };
                
                if !p_sep {
                    if i > 0 {
                        let (_, curr_end) = segments[i];
                        segments[i-1].1 = curr_end;
                        segments.remove(i);
                        i -= 1;
                        rule_applied = true;
                    }
                }
            }
            
            if !rule_applied {
                i += 1;
            }
        }
    }
}

fn is_separator(s: &str) -> bool {
    // Only check first char? The C code checks cp of string, implies single char check mainly
    // But returns true if any char is sep?
    // C: utf8_decode_re(s, &cp); ... 
    // It checks ONLY the first character.
    if let Some(c) = s.chars().next() {
        return utils::is_separator_cp(c);
    }
    false
}

fn is_invalid_single(s: &str) -> bool {
    let mut chars = s.chars();
    let first = match chars.next() {
        Some(c) => c,
        None => return false,
    };
    
    if chars.next().is_some() { return false; } // More than 1 char -> valid (or handled elsewhere)
    
    // logic: 
    // if ((cp >= 0x1780 && cp <= 0x17A2) || (cp >= 0x17A3 && cp <= 0x17B3)) return 0;
    // if (isdigit(cp) || (cp >= 0x17E0 && cp <= 0x17E9)) return 0;
    // if (is_separator(s)) return 0;
    // return 1;
    
    if (first >= '\u{1780}' && first <= '\u{17A2}') || (first >= '\u{17A3}' && first <= '\u{17B3}') { return false; }
    if utils::is_digit_cp(first) { return false; }
    if utils::is_separator_cp(first) { return false; }
    
    true
}
