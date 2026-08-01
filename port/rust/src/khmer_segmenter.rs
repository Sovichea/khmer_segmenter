use crate::kdict::KDict;
use crate::normalization::{
    khmer_normalize, khmer_normalize_mapped, MappedNormalization, NormalizedUnit,
};
use crate::rule_engine::RuleEngine;
use crate::spelling::{
    SpellcheckConfig, SpellcheckProfile, SpellingDiagnostic, SpellingSuggestion, TypoDetector,
};
use crate::utils;
use std::fmt;
use std::ops::Range;
#[cfg(not(target_arch = "wasm32"))]
use std::path::Path;
use std::sync::OnceLock;
// For handling null-terminated strings in KDict (Removed CStr)

#[derive(Clone)]
pub struct SegmenterConfig {
    pub enable_normalization: bool,
    pub enable_repair_mode: bool,
    pub enable_acronym_detection: bool,
    pub enable_unknown_merging: bool,
    pub enable_frequency_costs: bool,
    pub segmentation_length: SegmentationLength,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SegmentationLength {
    Long,
    Short,
}

impl Default for SegmenterConfig {
    fn default() -> Self {
        Self {
            enable_normalization: true,
            enable_repair_mode: true,
            enable_acronym_detection: true,
            enable_unknown_merging: true,
            enable_frequency_costs: true,
            segmentation_length: SegmentationLength::Long,
        }
    }
}

pub struct KhmerSegmenter {
    kdict: Option<KDict>,
    typo_detector: OnceLock<TypoDetector>,
    rule_engine: RuleEngine,
    config: SegmenterConfig,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Segmentation {
    normalized: String,
    ranges: Vec<Range<usize>>,
    mapped_segments: Vec<MappedSegment>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MappedSegment {
    pub normalized_range: Range<usize>,
    pub source_range: Range<usize>,
}

impl Segmentation {
    pub fn normalized(&self) -> &str {
        &self.normalized
    }

    pub fn ranges(&self) -> &[Range<usize>] {
        &self.ranges
    }

    pub fn mapped_segments(&self) -> &[MappedSegment] {
        &self.mapped_segments
    }

    pub fn tokens(&self) -> impl ExactSizeIterator<Item = &str> {
        self.ranges
            .iter()
            .map(|range| &self.normalized[range.clone()])
    }

    pub fn boundaries(&self) -> impl Iterator<Item = usize> + '_ {
        self.ranges
            .iter()
            .take(self.ranges.len().saturating_sub(1))
            .map(|range| range.end)
    }

    pub fn join(&self, separator: &str) -> String {
        let extra = separator
            .len()
            .saturating_mul(self.ranges.len().saturating_sub(1));
        let mut output = String::with_capacity(self.normalized.len() + extra);
        for (index, token) in self.tokens().enumerate() {
            if index > 0 {
                output.push_str(separator);
            }
            output.push_str(token);
        }
        output
    }
}

#[derive(Debug)]
pub enum SegmentationError {
    MissingDictionary,
    NoSegmentationPath,
}

impl fmt::Display for SegmentationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::MissingDictionary => formatter.write_str("Khmer dictionary is not loaded"),
            Self::NoSegmentationPath => formatter.write_str("No valid segmentation path was found"),
        }
    }
}

impl std::error::Error for SegmentationError {}

#[derive(Clone, Copy)]
struct State {
    cost: f32,
    prev_idx: isize,
}

impl KhmerSegmenter {
    pub fn new(kdict_path: Option<&str>, config: SegmenterConfig) -> std::io::Result<Self> {
        match kdict_path {
            Some(path) => Self::from_path(path, config),
            None => Ok(Self::new_with_dict(None, config)),
        }
    }

    #[cfg(not(target_arch = "wasm32"))]
    pub fn from_path(path: impl AsRef<Path>, config: SegmenterConfig) -> std::io::Result<Self> {
        Ok(Self::new_with_dict(Some(KDict::load(path)?), config))
    }

