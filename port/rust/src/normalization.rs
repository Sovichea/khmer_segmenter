use std::ops::Range;

#[derive(Debug, Eq, PartialEq, Clone)]
pub struct NormalizedUnit {
    pub text: String,
    pub source_range: Range<usize>,
}

#[derive(Debug, Eq, PartialEq, Clone)]
pub struct MappedNormalization {
    pub text: String,
    pub units: Vec<NormalizedUnit>,
}

#[derive(Eq, PartialEq, Clone)]
struct ClsPart {
    text: String,
    source_range: Range<usize>,
    type_: i32,
    index: usize,
}

fn get_char_type_norm(c: char) -> i32 {
    if ('\u{1780}'..='\u{17B3}').contains(&c) {
        return 1;
    }
    if c == '\u{17D2}' {
        return 2;
    }
    if c == '\u{17C9}' || c == '\u{17CA}' {
        return 3;
    }
    if ('\u{17B6}'..='\u{17C5}').contains(&c) {
        return 4;
    }
    if ('\u{17C6}'..='\u{17D1}').contains(&c) || c == '\u{17D3}' || c == '\u{17DD}' {
        return 5;
    }
    0
}

fn get_prio(part: &ClsPart) -> i32 {
    if part.type_ == 2 {
        if part.text.ends_with('\u{179A}') {
            return 20;
        }
        return if part.text.chars().count() > 1 { 10 } else { 15 };
    }
    match part.type_ {
        3 => 30,
        4 => 40,
        5 => 50,
        _ => 100,
    }
}

fn push_unit(output: &mut MappedNormalization, unit: NormalizedUnit) {
    output.text.push_str(&unit.text);
    output.units.push(unit);
}

fn flush_cluster(output: &mut MappedNormalization, cluster: &mut Vec<ClsPart>) {
    if cluster.is_empty() {
        return;
    }
    if cluster.len() > 2 {
        let base = cluster.remove(0);
        cluster.sort_by(|left, right| {
            get_prio(left)
                .cmp(&get_prio(right))
                .then_with(|| left.index.cmp(&right.index))
        });
        cluster.insert(0, base);
    }
    for part in cluster.drain(..) {
        push_unit(
            output,
            NormalizedUnit {
                text: part.text,
                source_range: part.source_range,
            },
        );
    }
}

pub fn khmer_normalize_mapped(text: &str) -> MappedNormalization {
    let source: Vec<(usize, char)> = text.char_indices().collect();
    let mut prepared = Vec::<NormalizedUnit>::with_capacity(source.len());
    let mut index = 0;
    while index < source.len() {
        let (start, character) = source[index];
        let end = source
            .get(index + 1)
            .map_or(text.len(), |(next, _)| *next);
        if matches!(character, '\u{200B}' | '\u{200C}' | '\u{200D}') {
            index += 1;
            continue;
        }
        if character == '\u{17C1}' {
            if let Some(&(next_start, next)) = source.get(index + 1) {
                let replacement = match next {
                    '\u{17B8}' => Some('\u{17BE}'),
                    '\u{17B6}' => Some('\u{17C4}'),
                    _ => None,
                };
                if let Some(replacement) = replacement {
                    let next_end = source
                        .get(index + 2)
                        .map_or(text.len(), |(after, _)| *after);
                    prepared.push(NormalizedUnit {
                        text: replacement.to_string(),
                        source_range: start..next_end.max(next_start),
                    });
                    index += 2;
                    continue;
                }
            }
        }
        prepared.push(NormalizedUnit {
            text: character.to_string(),
            source_range: start..end,
        });
        index += 1;
    }

    let mut output = MappedNormalization {
        text: String::with_capacity(text.len()),
        units: Vec::with_capacity(prepared.len()),
    };
    let mut cluster = Vec::<ClsPart>::with_capacity(8);
    let mut prepared_index = 0;
    let mut cluster_index = 0;
    while prepared_index < prepared.len() {
        let unit = &prepared[prepared_index];
        let character = unit.text.chars().next().expect("normalization unit");
        let type_ = get_char_type_norm(character);
        if type_ == 1 {
            flush_cluster(&mut output, &mut cluster);
            cluster_index = 0;
            cluster.push(ClsPart {
                text: unit.text.clone(),
                source_range: unit.source_range.clone(),
                type_,
                index: cluster_index,
            });
        } else if type_ == 2 {
            let mut text = unit.text.clone();
            let mut source_range = unit.source_range.clone();
            if let Some(next) = prepared.get(prepared_index + 1) {
                let next_char = next.text.chars().next().expect("normalization unit");
                if get_char_type_norm(next_char) == 1 {
                    text.push_str(&next.text);
                    source_range.end = next.source_range.end;
                    prepared_index += 1;
                }
            }
            cluster.push(ClsPart {
                text,
                source_range,
                type_: 2,
                index: cluster_index,
            });
        } else if type_ > 2 && !cluster.is_empty() {
            cluster.push(ClsPart {
                text: unit.text.clone(),
                source_range: unit.source_range.clone(),
                type_,
                index: cluster_index,
            });
        } else {
            flush_cluster(&mut output, &mut cluster);
            push_unit(&mut output, unit.clone());
            cluster_index = 0;
        }
        cluster_index += 1;
        prepared_index += 1;
    }
    flush_cluster(&mut output, &mut cluster);
    output
}

pub fn khmer_normalize(text: &str) -> String {
    khmer_normalize_mapped(text).text
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn maps_composition_reordering_and_removed_joiners() {
        let source = "\u{1780}\u{17C1}\u{17B8}\u{200B}\u{17C6}\u{17B6}";
        let normalized = khmer_normalize_mapped(source);
        assert_eq!(normalized.text, "\u{1780}\u{17BE}\u{17B6}\u{17C6}");
        assert_eq!(normalized.units[1].source_range, 3..9);
        assert_eq!(normalized.units[2].source_range, 15..18);
        assert_eq!(normalized.units[3].source_range, 12..15);
    }
}
