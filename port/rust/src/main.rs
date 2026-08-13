use rayon::prelude::*;
use std::collections::BTreeMap;
use std::env;
use std::fs::File;
use std::io::{self, BufRead, BufReader, Read, Write};
use std::path::Path;
use std::time::Instant;

use khmer_segmenter::kdict::{
    coeng_da_ta_variants, KDict, WORD_AUTOCOMPLETE, WORD_SEGMENT, WORD_SPELLCHECK,
    WORD_SUPPLEMENTAL, WORD_TYPO_SURFACE,
};
use khmer_segmenter::khmer_segmenter::{KhmerSegmenter, SegmentationLength, SegmenterConfig};
use khmer_segmenter::{SpellcheckProfile, SpellingAccuracy};

fn invalid_data(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.into())
}

fn clean_klex_word(value: &str) -> String {
    value
        .trim()
        .replace(['\u{200b}', '\u{200c}', '\u{200d}'], "")
}

fn compile_klex(source_path: &str, output_path: &str, base_path: Option<&str>) -> io::Result<()> {
    let source: serde_json::Value = serde_json::from_reader(File::open(source_path)?)
        .map_err(|error| invalid_data(error.to_string()))?;
    if source.get("version").and_then(|value| value.as_u64()) != Some(1) {
        return Err(invalid_data("KLEX requires version 1"));
    }
    let records = source
        .get("entries")
        .and_then(|value| value.as_array())
        .ok_or_else(|| invalid_data("KLEX requires an entries array"))?;

    let base = base_path.map(KDict::load).transpose()?;
    if base.as_ref().is_some_and(|pack| pack.version() < 2) {
        return Err(invalid_data("KLEX overlays require a KDIC v2 base pack"));
    }
    let mut flags_by_word: BTreeMap<String, u32> = base
        .as_ref()
        .map(|pack| {
            pack.lexical_entries()
                .into_iter()
                .map(|entry| (entry.word, entry.flags))
                .collect()
        })
        .unwrap_or_default();
    let base_costs: BTreeMap<String, f32> = base
        .as_ref()
        .map(|pack| {
            pack.lexical_entries()
                .into_iter()
                .map(|entry| (entry.word, entry.cost))
                .collect()
        })
        .unwrap_or_default();
    let mut counts: BTreeMap<String, f64> = BTreeMap::new();
    let mut overlay_words = std::collections::BTreeSet::new();
    let mut corrections: BTreeMap<String, String> = base
        .as_ref()
        .map(|pack| pack.typo_corrections().into_iter().collect())
        .unwrap_or_default();
    let mut overlay_corrections: BTreeMap<String, String> = BTreeMap::new();
    for (position, record) in records.iter().enumerate() {
        let number = position + 1;
        let record = record
            .as_object()
            .ok_or_else(|| invalid_data(format!("KLEX entry {number} must be an object")))?;
        let word = clean_klex_word(
            record
                .get("word")
                .and_then(|value| value.as_str())
                .unwrap_or(""),
        );
        let uses = record
            .get("uses")
            .and_then(|value| value.as_array())
            .ok_or_else(|| invalid_data(format!("KLEX entry {number} requires uses")))?;
        if word.is_empty() || uses.is_empty() {
            return Err(invalid_data(format!(
                "KLEX entry {number} requires word and uses"
            )));
        }
        overlay_words.insert(word.clone());
        let mut flags = 0_u32;
        for usage in uses {
            flags |= match usage.as_str() {
                Some("segmentation") => WORD_SEGMENT,
                Some("spelling") => WORD_SPELLCHECK,
                Some("autocomplete") => WORD_AUTOCOMPLETE,
                Some("typo") => WORD_TYPO_SURFACE,
                Some("supplemental") => WORD_SUPPLEMENTAL,
                Some(value) => {
                    return Err(invalid_data(format!(
                        "KLEX entry {number} has unknown use {value:?}"
                    )))
                }
                None => {
                    return Err(invalid_data(format!(
                        "KLEX entry {number} uses must contain strings"
                    )))
                }
            };
        }
        if flags & WORD_SUPPLEMENTAL != 0 {
            flags |= WORD_SEGMENT;
        }
        if flags & WORD_AUTOCOMPLETE != 0 && flags & WORD_SPELLCHECK == 0 {
            return Err(invalid_data(format!(
                "KLEX entry {number}: autocomplete requires spelling"
            )));
        }
        let frequency = record
            .get("frequency")
            .map(|value| {
                value.as_f64().ok_or_else(|| {
                    invalid_data(format!("KLEX entry {number}: frequency must be a number"))
                })
            })
            .transpose()?
            .unwrap_or(0.0);
        if !frequency.is_finite() || frequency < 0.0 {
            return Err(invalid_data(format!(
                "KLEX entry {number}: frequency must be finite and non-negative"
            )));
        }
        if flags & WORD_TYPO_SURFACE != 0 {
            let status = record
                .get("status")
                .and_then(|value| value.as_str())
                .unwrap_or("approved");
            if status == "approved" {
                let correction = clean_klex_word(
                    record
                        .get("correction")
                        .and_then(|value| value.as_str())
                        .unwrap_or(""),
                );
                if correction.is_empty() || correction == word {
                    return Err(invalid_data(format!(
                        "KLEX entry {number}: typo requires a different correction"
                    )));
                }
                if overlay_corrections
                    .insert(word.clone(), correction.clone())
                    .is_some_and(|previous| previous != correction)
                {
                    return Err(invalid_data(format!(
                        "conflicting KLEX correction for {word:?}"
                    )));
                }
                corrections.insert(word.clone(), correction);
            } else {
                flags &= !WORD_TYPO_SURFACE;
            }
        }
        *flags_by_word.entry(word.clone()).or_insert(0) |= flags;
        counts
            .entry(word)
            .and_modify(|value| *value = value.max(frequency))
            .or_insert(frequency);
    }

    for (typed, correction) in &corrections {
        if flags_by_word.get(correction).copied().unwrap_or(0) & WORD_SPELLCHECK == 0 {
            return Err(invalid_data(format!(
                "KLEX correction {typed:?} -> {correction:?} must target a spelling entry"
            )));
        }
    }

    let floor = 5.0_f64;
    let (default_cost, unknown_cost, mut costs) = if let Some(base) = base.as_ref() {
        let default_cost = base.default_cost();
        let total = floor * 10_f64.powf(default_cost as f64);
        let mut costs = base_costs;
        for word in overlay_words {
            if costs.contains_key(&word) {
                continue;
            }
            let count = counts.get(&word).copied().unwrap_or(0.0).max(floor);
            costs.insert(word, -(count / total).log10() as f32);
        }
        (default_cost, base.unknown_cost(), costs)
    } else {
        let total = counts
            .values()
            .map(|count| count.max(floor))
            .sum::<f64>()
            .max(floor);
        let default_cost = -(floor / total).log10() as f32;
        let costs = flags_by_word
            .keys()
            .map(|word| {
                let count = counts.get(word).copied().unwrap_or(0.0).max(floor);
                (word.clone(), -(count / total).log10() as f32)
            })
            .collect();
        (default_cost, default_cost + 5.0, costs)
    };
    // Match the Python KDIC compiler: aliases participate only in the compact
    // segmentation table and never become canonical spelling/completion forms.
    for (word, flags) in flags_by_word.clone() {
        if flags & WORD_SEGMENT == 0 {
            continue;
        }
        for alias in coeng_da_ta_variants(&word) {
            let alias_flags = flags & (WORD_SEGMENT | WORD_SUPPLEMENTAL);
            if let Some(existing) = flags_by_word.get_mut(&alias) {
                *existing |= alias_flags;
            } else {
                flags_by_word.insert(alias.clone(), alias_flags);
                costs.insert(alias, costs[&word]);
            }
        }
    }
    let segmentation_words: Vec<_> = flags_by_word
        .iter()
        .filter_map(|(word, flags)| (flags & WORD_SEGMENT != 0).then_some(word.clone()))
        .collect();
    let required_size = ((segmentation_words.len() as f64 / 0.70).ceil() as usize).max(2);
    let table_size = required_size.next_power_of_two();

    let mut pool = vec![0_u8];
    let mut offsets = BTreeMap::new();
    for word in flags_by_word.keys() {
        offsets.insert(word.clone(), pool.len() as u32);
        pool.extend_from_slice(word.as_bytes());
        pool.push(0);
    }
    let mut table = vec![(0_u32, 0_f32); table_size];
    for word in &segmentation_words {
        let mut slot =
            khmer_segmenter::utils::djb2_hash(word.as_bytes()) as usize & (table_size - 1);
        while table[slot].0 != 0 {
            slot = (slot + 1) & (table_size - 1);
        }
        table[slot] = (offsets[word], costs[word]);
    }

    let extension_offset = 32 + table_size * 8 + pool.len();
    let mut output = Vec::new();
    output.extend_from_slice(b"KDIC");
    output.extend_from_slice(&2_u32.to_le_bytes());
    output.extend_from_slice(&(segmentation_words.len() as u32).to_le_bytes());
    output.extend_from_slice(&(table_size as u32).to_le_bytes());
    output.extend_from_slice(&default_cost.to_le_bytes());
    output.extend_from_slice(&unknown_cost.to_le_bytes());
    let max_word_bytes = segmentation_words
        .iter()
        .map(|word| word.len() as u32)
        .max()
        .unwrap_or(0);
    output.extend_from_slice(&max_word_bytes.to_le_bytes());
    output.extend_from_slice(&(extension_offset as u32).to_le_bytes());
    for (offset, cost) in table {
        output.extend_from_slice(&offset.to_le_bytes());
        output.extend_from_slice(&cost.to_le_bytes());
    }
    output.extend_from_slice(&pool);
    output.extend_from_slice(b"KDX2");
    output.extend_from_slice(&1_u32.to_le_bytes());
    output.extend_from_slice(&(flags_by_word.len() as u32).to_le_bytes());
    output.extend_from_slice(&(corrections.len() as u32).to_le_bytes());
    for (word, flags) in &flags_by_word {
        output.extend_from_slice(&offsets[word].to_le_bytes());
        output.extend_from_slice(&flags.to_le_bytes());
        output.extend_from_slice(&costs[word].to_le_bytes());
    }
    for (typed, correction) in &corrections {
        output.extend_from_slice(&offsets[typed].to_le_bytes());
        output.extend_from_slice(&offsets[correction].to_le_bytes());
    }
    if let Some(parent) = Path::new(output_path).parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(output_path, output)?;
    Ok(())
}