    #[cfg(target_arch = "wasm32")]
    pub fn from_path(_path: impl AsRef<str>, _config: SegmenterConfig) -> std::io::Result<Self> {
        Err(std::io::Error::new(
            std::io::ErrorKind::Unsupported,
            "File loading is not supported on WASM; use from_bytes",
        ))
    }

    pub fn from_bytes(bytes: impl Into<Vec<u8>>, config: SegmenterConfig) -> std::io::Result<Self> {
        Ok(Self::new_with_dict(
            Some(KDict::from_bytes(bytes.into())?),
            config,
        ))
    }

    pub fn new_with_dict(kdict: Option<KDict>, config: SegmenterConfig) -> Self {
        Self {
            kdict,
            typo_detector: OnceLock::new(),
            rule_engine: RuleEngine::new(),
            config,
        }
    }

    // Helper to access string pool (Unsafe) - Removed in favor of direct byte access

    pub fn segment_detailed(&self, raw_text: &str) -> Result<Segmentation, SegmentationError> {
        let normalization = if self.config.enable_normalization {
            khmer_normalize_mapped(raw_text)
        } else {
            MappedNormalization {
                text: raw_text.to_owned(),
                units: raw_text
                    .char_indices()
                    .map(|(start, character)| NormalizedUnit {
                        text: character.to_string(),
                        source_range: start..start + character.len_utf8(),
                    })
                    .collect(),
            }
        };
        let text_owned = normalization.text.clone();
        let text = &text_owned;
        let n = text.len();

        if n == 0 {
            return Ok(Segmentation {
                normalized: text_owned,
                ranges: Vec::new(),
                mapped_segments: Vec::new(),
            });
        }

        // DP Table
        let mut dp = vec![
            State {
                cost: 1e9,
                prev_idx: -1
            };
            n + 1
        ];
        dp[0].cost = 0.0;

        // Dictionary Accessors
        let (header, table, mask) = if let Some(ref kd) = self.kdict {
            unsafe { (&*kd.header, kd.table, kd.table_mask) }
        } else {
            return Err(SegmentationError::MissingDictionary);
        };

        let mut i = 0;

        while i < n {
            // Skip unreachable
            if dp[i].cost >= 1e9 {
                if let Some(c) = text[i..].chars().next() {
                    let clen = c.len_utf8();
                    i += clen;
                } else {
                    i += 1;
                }
                continue;
            }

            let c = text[i..].chars().next().unwrap();
            let char_len = c.len_utf8();

            // Repair Mode
            if self.config.enable_repair_mode {
                let mut force_repair = false;
                if c >= '\u{17B6}' && c <= '\u{17C5}' {
                    force_repair = true;
                }

                if force_repair {
                    let next_idx = i + char_len;
                    let repair_cost = header.unknown_cost + 50.0;
                    if next_idx <= n && dp[i].cost + repair_cost < dp[next_idx].cost {
                        dp[next_idx].cost = dp[i].cost + repair_cost;
                        dp[next_idx].prev_idx = i as isize;
                    }
                    i += char_len;
                    continue;
                }
            }

            // Numbers
            let is_dig = utils::is_digit_cp(c);

            if is_dig {
                let num_len = utils::get_number_length(&text[i..]);
                let next_idx = i + num_len;
                let step_cost = 1.0;
                if next_idx <= n && dp[i].cost + step_cost < dp[next_idx].cost {
                    dp[next_idx].cost = dp[i].cost + step_cost;
                    dp[next_idx].prev_idx = i as isize;
                }
            } else if utils::is_separator_cp(c) {
                let next_idx = i + char_len;
                let step_cost = 0.1;
                if next_idx <= n && dp[i].cost + step_cost < dp[next_idx].cost {
                    dp[next_idx].cost = dp[i].cost + step_cost;
                    dp[next_idx].prev_idx = i as isize;
                }
            }

            // Acronyms
            if self.config.enable_acronym_detection && utils::is_acronym_start(&text[i..]) {
                let acr_len = utils::get_acronym_length(&text[i..]);
                let next_idx = i + acr_len;
                let step_cost = header.default_cost;
                if next_idx <= n && dp[i].cost + step_cost < dp[next_idx].cost {
                    dp[next_idx].cost = dp[i].cost + step_cost;
                    dp[next_idx].prev_idx = i as isize;
                }
            }

            // Dictionary Lookup
            if let Some(ref kd) = self.kdict {
                let max_wl = header.max_word_length as usize;
                let mut khash: u32 = 5381;
                let mut current_offset = i;
                let bytes = text.as_bytes();

                for sub_c in text[i..].chars() {
                    let sc_len = sub_c.len_utf8();
                    if current_offset + sc_len - i > max_wl {
                        break;
                    }

                    // Incremental Hash
                    for b in &bytes[current_offset..current_offset + sc_len] {
                        khash = (khash << 5).wrapping_add(khash).wrapping_add(*b as u32);
                    }

                    current_offset += sc_len;

                    // Lookup
                    let mut idx = khash & mask;
                    loop {
                        let entry = unsafe { &*table.add(idx as usize) };
                        if entry.name_offset == 0 {
                            break;
                        }

                        // Optimized: Pointer-based comparison
                        let len = current_offset - i;
                        let stored_ptr = kd.get_pool_ptr(entry.name_offset);
                        // bytes is a slice, as_ptr is safe.
                        let word_ptr = unsafe { bytes.as_ptr().add(i) };

                        unsafe {
                            // Check first byte, then SIMD body, then sentinel
                            if *stored_ptr == *word_ptr
                                && utils::fast_str_eq(stored_ptr, word_ptr, len)
                                && *stored_ptr.add(len) == 0
                            {
                                let new_cost = dp[i].cost + entry.cost;
                                if new_cost < dp[current_offset].cost {
                                    dp[current_offset].cost = new_cost;
                                    dp[current_offset].prev_idx = i as isize;
                                }
                                break;
                            }
                        }

                        idx = (idx + 1) & mask;
                    }
                }
            }

            // Handle Unknown Clusters
            let cluster_bytes = if utils::is_khmer_char(c) {
                utils::get_khmer_cluster_length(&text[i..])
            } else {
                char_len
            };

            let next_idx = i + cluster_bytes;
            let mut unk_cost = header.unknown_cost;
            if cluster_bytes == char_len && utils::is_khmer_char(c) {
                if !utils::is_valid_single_base_char(c) {
                    unk_cost += 10.0;
                }
            }

            if next_idx <= n {
                let new_cost = dp[i].cost + unk_cost;
                if new_cost < dp[next_idx].cost {
                    dp[next_idx].cost = new_cost;
                    dp[next_idx].prev_idx = i as isize;
                }
            }

            i += char_len;
        }

        // Backtrack
        if dp[n].prev_idx == -1 {
            return Err(SegmentationError::NoSegmentationPath);
        }

        let mut segments: Vec<(usize, usize)> = Vec::with_capacity(n / 2); // Pre-allocate estimate
        let mut curr = n;
        while curr > 0 {
            let prev = dp[curr].prev_idx as usize;
            segments.push((prev, curr));
            curr = prev;
        }
        segments.reverse();

        // Rule Engine
        self.rule_engine.apply(text, &mut segments);

        if self.config.enable_unknown_merging {
            let mut new_segments = Vec::with_capacity(segments.len());

            // Track consecutive unknowns as a single range
            let mut unknown_start: Option<usize> = None;
            let mut unknown_end: usize = 0;

            for (start, end) in segments {
                let seg = &text[start..end];
                let mut is_known = false;

                // Re-validation logic to determine if segment is "Known"
                let char_count = seg.chars().count();
                let first_char = seg.chars().next().unwrap(); // segments are never empty

                // 1. Check Separators (Single char)
                if char_count == 1 {
                    if utils::is_separator_cp(first_char) {
                        is_known = true;
                    } else if utils::is_digit_cp(first_char) {
                        is_known = true;
                    }
                    // Single digit
                    else if utils::is_valid_single_base_char(first_char) {
                        is_known = true;
                    }
                }

                // 2. Check Numbers
                if !is_known {
                    let num_len = utils::get_number_length(seg);
                    if num_len == seg.len() {
                        is_known = true;
                    }
                }

                // 4. Check Acronyms
                if !is_known && self.config.enable_acronym_detection {
                    if utils::is_acronym_start(seg) {
                        let acr_len = utils::get_acronym_length(seg);
                        if acr_len == seg.len() {
                            is_known = true;
                        }
                    }
                }

                // 5. Dictionary Check
                if !is_known {
                    let hash = utils::djb2_hash(seg.as_bytes());
                    let mut idx = hash & mask;
                    loop {
                        let entry = unsafe { &*table.add(idx as usize) };
                        if entry.name_offset == 0 {
                            break;
                        } // Not found
                        let stored_bytes = self
                            .kdict
                            .as_ref()
                            .unwrap()
                            .get_pool_bytes(entry.name_offset);
                        if stored_bytes == seg.as_bytes() {
                            is_known = true;
                            break;
                        }
                        idx = (idx + 1) & mask;
                    }
                }

                if is_known {
                    // Flush unknown buffer if exists
                    if let Some(u_start) = unknown_start {
                        new_segments.push((u_start, unknown_end));
                        unknown_start = None;
                    }
                    new_segments.push((start, end));
                } else {
                    // Extend unknown buffer
                    if let Some(u_start) = unknown_start {
                        // Check script continuity (Fix for mixing Khmer + Latin unknowns)
                        let buffer_text = &text[u_start..unknown_end];
                        if let Some(last_char) = buffer_text.chars().last() {
                            if let Some(curr_char) = seg.chars().next() {
                                if utils::is_khmer_char(last_char)
                                    != utils::is_khmer_char(curr_char)
                                {
                                    // Flush previous buffer
                                    new_segments.push((u_start, unknown_end));
                                    unknown_start = None;
                                }
                            }
                        }
                    }

                    if unknown_start.is_none() {
                        unknown_start = Some(start);
                    }
                    unknown_end = end;
                }
            }

            // Flush remaining unknown buffer
            if let Some(u_start) = unknown_start {
                new_segments.push((u_start, unknown_end));
            }

            segments = new_segments;
        }

        if self.config.segmentation_length == SegmentationLength::Short {
            segments = self.refine_segments_for_short_length(text, &segments);
        }

        let ranges: Vec<Range<usize>> = segments
            .into_iter()
            .map(|(start, end)| start..end)
            .collect();
        let mapped_segments = ranges
            .iter()
            .map(|range| MappedSegment {
                normalized_range: range.clone(),
                source_range: source_range_for(&normalization, range),
            })
            .collect();
        Ok(Segmentation {
            normalized: text_owned,
            ranges,
            mapped_segments,
        })
    }

