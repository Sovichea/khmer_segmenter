

#[derive(Eq, PartialEq, Clone, Copy)]
struct ClsPart {
    c1: char,
    c2: Option<char>,
    type_: i32,
    index: u8,
}

fn get_char_type_norm(c: char) -> i32 {
    if (c >= '\u{1780}' && c <= '\u{17A2}') || (c >= '\u{17A3}' && c <= '\u{17B3}') { return 1; } // BASE
    if c == '\u{17D2}' { return 2; } // COENG
    if c == '\u{17C9}' || c == '\u{17CA}' { return 3; } // REGISTER
    if c >= '\u{17B6}' && c <= '\u{17C5}' { return 4; } // VOWEL
    if (c >= '\u{17C6}' && c <= '\u{17D1}') || c == '\u{17D3}' || c == '\u{17DD}' { return 5; } // SIGN
    0 // OTHER
}

fn get_prio(p: &ClsPart) -> i32 {
    if p.type_ == 2 { // COENG
        if let Some(sub) = p.c2 {
             if sub == '\u{179A}' { return 20; } // Ro Subscript
             return 10; // Non-Ro Subscript
        }
        return 15; // Stray Coeng
    }
    if p.type_ == 3 { return 30; }
    if p.type_ == 4 { return 40; }
    if p.type_ == 5 { return 50; }
    100
}

pub fn khmer_normalize(text: &str) -> String {
    let mut temp = String::with_capacity(text.len());
    let mut chars = text.chars().peekable();
    
    while let Some(c) = chars.next() {
        if c == '\u{200B}' || c == '\u{200C}' || c == '\u{200D}' { continue; }
        if c == '\u{17C1}' { // e
            if let Some(&next) = chars.peek() {
                if next == '\u{17B8}' { temp.push('\u{17BE}'); chars.next(); continue; } // oe
                if next == '\u{17B6}' { temp.push('\u{17C4}'); chars.next(); continue; } // au
            }
        }
        temp.push(c);
    }
    
    let mut final_str = String::with_capacity(temp.len());
    let mut cluster: Vec<ClsPart> = Vec::with_capacity(8);
    let mut cls_count = 0;
    
    let mut iter = temp.chars().peekable();
    
    while let Some(c) = iter.next() {
        let type_ = get_char_type_norm(c);
        
        if type_ == 1 { // BASE
            flush_cluster(&mut final_str, &mut cluster);
            cluster.push(ClsPart { c1: c, c2: None, type_, index: cls_count });
            cls_count += 1;
        } else if type_ == 2 { // COENG
             let mut c2 = None;
             if let Some(&next) = iter.peek() {
                 if get_char_type_norm(next) == 1 {
                     iter.next();
                     c2 = Some(next);
                 }
             }
             cluster.push(ClsPart { c1: c, c2, type_: 2, index: cls_count });
             cls_count += 1;
        } else if type_ > 2 {
            if !cluster.is_empty() {
                cluster.push(ClsPart { c1: c, c2: None, type_, index: cls_count });
                cls_count += 1;
            } else {
                final_str.push(c);
            }
        } else {
            flush_cluster(&mut final_str, &mut cluster);
            final_str.push(c);
            cls_count = 0;
        }
    }
    flush_cluster(&mut final_str, &mut cluster);
    final_str
}

fn flush_cluster(final_str: &mut String, cluster: &mut Vec<ClsPart>) {
    if cluster.is_empty() { return; }
    if cluster.len() > 2 {
        let base = cluster.remove(0);
        cluster.sort_by(|a, b| {
            let prio_a = get_prio(a);
            let prio_b = get_prio(b);
            if prio_a != prio_b { prio_a.cmp(&prio_b) }
            else { a.index.cmp(&b.index) }
        });
        cluster.insert(0, base);
    }
    for part in cluster.iter() {
        final_str.push(part.c1);
        if let Some(c2) = part.c2 { final_str.push(c2); }
    }
    cluster.clear();
}