fn run_data_compile(args: &[String]) -> io::Result<()> {
    let mut source = None;
    let mut output = None;
    let mut base = None;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--output" | "-o" => {
                index += 1;
                output = args.get(index).cloned();
            }
            "--base" => {
                index += 1;
                base = args.get(index).cloned();
            }
            value if value.starts_with('-') => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    format!("unknown data compile option: {value}"),
                ));
            }
            value if source.is_none() => source = Some(value.to_owned()),
            value => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    format!("unexpected data compile argument: {value}"),
                ));
            }
        }
        index += 1;
    }
    let source = source.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "data compile requires a KLEX file",
        )
    })?;
    let output = output.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "data compile requires --output",
        )
    })?;
    compile_klex(&source, &output, base.as_deref())?;
    println!("Compiled unified KDIC v2 pack: {output}");
    Ok(())
}

fn default_dictionary_path() -> Option<&'static str> {
    [
        "khmer_dictionary.kdict",
        "../../port/common/khmer_dictionary.kdict",
        "../common/khmer_dictionary.kdict",
        "c:/Users/Sovichea/Documents/git/khmer_segmenter/port/common/khmer_dictionary.kdict",
    ]
    .into_iter()
    .find(|path| Path::new(path).exists())
}

fn run_diagnose(args: &[String], include_segments: bool) -> io::Result<()> {
    let mut profile = SpellcheckProfile::Typing;
    let mut accuracy = SpellingAccuracy::Lexical;
    let mut dictionary: Option<String> = None;
    let mut input: Option<String> = None;
    let mut format = "json";
    let mut text_parts = Vec::new();
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--profile" => {
                index += 1;
                let value = args.get(index).ok_or_else(|| {
                    io::Error::new(io::ErrorKind::InvalidInput, "--profile requires a value")
                })?;
                profile = value
                    .parse()
                    .map_err(|error: String| io::Error::new(io::ErrorKind::InvalidInput, error))?;
            }
            "--accuracy" => {
                index += 1;
                let value = args.get(index).ok_or_else(|| {
                    io::Error::new(io::ErrorKind::InvalidInput, "--accuracy requires a value")
                })?;
                accuracy = value
                    .parse()
                    .map_err(|error: String| io::Error::new(io::ErrorKind::InvalidInput, error))?;
            }
            "--dictionary" | "--data" => {
                index += 1;
                dictionary = Some(
                    args.get(index)
                        .ok_or_else(|| {
                            io::Error::new(
                                io::ErrorKind::InvalidInput,
                                "--dictionary requires a path",
                            )
                        })?
                        .clone(),
                );
            }
            "--input" | "-i" => {
                index += 1;
                input = Some(
                    args.get(index)
                        .ok_or_else(|| {
                            io::Error::new(io::ErrorKind::InvalidInput, "--input requires a path")
                        })?
                        .clone(),
                );
            }
            "--format" => {
                index += 1;
                format = args.get(index).map(String::as_str).ok_or_else(|| {
                    io::Error::new(io::ErrorKind::InvalidInput, "--format requires a value")
                })?;
                if !matches!(format, "json" | "jsonl" | "plain") {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidInput,
                        "--format must be json, jsonl, or plain",
                    ));
                }
            }
            value if value.starts_with('-') => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    format!("unknown diagnose option: {value}"),
                ));
            }
            value => text_parts.push(value.to_owned()),
        }
        index += 1;
    }

    if input.is_some() && !text_parts.is_empty() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "provide text or --input, not both",
        ));
    }
    let text = if let Some(path) = input {
        std::fs::read_to_string(path)?
    } else if !text_parts.is_empty() {
        text_parts.join(" ")
    } else {
        let mut value = String::new();
        io::stdin().read_to_string(&mut value)?;
        value
    };
    let dictionary = dictionary.or_else(|| default_dictionary_path().map(str::to_owned));
    let segmenter = KhmerSegmenter::new(dictionary.as_deref(), SegmenterConfig::default())
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error.to_string()))?;
    let analysis = segmenter
        .analyze_text_with_accuracy(&text, profile, accuracy)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error.to_string()))?;
    let normalized = analysis.segmentation.normalized().to_owned();
    let segments: Vec<_> = analysis
        .segmentation
        .ranges()
        .iter()
        .zip(analysis.segmentation.mapped_segments())
        .map(|(range, mapped)| {
            let word = &normalized[range.clone()];
            serde_json::json!({
                "text": word,
                "start": range.start,
                "end": range.end,
                "source_start": mapped.source_range.start,
                "source_end": mapped.source_range.end,
                "known": segmenter.is_known_word(word),
                "spelling_valid": segmenter.is_spelling_valid_with_accuracy(word, accuracy),
            })
        })
        .collect();
    let diagnostics = analysis.diagnostics;

    if format == "plain" {
        for diagnostic in diagnostics {
            let suggestion = diagnostic
                .suggestions
                .first()
                .map(|item| item.text.as_str())
                .unwrap_or("");
            println!(
                "{}\t{}\t{}\t{:.3}\t{}",
                diagnostic.range.start,
                diagnostic.range.end,
                diagnostic.text,
                diagnostic.confidence,
                suggestion
            );
        }
        return Ok(());
    }

    let diagnostics: Vec<_> = diagnostics
        .into_iter()
        .map(|diagnostic| {
            serde_json::json!({
                "text": diagnostic.text,
                "start": diagnostic.range.start,
                "end": diagnostic.range.end,
                "source_start": diagnostic.source_range.start,
                "source_end": diagnostic.source_range.end,
                "kind": diagnostic.kind.as_str(),
                "confidence": diagnostic.confidence,
                "suggestions": diagnostic.suggestions.into_iter().map(|suggestion| {
                    serde_json::json!({
                        "text": suggestion.text,
                        "edit_cost": suggestion.edit_cost,
                    })
                }).collect::<Vec<_>>(),
            })
        })
        .collect();
    let mut record = serde_json::json!({
        "text": text,
        "profile": profile.as_str(),
        "diagnostics": diagnostics,
    });
    if include_segments {
        record["normalized"] = serde_json::Value::String(normalized);
        record["segments"] = serde_json::Value::Array(segments);
    }
    if format == "jsonl" {
        println!("{record}");
    } else {
        println!(
            "{}",
            serde_json::to_string_pretty(&record)
                .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?
        );
    }
    Ok(())
}