    pub fn segment(&self, raw_text: &str, separator: Option<&str>) -> String {
        match self.segment_detailed(raw_text) {
            Ok(segmentation) => segmentation.join(separator.unwrap_or("\u{200B}")),
            Err(_) if self.config.enable_normalization => khmer_normalize(raw_text),
            Err(_) => raw_text.to_owned(),
        }
    }

    pub fn is_known_word(&self, word: &str) -> bool {
        self.is_dictionary_word(word)
            || self
                .typo_detector()
                .is_some_and(|detector| detector.is_word(word))
    }

    pub fn suggest_spelling(
        &self,
        word: &str,
        max_edit_cost: f32,
        max_suggestions: usize,
    ) -> Vec<SpellingSuggestion> {
        self.typo_detector()
            .map(|detector| detector.suggest_word(word, max_edit_cost, max_suggestions))
            .unwrap_or_default()
    }

    /// Suggest dictionary words beginning with the supplied prefix.
    pub fn complete_word(&self, prefix: &str, max_suggestions: usize) -> Vec<SpellingSuggestion> {
        self.typo_detector()
            .map(|detector| detector.complete_prefix(prefix, max_suggestions))
            .unwrap_or_default()
    }

    pub fn detect_typos(
        &self,
        raw_text: &str,
        max_edit_cost: f32,
        max_suggestions: usize,
        include_valid_fragments: bool,
    ) -> Result<Vec<SpellingDiagnostic>, SegmentationError> {
        self.check_text_with_config(
            raw_text,
            SpellcheckConfig::new(
                max_edit_cost,
                max_suggestions,
                1,
                include_valid_fragments,
                0.0,
            ),
        )
    }

