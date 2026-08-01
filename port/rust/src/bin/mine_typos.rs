use std::collections::{BTreeSet, HashMap};
use std::env;
use std::fs::File;
use std::io::{self, BufRead, BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};

use khmer_segmenter::{KhmerSegmenter, SegmenterConfig, SpellcheckProfile};

#[derive(Debug)]
struct Evidence {
    typed: String,
    correction: String,
    count: usize,
    confidence_sum: f64,
    edit_cost: f32,
    sources: BTreeSet<String>,
    contexts: Vec<String>,
}

fn context(text: &str, start: usize, end: usize, needle: &str) -> String {
    let (start, end) = if start <= end
        && end <= text.len()
        && text.is_char_boundary(start)
        && text.is_char_boundary(end)
        && text.get(start..end) == Some(needle)
    {
        (start, end)
    } else if let Some(found) = text.find(needle) {
        (found, found + needle.len())
    } else {
        (0, 0)
    };
    let start_chars = text[..start].chars().count();
    let end_chars = start_chars + text[start..end].chars().count();
    let chars: Vec<_> = text.chars().collect();
    let left = start_chars.saturating_sub(24);
    let right = (end_chars + 24).min(chars.len());
    chars[left..right]
        .iter()
        .collect::<String>()
        .trim()
        .to_owned()
}

fn default_dictionary() -> Option<&'static str> {
    [
        "khmer_dictionary.kdict",
        "../../port/common/khmer_dictionary.kdict",
        "../common/khmer_dictionary.kdict",
    ]
    .into_iter()
    .find(|path| Path::new(path).is_file())
}

fn main() -> io::Result<()> {
    let args: Vec<_> = env::args().skip(1).collect();
    let mut dictionary: Option<String> = None;
    let mut output: Option<PathBuf> = None;
    let mut max_lines = usize::MAX;
    let mut inputs = Vec::new();
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--dictionary" => {
                index += 1;
                dictionary = args.get(index).cloned();
            }
            "--output" => {
                index += 1;
                output = args.get(index).map(PathBuf::from);
            }
            "--max-lines" => {
                index += 1;
                max_lines = args
                    .get(index)
                    .and_then(|value| value.parse().ok())
                    .unwrap_or(usize::MAX);
            }
            value if value.starts_with('-') => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    format!("unknown option: {value}"),
                ));
            }
            value => inputs.push(PathBuf::from(value)),
        }
        index += 1;
    }
    if inputs.is_empty() || output.is_none() {
        eprintln!(
            "usage: mine_typos --output candidates.jsonl [--dictionary FILE] [--max-lines N] INPUT..."
        );
        return Ok(());
    }

    let dictionary = dictionary
        .or_else(|| default_dictionary().map(str::to_owned))
        .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "KDIC dictionary not found"))?;
    let segmenter = KhmerSegmenter::new(Some(&dictionary), SegmenterConfig::default())
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error.to_string()))?;
    let mut evidence: HashMap<(String, String), Evidence> = HashMap::new();
    let mut lines_seen = 0usize;

    for input in inputs {
        let source = input
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("unknown")
            .to_owned();
        let reader = BufReader::new(File::open(&input)?);
        for line in reader.lines() {
            if lines_seen >= max_lines {
                break;
            }
            // Corpus files may contain editor- or tokenizer-inserted word
            // boundaries. They are not part of Khmer spelling and must not
            // influence segmentation or typo-span discovery.
            let line = line?.replace('\u{200b}', "");
            if line.trim().is_empty() {
                continue;
            }
            lines_seen += 1;
            let diagnostics = segmenter
                .check_text(&line, SpellcheckProfile::HighRecall)
                .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error.to_string()))?;
            for diagnostic in diagnostics {
                let Some(suggestion) = diagnostic.suggestions.first() else {
                    continue;
                };
                let key = (diagnostic.text.clone(), suggestion.text.clone());
                let item = evidence.entry(key).or_insert_with(|| Evidence {
                    typed: diagnostic.text.clone(),
                    correction: suggestion.text.clone(),
                    count: 0,
                    confidence_sum: 0.0,
                    edit_cost: suggestion.edit_cost,
                    sources: BTreeSet::new(),
                    contexts: Vec::new(),
                });
                item.count += 1;
                item.confidence_sum += diagnostic.confidence as f64;
                item.sources.insert(source.clone());
                let excerpt = context(
                    &line,
                    diagnostic.range.start,
                    diagnostic.range.end,
                    &diagnostic.text,
                );
                if item.contexts.len() < 3 && !item.contexts.contains(&excerpt) {
                    item.contexts.push(excerpt);
                }
            }
        }
    }

    let mut evidence: Vec<_> = evidence.into_values().collect();
    evidence.sort_by(|left, right| {
        right
            .count
            .cmp(&left.count)
            .then_with(|| left.edit_cost.total_cmp(&right.edit_cost))
            .then_with(|| left.typed.cmp(&right.typed))
    });
    let mut writer = BufWriter::new(File::create(output.unwrap())?);
    for item in evidence {
        let record = serde_json::json!({
            "typed": item.typed,
            "correction": item.correction,
            "count": item.count,
            "average_confidence": item.confidence_sum / item.count as f64,
            "edit_cost": item.edit_cost,
            "sources": item.sources,
            "contexts": item.contexts,
        });
        serde_json::to_writer(&mut writer, &record)
            .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
        writeln!(writer)?;
    }
    eprintln!("scanned_lines={lines_seen}");
    Ok(())
}