#[cfg(target_os = "linux")]
fn get_memory_mb() -> f64 {
    use std::fs::File;
    use std::io::{BufRead, BufReader};

    if let Ok(file) = File::open("/proc/self/status") {
        let reader = BufReader::new(file);
        for line in reader.lines() {
            if let Ok(l) = line {
                if l.starts_with("VmRSS:") {
                    let parts: Vec<&str> = l.split_whitespace().collect();
                    if parts.len() >= 2 {
                        if let Ok(kb) = parts[1].parse::<f64>() {
                            return kb / 1024.0;
                        }
                    }
                }
            }
        }
    }
    0.0
}

#[cfg(not(target_os = "linux"))]
fn get_memory_mb() -> f64 {
    0.0
}

fn main() -> io::Result<()> {
    // Config defaults
    let mut config = SegmenterConfig::default();
    let mut input_files = Vec::new();
    let mut output_file: Option<String> = None;
    let mut input_text: Option<String> = None;
    let mut mode_benchmark = false;
    let mut threads = 4;
    let mut limit: i32 = -1;
    let mut test_hyphenation_word: Option<String> = None;
    let mut dictionary_path: Option<String> = None;

    let args: Vec<String> = env::args().collect();
    if args.get(1).map(String::as_str) == Some("diagnose") {
        return run_diagnose(&args[2..], false);
    }
    if args.get(1).map(String::as_str) == Some("analyze") {
        return run_diagnose(&args[2..], true);
    }
    if args.get(1).map(String::as_str) == Some("data")
        && args.get(2).map(String::as_str) == Some("compile")
    {
        return run_data_compile(&args[3..]);
    }
    let mut i = 1;
    while i < args.len() {
        let arg = &args[i];
        if arg == "--benchmark" || arg == "--bench" {
            mode_benchmark = true;
            eprintln!("DEBUG: Set benchmark match {}", arg);
        } else if arg == "--dictionary" || arg == "--kdict" {
            if i + 1 < args.len() {
                dictionary_path = Some(args[i + 1].clone());
                i += 1;
            }
        } else if arg == "--input" || arg == "--file" {
            eprintln!("DEBUG: Found input flag at {}", i);
            while i + 1 < args.len() && !args[i + 1].starts_with('-') {
                eprintln!("DEBUG: Pushing input file: {}", args[i + 1]);
                input_files.push(args[i + 1].clone());
                i += 1;
            }
        } else if arg == "--output" {
            if i + 1 < args.len() {
                output_file = Some(args[i + 1].clone());
                i += 1;
            }
        } else if arg == "--threads" {
            if i + 1 < args.len() {
                threads = args[i + 1].parse().unwrap_or(4);
                i += 1;
            }
        } else if arg == "--limit" {
            if i + 1 < args.len() {
                limit = args[i + 1].parse().unwrap_or(-1);
                i += 1;
            }
        } else if arg == "--no-norm" {
            config.enable_normalization = false;
        } else if arg == "--no-repair" {
            config.enable_repair_mode = false;
        } else if arg == "--no-acronym" {
            config.enable_acronym_detection = false;
        } else if arg == "--no-merging" {
            config.enable_unknown_merging = false;
        } else if arg == "--no-freq" {
            config.enable_frequency_costs = false; // Not used in binary dict but kept for compat
        } else if arg == "--short" {
            config.segmentation_length = SegmentationLength::Short;
        } else if arg == "--long" {
            config.segmentation_length = SegmentationLength::Long;
        } else if arg == "--segmentation-length" || arg == "--length" {
            if i + 1 < args.len() {
                match args[i + 1].as_str() {
                    "short" => config.segmentation_length = SegmentationLength::Short,
                    "long" => config.segmentation_length = SegmentationLength::Long,
                    value => eprintln!(
                        "WARNING: Unknown segmentation length '{}'; expected 'long' or 'short'",
                        value
                    ),
                }
                i += 1;
            }
        } else if let Some(value) = arg.strip_prefix("--segmentation-length=") {
            match value {
                "short" => config.segmentation_length = SegmentationLength::Short,
                "long" => config.segmentation_length = SegmentationLength::Long,
                value => eprintln!(
                    "WARNING: Unknown segmentation length '{}'; expected 'long' or 'short'",
                    value
                ),
            }
        } else if let Some(value) = arg.strip_prefix("--length=") {
            match value {
                "short" => config.segmentation_length = SegmentationLength::Short,
                "long" => config.segmentation_length = SegmentationLength::Long,
                value => eprintln!(
                    "WARNING: Unknown segmentation length '{}'; expected 'long' or 'short'",
                    value
                ),
            }
        } else if arg == "--test-hyphenation" {
            if i + 1 < args.len() {
                test_hyphenation_word = Some(args[i + 1].clone());
                i += 1;
            }
        } else if arg == "--hyphenate-sentence" {
            if i + 1 < args.len() {
                input_text = Some(args[i + 1].clone());
                test_hyphenation_word = Some("SENTENCE_TEST".to_string()); // flag
                i += 1;
            }
        } else if !arg.starts_with('-') {
            if let Some(ref mut text) = input_text {
                text.push(' ');
                text.push_str(arg);
            } else {
                input_text = Some(arg.clone());
            }
        }
        i += 1;
    }

    eprintln!("DEBUG: Args: {:?}", args);
    eprintln!("DEBUG: Parsed Input Files: {:?}", input_files);
    eprintln!("DEBUG: Benchmark Mode: {}", mode_benchmark);

    if let Some(test_val) = test_hyphenation_word {
        let hyp_paths = [
            "khmer_hyphenation.kdict",
            "../../port/common/khmer_hyphenation.kdict",
            "../common/khmer_hyphenation.kdict",
            "c:/Users/Sovichea/Documents/git/khmer_segmenter/port/common/khmer_hyphenation.kdict",
        ];

        let mut hyp_dict_opt = None;
        for p in &hyp_paths {
            if Path::new(p).exists() {
                if let Ok(d) = khmer_segmenter::kdict::KHypDict::load(p) {
                    hyp_dict_opt = Some(d);
                    break;
                }
            }
        }

        if test_val == "SENTENCE_TEST" {
            if let Some(text) = input_text {
                let dict_path = Some("../../port/common/khmer_dictionary.kdict");
                let seg = KhmerSegmenter::new(dict_path, config).unwrap();
                let segmented = seg.segment(&text, Some(" | "));
                println!("1. Original:   {}", text);
                println!("2. Segmented:  {}", segmented);

                if let Some(dict) = hyp_dict_opt {
                    let mut final_tokens = Vec::new();
                    for token in segmented.split(" | ") {
                        if let Some(hyphenated) = dict.lookup(token) {
                            final_tokens.push(hyphenated.replace('\u{200b}', "-"));
                        } else {
                            final_tokens.push(token.to_string());
                        }
                    }
                    println!("3. Hyphenated: {}", final_tokens.join(" | "));
                }
            }
        } else {
            // Original word test
            println!("Testing hyphenation lookup for: {}", test_val);
            if let Some(dict) = hyp_dict_opt {
                if let Some(hyphenated) = dict.lookup(&test_val) {
                    println!("Match found!");
                    println!("Original: {}", test_val);
                    println!("Hyphenated: {}", hyphenated.replace('\u{200b}', "-"));
                } else {
                    println!("No hyphenation found for '{}'", test_val);
                }
            } else {
                println!("Error: Could not load khmer_hyphenation.kdict from any default paths.");
            }
        }
        return Ok(());
    }
    if !input_files.is_empty() && output_file.is_none() {
        output_file = Some("segmentation_results.txt".to_string());
    }

    // Locate Dictionary
    let dict_paths = [
        "khmer_dictionary.kdict",
        "../../port/common/khmer_dictionary.kdict",
        "../common/khmer_dictionary.kdict", // Just in case
        "c:/Users/Sovichea/Documents/git/khmer_segmenter/port/common/khmer_dictionary.kdict", // Absolute fallback
    ];

    let mut dict_path = dictionary_path.as_deref();
    if dict_path.is_none() {
        for p in &dict_paths {
            if Path::new(p).exists() {
                dict_path = Some(p);
                break;
            }
        }
    }

    if mode_benchmark || !input_files.is_empty() {
        eprintln!("Initializing segmenter (Dict: {:?})...", dict_path);
    }

    let seg = match KhmerSegmenter::new(dict_path, config) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Failed to init segmenter: {}", e);
            return Ok(());
        }
    };

    if mode_benchmark || !input_files.is_empty() {
        eprintln!("Initialization complete.");
    }

    // Set thread pool? Rayon auto-configures but we can force it if we want strict control.
    rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build_global()
        .unwrap();

    if mode_benchmark {
        if !input_files.is_empty() {
            let mut lines = Vec::new();
            let mut current_limit = limit;

            eprintln!("DEBUG: Input files: {:?}", input_files);

            for file in &input_files {
                eprintln!("DEBUG: Reading file: {}", file);
                let f = File::open(file)?;
                let reader = BufReader::new(f);
                for line in reader.lines() {
                    if limit != -1 && current_limit <= 0 {
                        break;
                    }
                    if let Ok(l) = line {
                        // Remove BOM
                        let clean = if l.starts_with("\u{FEFF}") {
                            l.chars().skip(1).collect()
                        } else {
                            l
                        };
                        let clean_trimmed = clean.trim().to_string();
                        lines.push(clean_trimmed);
                        if limit != -1 {
                            current_limit -= 1;
                        }
                    }
                }
                if limit != -1 && current_limit <= 0 {
                    break;
                }
            }
            eprintln!("DEBUG: Read {} lines", lines.len());

            // Calculate size
            let total_bytes: usize = lines.iter().map(|l| l.len()).sum();
            let total_mb = total_bytes as f64 / (1024.0 * 1024.0);

            eprintln!(
                "\n--- Input Benchmark ({} lines, {:.2} MB) ---",
                lines.len(),
                total_mb
            );
            let start_mem = get_memory_mb();
            eprintln!("Initial Memory: {:.2} MB", start_mem);

            // 1. Sequential
            eprint!("[1 Thread] Processing...");
            let start_mem = get_memory_mb();
            let start = Instant::now();
            let results_seq: Vec<String> =
                lines.iter().map(|l| seg.segment(l, Some(" | "))).collect();
            let duration = start.elapsed();
            let end_mem = get_memory_mb();
            eprintln!(
                " Done in {:.3}s ({:.2} lines/sec)",
                duration.as_secs_f64(),
                lines.len() as f64 / duration.as_secs_f64()
            );
            eprintln!("Mem Delta: {:.2} MB", end_mem - start_mem);

            if let Some(out_path) = &output_file {
                let mut f = File::create(out_path)?;
                for (orig, res) in lines.iter().zip(results_seq.iter()) {
                    writeln!(f, "Original:  {}", orig)?;
                    writeln!(f, "Segmented: {}", res)?;
                    writeln!(f, "----------------------------------------")?;
                }
                eprintln!("Results saved to {}", out_path);
            }

            // 2. Parallel
            if threads > 1 {
                eprint!("[{} Threads] Processing...", threads);
                let start_mem = get_memory_mb();
                let start = Instant::now();
                let _results_par: Vec<String> = lines
                    .par_iter()
                    .map(|l| seg.segment(l, Some(" | ")))
                    .collect();
                let duration_par = start.elapsed();
                let end_mem = get_memory_mb();
                eprintln!(
                    " Done in {:.3}s ({:.2} lines/sec)",
                    duration_par.as_secs_f64(),
                    lines.len() as f64 / duration_par.as_secs_f64()
                );
                eprintln!("Mem Delta: {:.2} MB", end_mem - start_mem);
                eprintln!(
                    "Speedup: {:.2}x",
                    duration.as_secs_f64() / duration_par.as_secs_f64()
                );
            }
        } else {
            // Standard text benchmark
            let text = "ក្រុមហ៊ុនទទួលបានប្រាក់ចំណូល ១ ០០០ ០០០ ដុល្លារក្នុងឆ្នាំនេះ ខណៈដែលតម្លៃភាគហ៊ុនកើនឡើង ៥% ស្មើនឹង 50.00$។លោក ទេព សុវិចិត្រ នាយកប្រតិបត្តិដែលបញ្ចប់ការសិក្សាពីសាកលវិទ្យាល័យភូមិន្ទភ្នំពេញ (ស.ភ.ភ.ព.) បានថ្លែងថា ភាពជោគជ័យផ្នែកហិរញ្ញវត្ថុនាឆ្នាំនេះ គឺជាសក្ខីភាពនៃកិច្ចខិតខំប្រឹងប្រែងរបស់ក្រុមការងារទាំងមូល និងការជឿទុកចិត្តពីសំណាក់វិនិយោគិន។";
            let iterations_seq = 1000;
            let iterations_conc = 5000;

            println!("\n--- Benchmark Suite ---");
            println!("Text Length: {} chars", text.chars().count());
            println!("Initial Memory: {:.2} MB", get_memory_mb());

            // Warmup
            let check = seg.segment(text, Some(" | "));
            println!("\n[Output Check]\n{}\n", check);

            if let Some(out_path) = output_file {
                let mut f = File::create(out_path)?;
                writeln!(f, "Original:  {}", text)?;
                writeln!(f, "Segmented: {}", check)?;
                writeln!(f, "----------------------------------------")?;
            } else {
                let mut f = File::create("benchmark_results.txt")?;
                writeln!(f, "Original:  {}", text)?;
                writeln!(f, "Segmented: {}", check)?;
                writeln!(f, "----------------------------------------")?;
            }

            // Sequential
            println!("\n[Sequential] Running {} iterations...", iterations_seq);
            let start_mem = get_memory_mb();
            let start = Instant::now();
            for _ in 0..iterations_seq {
                let _ = seg.segment(text, None); // NULL separator in C means "no separator"? No, C uses default if NULL. BUT benchmark passes NULL?
                                                 // In C benchmark loop: khmer_segmenter_segment(seg, text, NULL);
                                                 // In C khmer_segmenter_segment: if (!separator) separator = "\xE2\x80\x8B";
                                                 // In Rust segment: if separator is None, use ZWS.
            }
            let duration = start.elapsed();
            let end_mem = get_memory_mb();
            println!("Time: {:.3}s", duration.as_secs_f64());
            println!(
                "Avg: {:.3} ms/call",
                (duration.as_secs_f64() * 1000.0) / iterations_seq as f64
            );
            println!("Mem Delta: {:.2} MB", end_mem - start_mem);

            // Concurrent
            println!(
                "\n[Concurrent] Running {} iterations with {} threads...",
                iterations_conc, threads
            );
            let start_mem = get_memory_mb();
            let start = Instant::now();
            (0..iterations_conc).into_par_iter().for_each(|_| {
                let _ = seg.segment(text, None);
            });
            let duration = start.elapsed();
            let end_mem = get_memory_mb();
            println!("Time: {:.3}s", duration.as_secs_f64());
            println!(
                "Throughput: {:.2} calls/sec",
                iterations_conc as f64 / duration.as_secs_f64()
            );
            println!("Mem Delta: {:.2} MB", end_mem - start_mem);
        }
    } else if !input_files.is_empty() {
        let mut out: Box<dyn Write> = if let Some(path) = output_file {
            Box::new(File::create(path)?)
        } else {
            Box::new(io::stdout())
        };

        let mut lines = Vec::new();
        let mut current_limit = limit;
        for file in &input_files {
            let f = File::open(file)?;
            let reader = BufReader::new(f);
            for line in reader.lines() {
                if limit != -1 && current_limit <= 0 {
                    break;
                }
                if let Ok(l) = line {
                    // Remove BOM
                    let clean = if l.starts_with("\u{FEFF}") {
                        l.chars().skip(1).collect()
                    } else {
                        l
                    };
                    lines.push(clean);
                    if limit != -1 {
                        current_limit -= 1;
                    }
                }
            }
            if limit != -1 && current_limit <= 0 {
                break;
            }
        }

        // Use parallel processing if threads > 1
        if threads > 1 {
            let results: Vec<String> = lines
                .par_iter()
                .map(|l| seg.segment(l, Some(" | ")))
                .collect();

            for (orig, res) in lines.iter().zip(results.iter()) {
                writeln!(out, "Original:  {}", orig)?;
                writeln!(out, "Segmented: {}", res)?;
                writeln!(out, "----------------------------------------")?;
            }
        } else {
            for l in lines {
                let res = seg.segment(&l, Some(" | "));
                writeln!(out, "Original:  {}", l)?;
                writeln!(out, "Segmented: {}", res)?;
                writeln!(out, "----------------------------------------")?;
            }
        }
    } else if let Some(text) = input_text {
        let res = seg.segment(&text, Some(" | "));
        println!("Input: {}", text);
        println!("Output: {}", res);

        // Save
        let out_path = output_file.unwrap_or("segmentation_results.txt".to_string());
        let mut f = File::create(&out_path)?;
        writeln!(f, "Original:  {}", text)?;
        writeln!(f, "Segmented: {}", res)?;
        writeln!(f, "----------------------------------------")?;
        eprintln!("Results saved to {}", out_path);
    } else {
        println!("Usage: khmer_segmenter.exe [flags] [text]");
        println!("  --input <path...> Multiple input files");
        println!("  --dictionary <path> Unified KDIC v2 language pack");
        println!("  --output <path>   Output file path");
        println!("  --limit <N>       Limit total lines processed");
        println!("  --threads <N>     Number of threads (default: 4)");
        println!("  --benchmark       Run benchmark (uses --input if provided)");
        println!("  --segmentation-length <long|short>");
        println!(
            "                    Long is best for word suggestion; short is best for rendering"
        );
        println!("  --long            Alias for --segmentation-length long");
        println!("  --short           Alias for --segmentation-length short");
        println!("  --test-hyphenation <word> Test lookup in khmer_hyphenation.kdict");
        println!("  --hyphenate-sentence <text> Segment text and apply hyphenation");
        println!("  diagnose [--profile typing|document|high-recall] [--accuracy lexical|visual] <text>");
        println!("                    Return spellcheck diagnostics as JSON");
        println!("  analyze [--profile typing|document|high-recall] [--accuracy lexical|visual] <text>");
        println!("                    Return mapped segments and diagnostics in one pass");
        println!("  data compile <file.klex.json> --output <file.kdict> [--base <base.kdict>]");
        println!("                    Compile a unified KDIC v2 language pack");
        println!("  <text>            Process raw text");
    }

    Ok(())
}