    /// Check continuous Khmer text with stable integration-oriented defaults.
    pub fn check_text(
        &self,
        raw_text: &str,
        profile: SpellcheckProfile,
    ) -> Result<Vec<SpellingDiagnostic>, SegmentationError> {
        self.check_text_with_config(raw_text, profile.config())
    }

    /// Advanced spellcheck entry point for applications that need custom tuning.
    pub fn check_text_with_config(
        &self,
        raw_text: &str,
        config: SpellcheckConfig,
    ) -> Result<Vec<SpellingDiagnostic>, SegmentationError> {
        let segmentation = self.segment_detailed(raw_text)?;
        Ok(self
            .typo_detector()
            .map(|detector| {
                detector.detect(
                    &segmentation,
                    config.max_edit_cost,
                    config.max_suggestions,
                    config.context_tokens,
                    config.include_valid_fragments,
                )
            })
            .unwrap_or_default()
            .into_iter()
            .filter(|diagnostic| diagnostic.confidence >= config.min_confidence)
            .collect())
    }

    fn typo_detector(&self) -> Option<&TypoDetector> {
        self.kdict.as_ref().map(|dictionary| {
            self.typo_detector
                .get_or_init(|| TypoDetector::from_kdict(dictionary))
        })
    }

    fn refine_segments_for_short_length(
        &self,
        text: &str,
        segments: &[(usize, usize)],
    ) -> Vec<(usize, usize)> {
        let mut refined = Vec::with_capacity(segments.len());

        for &(start, end) in segments {
            let segment_text = &text[start..end];
            if let Some(parts) = self.short_dictionary_partition(segment_text) {
                refined.extend(
                    parts
                        .into_iter()
                        .map(|range| (start + range.start, start + range.end)),
                );
            } else {
                refined.push((start, end));
            }
        }

        refined
    }

