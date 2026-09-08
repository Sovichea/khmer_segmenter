use std::collections::{BTreeMap, HashMap};
use std::env;
use std::fs::File;
use std::io::{self, BufRead, BufReader, BufWriter, Write};
use std::path::PathBuf;

use khmer_segmenter::{KhmerSegmenter, SegmenterConfig};

#[derive(Default)]
struct Evidence {
    segmenter_unknown_count: u64,
    external_boundary_count: u64,
    contexts: Vec<String>,
}

fn clean(value: &str) -> String {
    value.replace('\u{200b}', "").trim().to_owned()
}

fn plausible_khmer_word(value: &str) -> bool {
    let mut consonants = 0usize;
    let mut characters = 0usize;
    for character in value.chars() {
        if !matches!(character, '\u{1780}'..='\u{17d3}' | '\u{17dd}') {
            return false;
        }
        consonants += usize::from(matches!(character, '\u{1780}'..='\u{17a2}'));
        characters += 1;
    }
    (2..=40).contains(&characters) && consonants >= 2
}

fn excerpt(text: &str, needle: &str) -> String {
    let Some(byte_start) = text.find(needle) else {
        return text.chars().take(100).collect();
    };
    let start_chars = text[..byte_start].chars().count();
    let end_chars = start_chars + needle.chars().count();
    let chars: Vec<_> = text.chars().collect();
    let left = start_chars.saturating_sub(30);
    let right = (end_chars + 30).min(chars.len());
    let before: String = chars[left..start_chars].iter().collect();
    let after: String = chars[end_chars..right].iter().collect();
    format!("{}[{}]{}", before.trim_start(), needle, after.trim_end())
}

fn record(
    evidence: &mut HashMap<String, Evidence>,
    word: &str,
    context: &str,
    from_segmenter: bool,
) {
    let item = evidence.entry(word.to_owned()).or_default();
    if from_segmenter {
        item.segmenter_unknown_count += 1;
    } else {
        item.external_boundary_count += 1;
    }
    if item.contexts.len() < 3 {
        let sample = excerpt(context, word);
        if !item.contexts.contains(&sample) {
            item.contexts.push(sample);
        }
    }
}

fn main() -> io::Result<()> {
    let args: Vec<_> = env::args().skip(1).collect();
    let mut raw = None;
    let mut segmented = None;
    let mut dictionary = None;
    let mut output = None;
    let mut merge_candidates = None;
    let mut frequency_output = None;
    let mut skip_segmenter = false;
    let mut max_lines = usize::MAX;
    let mut index = 0;
    while index < args.len() {
        let target = match args[index].as_str() {
            "--raw" => &mut raw,
            "--segmented" => &mut segmented,
            "--dictionary" | "--kdict" => &mut dictionary,
            "--output" => &mut output,
            "--merge-candidates" => &mut merge_candidates,
            "--frequency-output" => &mut frequency_output,
            "--skip-segmenter" => {
                skip_segmenter = true;
                index += 1;
                continue;
            }
            "--max-lines" => {
                index += 1;
                max_lines = args
                    .get(index)
                    .and_then(|value| value.parse().ok())
                    .unwrap_or(usize::MAX);
                index += 1;
                continue;
            }
            value => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    format!("unknown option {value:?}"),
                ));
            }
        };
        index += 1;
        *target = args.get(index).map(PathBuf::from);
        index += 1;
    }
    let required = |value: Option<PathBuf>, name: &str| {
        value.ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidInput, format!("{name} is required"))
        })
    };
    let raw = required(raw, "--raw")?;
    let dictionary = required(dictionary, "--dictionary")?;
    let output = required(output, "--output")?;
    let segmenter = KhmerSegmenter::from_path(dictionary, SegmenterConfig::default())?;
    let raw_reader = BufReader::with_capacity(1024 * 1024, File::open(raw)?);
    let mut segmented_lines = match segmented {
        Some(path) => Some(BufReader::with_capacity(1024 * 1024, File::open(path)?).lines()),
        None => None,
    };
    let mut evidence = HashMap::<String, Evidence>::new();
    let mut known_frequencies = HashMap::<String, u64>::new();
    if let Some(path) = merge_candidates {
        let reader = BufReader::with_capacity(1024 * 1024, File::open(path)?);
        for line in reader.lines() {
            let value: serde_json::Value = serde_json::from_str(&line?)
                .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
            let Some(word) = value.get("word").and_then(|item| item.as_str()) else {
                continue;
            };
            let item = evidence.entry(word.to_owned()).or_default();
            item.segmenter_unknown_count = value
                .get("segmenter_unknown_count")
                .and_then(|count| count.as_u64())
                .unwrap_or(0);
            item.external_boundary_count = value
                .get("external_boundary_count")
                .and_then(|count| count.as_u64())
                .unwrap_or(0);
            item.contexts = value
                .get("contexts")
                .and_then(|contexts| contexts.as_array())
                .into_iter()
                .flatten()
                .filter_map(|context| context.as_str().map(str::to_owned))
                .take(3)
                .collect();
        }
    }
    let mut lines = 0usize;

    for raw_result in raw_reader.lines() {
        if lines >= max_lines {
            break;
        }
        let raw_line = clean(&raw_result?);
        let segmented_line = segmented_lines
            .as_mut()
            .and_then(Iterator::next)
            .transpose()?
            .map(|line| clean(&line));
        if raw_line.is_empty() {
            continue;
        }
        lines += 1;

        if !skip_segmenter {
            let analysis = segmenter
                .segment_detailed(&raw_line)
                .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error.to_string()))?;
            for token in analysis.tokens() {
                if segmenter.is_known_word(token) {
                    *known_frequencies.entry(token.to_owned()).or_default() += 1;
                } else if plausible_khmer_word(token) {
                    record(&mut evidence, token, &raw_line, true);
                }
            }
        }
        if let Some(segmented_line) = segmented_line {
            for token in segmented_line.split_whitespace().map(clean) {
                if plausible_khmer_word(&token) && !segmenter.is_known_word(&token) {
                    record(&mut evidence, &token, &raw_line, false);
                }
            }
        }
        if lines % 100_000 == 0 {
            eprintln!("lines={lines} candidates={}", evidence.len());
        }
    }

    let mut ordered: Vec<_> = evidence.into_iter().collect();
    ordered.sort_by(|(left_word, left), (right_word, right)| {
        let left_total = left.segmenter_unknown_count + left.external_boundary_count;
        let right_total = right.segmenter_unknown_count + right.external_boundary_count;
        right_total
            .cmp(&left_total)
            .then_with(|| {
                right
                    .external_boundary_count
                    .cmp(&left.external_boundary_count)
            })
            .then_with(|| left_word.cmp(right_word))
    });

    let mut writer = BufWriter::new(File::create(output)?);
    for (word, item) in ordered {
        let isolated_segmentation = segmenter.segment(&word, Some(" | "));
        let record = serde_json::json!({
            "word": word,
            "segmenter_unknown_count": item.segmenter_unknown_count,
            "external_boundary_count": item.external_boundary_count,
            "isolated_segmentation": isolated_segmentation,
            "contexts": item.contexts,
        });
        serde_json::to_writer(&mut writer, &record)
            .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
        writeln!(writer)?;
    }
    eprintln!("scanned_lines={lines}");
    if let Some(path) = frequency_output {
        let ordered: BTreeMap<_, _> = known_frequencies.into_iter().collect();
        let mut writer = BufWriter::new(File::create(path)?);
        serde_json::to_writer_pretty(&mut writer, &ordered)
            .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
        writeln!(writer)?;
    }
    Ok(())
}