#[cfg(test)]
mod cli_tests {
    use super::*;
    use khmer_segmenter::kdict::{KDict, WORD_SEGMENT, WORD_SPELLCHECK, WORD_TYPO_SURFACE};

    #[test]
    fn native_cli_compiler_writes_unified_policy_and_corrections() {
        let stem = format!("khmer-klex-test-{}", std::process::id());
        let source = std::env::temp_dir().join(format!("{stem}.json"));
        let output = std::env::temp_dir().join(format!("{stem}.kdict"));
        let overlay_source = std::env::temp_dir().join(format!("{stem}-overlay.json"));
        let overlay_output = std::env::temp_dir().join(format!("{stem}-overlay.kdict"));
        std::fs::write(&source, include_str!("../../../examples/custom.klex.json")).unwrap();
        compile_klex(source.to_str().unwrap(), output.to_str().unwrap(), None).unwrap();

        let dictionary = KDict::load(&output).unwrap();
        assert_eq!(dictionary.version(), 2);
        let entries: BTreeMap<_, _> = dictionary
            .lexical_entries()
            .into_iter()
            .map(|entry| (entry.word.clone(), entry))
            .collect();
        assert_eq!(
            entries["ដេល"].flags & (WORD_SEGMENT | WORD_SPELLCHECK | WORD_TYPO_SURFACE),
            WORD_SEGMENT | WORD_TYPO_SURFACE
        );
        assert!(dictionary
            .typo_corrections()
            .contains(&("ដេល".to_owned(), "ដែល".to_owned())));

        let preserved = dictionary.lexical_entries().into_iter().next().unwrap();
        std::fs::write(
            &overlay_source,
            r#"{"version":1,"entries":[{"word":"customword","uses":["segmentation","spelling"],"frequency":5}]}"#,
        )
        .unwrap();
        compile_klex(
            overlay_source.to_str().unwrap(),
            overlay_output.to_str().unwrap(),
            Some(output.to_str().unwrap()),
        )
        .unwrap();
        let overlay = KDict::load(&overlay_output).unwrap();
        assert!(overlay
            .lexical_entries()
            .iter()
            .any(|entry| entry.word == "customword"));
        assert_eq!(
            overlay
                .lexical_entries()
                .iter()
                .find(|entry| entry.word == preserved.word)
                .unwrap()
                .cost,
            preserved.cost
        );
        assert_eq!(overlay.typo_corrections(), dictionary.typo_corrections());

        let _ = std::fs::remove_file(source);
        let _ = std::fs::remove_file(output);
        let _ = std::fs::remove_file(overlay_source);
        let _ = std::fs::remove_file(overlay_output);
    }
}