    fn short_dictionary_partition(&self, text: &str) -> Option<Vec<Range<usize>>> {
        if text.is_empty() || !text.is_char_boundary(0) {
            return None;
        }

        let char_boundaries: Vec<usize> = text
            .char_indices()
            .map(|(index, _)| index)
            .chain(std::iter::once(text.len()))
            .collect();
        if char_boundaries.len() <= 2 {
            return None;
        }

        let mut best: Vec<Option<Vec<Range<usize>>>> = vec![None; text.len() + 1];
        best[0] = Some(Vec::new());

        for &start in &char_boundaries {
            let Some(prefix) = best[start].clone() else {
                continue;
            };

            for &end in char_boundaries.iter().filter(|&&end| end > start) {
                let candidate = &text[start..end];
                if !self.is_short_segmentation_part(candidate) {
                    continue;
                }

                let mut candidate_parts = prefix.clone();
                candidate_parts.push(start..end);

                let should_replace = best[end]
                    .as_ref()
                    .map(|current| candidate_parts.len() > current.len())
                    .unwrap_or(true);
                if should_replace {
                    best[end] = Some(candidate_parts);
                }
            }
        }

        let parts = best[text.len()].clone()?;
        if parts.len() > 1 {
            Some(parts)
        } else {
            None
        }
    }

    fn is_dictionary_word(&self, word: &str) -> bool {
        self.kdict
            .as_ref()
            .and_then(|dictionary| dictionary.cost(word))
            .is_some()
    }

    fn is_short_segmentation_part(&self, word: &str) -> bool {
        word.chars().count() >= 3 && self.is_dictionary_word(word)
    }
}

fn source_range_for(normalization: &MappedNormalization, range: &Range<usize>) -> Range<usize> {
    let mut normalized_offset = 0;
    let mut source_start = None;
    let mut source_end = 0;
    for unit in &normalization.units {
        let unit_end = normalized_offset + unit.text.len();
        if normalized_offset < range.end && unit_end > range.start {
            source_start.get_or_insert(unit.source_range.start);
            source_end = source_end.max(unit.source_range.end);
        }
        normalized_offset = unit_end;
        if normalized_offset >= range.end {
            break;
        }
    }
    source_start.unwrap_or(0)..source_end
}

#[cfg(test)]
mod tests {
    use super::*;

    const TEST_DICTIONARY: &[u8] = include_bytes!("../../common/khmer_dictionary.kdict");

    fn segmenter(length: SegmentationLength) -> KhmerSegmenter {
        let mut config = SegmenterConfig::default();
        config.segmentation_length = length;
        KhmerSegmenter::from_bytes(TEST_DICTIONARY.to_vec(), config).unwrap()
    }

    fn tokens(segmenter: &KhmerSegmenter, text: &str) -> Vec<String> {
        segmenter
            .segment_detailed(text)
            .unwrap()
            .tokens()
            .map(ToOwned::to_owned)
            .collect()
    }

    #[test]
    fn long_segmentation_preserves_current_long_dictionary_tokens() {
        let segmenter = segmenter(SegmentationLength::Long);

        assert_eq!(tokens(&segmenter, "ភាសាខ្មែរ"), vec!["ភាសា", "ខ្មែរ"]);
        assert_eq!(tokens(&segmenter, "ភាសាផ្លូវការ"), vec!["ភាសា", "ផ្លូវ", "ការ"]);
        assert_eq!(tokens(&segmenter, "ប្រើប្រាស់"), vec!["ប្រើប្រាស់"]);
        assert_eq!(tokens(&segmenter, "ប្រចាំថ្ងៃ"), vec!["ប្រចាំ", "ថ្ងៃ"]);
    }

    #[test]
    fn short_segmentation_refines_long_dictionary_tokens_for_layout() {
        let segmenter = segmenter(SegmentationLength::Short);

        assert_eq!(tokens(&segmenter, "ភាសាខ្មែរ"), vec!["ភាសា", "ខ្មែរ"]);
        assert_eq!(tokens(&segmenter, "ភាសាផ្លូវការ"), vec!["ភាសា", "ផ្លូវ", "ការ"]);
        assert_eq!(tokens(&segmenter, "ប្រើប្រាស់"), vec!["ប្រើ", "ប្រាស់"]);
        assert_eq!(tokens(&segmenter, "ប្រចាំថ្ងៃ"), vec!["ប្រចាំ", "ថ្ងៃ"]);
    }

    #[test]
    fn short_segmentation_does_not_create_single_consonant_fragments() {
        let segmenter = segmenter(SegmentationLength::Short);

        assert_eq!(tokens(&segmenter, "ខ្មែរ"), vec!["ខ្មែរ"]);
        assert_eq!(tokens(&segmenter, "ផ្លូវការ"), vec!["ផ្លូវ", "ការ"]);
        assert!(!tokens(&segmenter, "ភាសាផ្លូវការ")
            .iter()
            .any(|token| token == "រ" || token == "វ"));
    }

    #[test]
    fn spelling_suggestions_recover_reviewed_typos() {
        let segmenter = segmenter(SegmentationLength::Long);
        for (typed, intended) in [
            ("សួរស្តី", "សួស្ដី"),
            ("ជម្រុញ", "ជំរុញ"),
            ("ប្រហេស", "ប្រហែស"),
            ("សសេរ", "សរសេរ"),
            ("រស់ជាតិ", "រសជាតិ"),
            ("សុិ", "ស៊ី"),
            ("សុម", "សូម"),
            ("រយះពេល", "រយៈពេល"),
            ("រយះកម្ពស់", "រយៈកម្ពស់"),
            ("រយះបណ្តោយ", "រយៈបណ្តោយ"),
            ("រយះទទឹង", "រយៈទទឹង"),
            ("អាការះ", "អាការៈ"),
            ("ព្យញ្ជនះ", "ព្យញ្ជនៈ"),
            ("តាមរយះ", "តាមរយៈ"),
            ("សិល្បះ", "សិល្បៈ"),
            ("ទស្សនះ", "ទស្សនៈ"),
        ] {
            let suggestions = segmenter.suggest_spelling(typed, 1.5, 5);
            assert_eq!(
                suggestions.first().map(|item| item.text.as_str()),
                Some(intended)
            );
        }
    }

    #[test]
    fn typing_profile_recovers_reviewed_valid_fragment_typos() {
        let segmenter = segmenter(SegmentationLength::Long);
        for (typed, intended) in [
            (
                "\u{179f}\u{17bd}\u{179a}\u{179f}\u{17d2}\u{178f}\u{17b8}",
                "\u{179f}\u{17bd}\u{179f}\u{17d2}\u{178a}\u{17b8}",
            ),
            (
                "\u{1787}\u{1798}\u{17d2}\u{179a}\u{17bb}\u{1789}",
                "\u{1787}\u{17c6}\u{179a}\u{17bb}\u{1789}",
            ),
            (
                "\u{1794}\u{17d2}\u{179a}\u{17a0}\u{17c1}\u{179f}",
                "\u{1794}\u{17d2}\u{179a}\u{17a0}\u{17c2}\u{179f}",
            ),
            (
                "\u{179f}\u{179f}\u{17c1}\u{179a}",
                "\u{179f}\u{179a}\u{179f}\u{17c1}\u{179a}",
            ),
            (
                "\u{179a}\u{179f}\u{17cb}\u{1787}\u{17b6}\u{178f}\u{17b7}",
                "\u{179a}\u{179f}\u{1787}\u{17b6}\u{178f}\u{17b7}",
            ),
            ("រយះពេល", "រយៈពេល"),
            ("រយះកម្ពស់", "រយៈកម្ពស់"),
            ("រយះបណ្តោយ", "រយៈបណ្តោយ"),
            ("រយះទទឹង", "រយៈទទឹង"),
            ("អាការះ", "អាការៈ"),
            ("ព្យញ្ជនះ", "ព្យញ្ជនៈ"),
            ("តាមរយះ", "តាមរយៈ"),
            ("សិល្បះ", "សិល្បៈ"),
            ("ទស្សនះ", "ទស្សនៈ"),
        ] {
            let diagnostics = segmenter
                .check_text(typed, SpellcheckProfile::Typing)
                .unwrap();
            assert_eq!(diagnostics.len(), 1, "{typed}");
            assert_eq!(diagnostics[0].text, typed);
            assert_eq!(diagnostics[0].suggestions[0].text, intended);
        }
    }

    #[test]
    fn typo_diagnostic_can_cover_fragmented_word() {
        let segmenter = segmenter(SegmentationLength::Long);
        let diagnostics = segmenter.detect_typos("សម្បត្ត", 0.75, 5, true).unwrap();

        assert_eq!(diagnostics[0].text, "សម្បត្ត");
        assert_eq!(diagnostics[0].suggestions[0].text, "សម្បត្តិ");
    }

    #[test]
    fn dictionary_derived_reahmuk_confusion_preserves_valid_collision() {
        let segmenter = segmenter(SegmentationLength::Long);

        assert!(segmenter.is_known_word("ស្រះ"));
        assert!(segmenter.suggest_spelling("ស្រះ", 1.5, 5).is_empty());
        assert!(segmenter
            .check_text("ស្រះ", SpellcheckProfile::Typing)
            .unwrap()
            .is_empty());
    }
}
