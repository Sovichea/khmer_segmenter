//! Deterministic Khmer spelling suggestions backed by the compiled KDIC.

use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};
use std::ops::Range;
use std::str::FromStr;
use std::sync::OnceLock;

use crate::kdict::coeng_da_ta_variants;
use crate::kdict::{KDict, WORD_AUTOCOMPLETE, WORD_SPELLCHECK};
use crate::khmer_segmenter::Segmentation;
use crate::normalization::khmer_normalize;

const COENG: char = '\u{17d2}';
const NIKAHIT: char = '\u{17c6}';
const RO: char = '\u{179a}';
const CA: char = '\u{1785}';
const CO: char = '\u{1787}';
const TYPO_CORRECTIONS_TSV: &str = include_str!("../data/khmer_typo_corrections.tsv");
const SPELLCHECK_WORDS: &str = include_str!("../data/khmer_spellcheck_words.txt");
const REAHMUK: char = '\u{17c7}'; // ះ
const YUUKALEAPINTU: char = '\u{17c8}'; // ៈ
const COMMON_VISUAL_CONFUSIONS: &[(char, char)] = &[
    (REAHMUK, YUUKALEAPINTU),
    (YUUKALEAPINTU, REAHMUK),
    ('\u{17bc}', '\u{17bd}'), // ូ -> ួ
    ('\u{17bd}', '\u{17bc}'), // ួ -> ូ
    ('\u{17cf}', '\u{17cd}'), // ៏ -> ៍
    ('\u{17cd}', '\u{17cf}'), // ៍ -> ៏
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SpellcheckProfile {
    Typing,
    Document,
    HighRecall,
}

/// Exact curated spelling, or a UI-oriented COENG DA/TA equivalence policy.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SpellingAccuracy {
    Lexical,
    Visual,
}

impl SpellingAccuracy {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Lexical => "lexical",
            Self::Visual => "visual",
        }
    }
}

impl FromStr for SpellingAccuracy {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "lexical" => Ok(Self::Lexical),
            "visual" => Ok(Self::Visual),
            _ => Err(format!(
                "unknown spelling accuracy {value:?}; expected lexical or visual"
            )),
        }
    }
}

/// Which reviewed sources may make a spelling valid.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum SpellingAuthority {
    #[default]
    Official,
    Community,
}

impl SpellingAuthority {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Official => "official",
            Self::Community => "community",
        }
    }
}

impl FromStr for SpellingAuthority {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "official" => Ok(Self::Official),
            "community" => Ok(Self::Community),
            _ => Err(format!(
                "unknown spelling authority {value:?}; expected official or community"
            )),
        }
    }
}

const COMMUNITY_SPELLINGS: &str = include_str!("../data/khmer_dictionary_community_spellings.txt");
const TYPO_PHRASE_EXCLUSIONS: &str = include_str!("../data/khmer_typo_phrase_exclusions.txt");

/// log10(4); a correction is well attested when its KDIC cost is at least this
/// much below the floor cost, i.e. its frequency is at least 20.
const OOV_CORRECTION_COST: f32 = 0.602_06;

/// Cost penalty applied to reviewed community spellings absent from KDIC, so
/// frequent dictionary words still rank ahead of them.
const COMMUNITY_SPELLING_COST_PENALTY: f32 = 1.0;

/// Reviewed community spellings, normalized for lookup.
pub fn community_spellings() -> Vec<String> {
    COMMUNITY_SPELLINGS
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(khmer_normalize)
        .filter(|word| !word.is_empty())
        .collect()
}

impl SpellcheckProfile {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Typing => "typing",
            Self::Document => "document",
            Self::HighRecall => "high-recall",
        }
    }

    pub const fn config(self) -> SpellcheckConfig {
        match self {
            Self::Typing => SpellcheckConfig::new(0.75, 3, 1, false, 0.80),
            Self::Document => SpellcheckConfig::new(1.00, 5, 1, false, 0.75),
            Self::HighRecall => SpellcheckConfig::new(1.50, 5, 1, true, 0.0),
        }
    }
}

impl FromStr for SpellcheckProfile {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "typing" => Ok(Self::Typing),
            "document" => Ok(Self::Document),
            "high-recall" | "high_recall" => Ok(Self::HighRecall),
            _ => Err(format!(
                "unknown spellcheck profile {value:?}; expected typing, document, or high-recall"
            )),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SpellcheckConfig {
    pub max_edit_cost: f32,
    pub max_suggestions: usize,
    pub context_tokens: usize,
    pub include_valid_fragments: bool,
    pub min_confidence: f32,
}

impl SpellcheckConfig {
    pub const fn new(
        max_edit_cost: f32,
        max_suggestions: usize,
        context_tokens: usize,
        include_valid_fragments: bool,
        min_confidence: f32,
    ) -> Self {
        Self {
            max_edit_cost,
            max_suggestions,
            context_tokens,
            include_valid_fragments,
            min_confidence,
        }
    }
}

#[cfg(test)]
mod profile_tests {
    use super::*;

    #[test]
    fn named_profiles_match_python_defaults() {
        assert_eq!(
            SpellcheckProfile::Typing.config(),
            SpellcheckConfig::new(0.75, 3, 1, false, 0.80)
        );
        assert_eq!(
            SpellcheckProfile::Document.config(),
            SpellcheckConfig::new(1.00, 5, 1, false, 0.75)
        );
        assert_eq!(
            SpellcheckProfile::HighRecall.config(),
            SpellcheckConfig::new(1.50, 5, 1, true, 0.0)
        );
        assert_eq!(
            "high-recall".parse::<SpellcheckProfile>(),
            Ok(SpellcheckProfile::HighRecall)
        );
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct SpellingSuggestion {
    pub text: String,
    pub edit_cost: f32,
    pub lexical_cost: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DiagnosticKind {
    MissingDependentVowel,
    ExtraCharacter,
    ProbableMisspelling,
    UnknownWord,
}

impl DiagnosticKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::MissingDependentVowel => "missing_dependent_vowel",
            Self::ExtraCharacter => "extra_character",
            Self::ProbableMisspelling => "probable_misspelling",
            Self::UnknownWord => "unknown_word",
        }
    }
}

impl std::fmt::Display for DiagnosticKind {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct SpellingDiagnostic {
    pub text: String,
    /// Byte range in normalized text.
    pub range: Range<usize>,
    /// Byte range in the original input. Populated by the segmenter analysis API.
    pub source_range: Range<usize>,
    pub kind: DiagnosticKind,
    pub confidence: f32,
    pub suggestions: Vec<SpellingSuggestion>,
}

#[derive(Debug)]
struct Proposal {
    diagnostic: SpellingDiagnostic,
    start_token: usize,
    end_token: usize,
}

impl Proposal {
    fn score(&self) -> f32 {
        let token_count = (self.end_token - self.start_token + 1) as f32;
        match self.diagnostic.suggestions.first() {
            Some(suggestion) => token_count - 0.5 * suggestion.edit_cost - 0.25,
            None => token_count,
        }
    }
}

pub struct TypoDetector {
    words: HashSet<String>,
    visual_words: HashSet<String>,
    autocomplete_words: HashSet<String>,
    entries: Vec<(String, f32)>,
    exact_skeleton: HashMap<String, Vec<usize>>,
    deletion_skeleton: HashMap<String, Vec<usize>>,
    reviewed_typos: HashMap<String, String>,
    approved_typos: HashSet<String>,
    default_cost: f32,
    max_exact_typo_chars: usize,
    composition_parts: OnceLock<CompositionParts>,
}

struct CompositionParts {
    words: HashSet<String>,
    costs: HashMap<String, f32>,
    max_len: usize,
}

/// Count Khmer orthographic clusters (base characters that are not subscripts).
fn orthographic_cluster_count(text: &str) -> usize {
    let mut count = 0;
    let mut previous = '\0';
    for character in text.chars() {
        if ('\u{1780}'..='\u{17b3}').contains(&character) && previous != COENG {
            count += 1;
        }
        previous = character;
    }
    count
}

impl TypoDetector {
    pub fn from_kdict(dictionary: &KDict) -> Self {
        Self::from_kdict_with_authority(dictionary, SpellingAuthority::Official)
    }

    pub fn from_kdict_with_authority(dictionary: &KDict, authority: SpellingAuthority) -> Self {
        // KDIC is the broad segmentation lexicon and may contain supplemental
        // words or known typo surfaces. Spelling and completion intentionally
        // use only the separately curated spelling vocabulary.
        let (mut entries, mut autocomplete_words, mut reviewed_typos): (
            Vec<(String, f32)>,
            HashSet<String>,
            HashMap<String, String>,
        ) = if dictionary.has_unified_metadata() {
            let lexical_entries = dictionary.lexical_entries();
            (
                lexical_entries
                    .iter()
                    .filter(|entry| entry.flags & WORD_SPELLCHECK != 0)
                    .map(|entry| (entry.word.clone(), entry.cost))
                    .collect(),
                lexical_entries
                    .iter()
                    .filter(|entry| entry.flags & WORD_AUTOCOMPLETE != 0)
                    .map(|entry| entry.word.clone())
                    .collect(),
                dictionary.typo_corrections().into_iter().collect(),
            )
        } else {
            let entries: Vec<_> = SPELLCHECK_WORDS
                .lines()
                .map(str::trim)
                .filter(|word| is_lexical_khmer(word))
                .map(|word| {
                    (
                        word.to_owned(),
                        dictionary
                            .cost(word)
                            .unwrap_or_else(|| dictionary.default_cost()),
                    )
                })
                .collect();
            let autocomplete_words = entries.iter().map(|(word, _)| word.clone()).collect();
            let reviewed_typos = TYPO_CORRECTIONS_TSV
                .lines()
                .skip(1)
                .filter_map(|line| {
                    let columns: Vec<_> = line.split('\t').collect();
                    (columns.len() >= 4 && columns[1] == "approved")
                        .then(|| (columns[2].to_owned(), columns[3].to_owned()))
                })
                .collect();
            (entries, autocomplete_words, reviewed_typos)
        };
        if !entries.iter().any(|(word, _)| word == "ឲ្យ") {
            if let Some((_, cost)) = entries.iter().find(|(word, _)| word == "ឱ្យ") {
                entries.push(("ឲ្យ".to_owned(), *cost + 0.001));
                autocomplete_words.insert("ឲ្យ".to_owned());
            }
        }
        if authority == SpellingAuthority::Community {
            let community_cost = dictionary.default_cost() + COMMUNITY_SPELLING_COST_PENALTY;
            let mut existing: HashSet<String> =
                entries.iter().map(|(word, _)| word.clone()).collect();
            for word in community_spellings() {
                if existing.insert(word.clone()) {
                    entries.push((word.clone(), community_cost));
                }
                autocomplete_words.insert(word);
            }
        }
        let words: HashSet<String> = entries.iter().map(|(word, _)| word.clone()).collect();
        // Some Khmer signs are difficult to distinguish on small screens.
        // Derive one-character aliases, excluding valid words and aliases that
        // could refer to more than one dictionary entry. Reviewed pairs remain
        // authoritative when they overlap a generated rule.
        let mut generated_candidates: HashMap<String, HashSet<String>> = HashMap::new();
        let common_ending_cost_limit = dictionary.default_cost() - 0.30;
        for (word, lexical_cost) in &entries {
            let characters: Vec<char> = word.chars().collect();
            for (index, character) in characters.iter().enumerate() {
                for (typed_character, intended_character) in COMMON_VISUAL_CONFUSIONS {
                    if character != intended_character {
                        continue;
                    }
                    let mut alias = characters.clone();
                    alias[index] = *typed_character;
                    let alias: String = alias.into_iter().collect();
                    if !words.contains(&alias) {
                        generated_candidates
                            .entry(alias)
                            .or_default()
                            .insert(word.clone());
                    }
                }
                if index > 0 && characters[index - 1] == COENG && matches!(*character, CA | CO) {
                    let mut alias = characters.clone();
                    alias[index] = if *character == CA { CO } else { CA };
                    let alias: String = alias.into_iter().collect();
                    if !words.contains(&alias) {
                        generated_candidates
                            .entry(alias)
                            .or_default()
                            .insert(word.clone());
                    }
                }
            }
            let ro_positions: Vec<usize> = characters
                .iter()
                .enumerate()
                .filter_map(|(index, character)| {
                    (*character == RO && (index == 0 || characters[index - 1] != COENG))
                        .then_some(index)
                })
                .collect();
            for (position, first) in ro_positions.iter().enumerate() {
                let alias: String = characters
                    .iter()
                    .enumerate()
                    .filter_map(|(index, character)| (index != *first).then_some(*character))
                    .collect();
                if !alias.is_empty() && !words.contains(&alias) {
                    generated_candidates
                        .entry(alias)
                        .or_default()
                        .insert(word.clone());
                }
                for second in ro_positions.iter().skip(position + 1) {
                    let alias: String = characters
                        .iter()
                        .enumerate()
                        .filter_map(|(index, character)| {
                            (index != *first && index != *second).then_some(*character)
                        })
                        .collect();
                    if !alias.is_empty() && !words.contains(&alias) {
                        generated_candidates
                            .entry(alias)
                            .or_default()
                            .insert(word.clone());
                    }
                }
            }
            if *lexical_cost <= common_ending_cost_limit {
                for (index, character) in characters.iter().enumerate() {
                    if index > 0
                        && is_base(*character)
                        && characters[index - 1] != COENG
                        && characters[index - 1] != RO
                    {
                        let alias: String = characters[..index]
                            .iter()
                            .copied()
                            .chain(std::iter::once(RO))
                            .chain(characters[index..].iter().copied())
                            .collect();
                        if !words.contains(&alias) {
                            generated_candidates
                                .entry(alias)
                                .or_default()
                                .insert(word.clone());
                        }
                    }
                }
            }
            if characters
                .last()
                .is_some_and(|character| is_dependent_vowel(*character))
                && *lexical_cost <= common_ending_cost_limit
            {
                let alias = format!("{word}{RO}");
                if !words.contains(&alias) {
                    generated_candidates
                        .entry(alias)
                        .or_default()
                        .insert(word.clone());
                }
            }
        }
        // Reviewed phrase collisions such as ត្រីសួរ ("fish asked") resemble a
        // rare compound (ត្រីសូរ) but are really common phrases. They are
        // excluded from the generated aliases; approved pairs are unaffected.
        let excluded: HashSet<&str> = TYPO_PHRASE_EXCLUSIONS
            .lines()
            .map(str::trim)
            .filter(|line| !line.is_empty())
            .collect();
        let approved_typos: HashSet<String> = reviewed_typos.keys().cloned().collect();
        let default_cost = dictionary.default_cost();
        for (typed, candidates) in generated_candidates {
            if candidates.len() == 1 && !excluded.contains(typed.as_str()) {
                reviewed_typos
                    .entry(typed)
                    .or_insert_with(|| candidates.into_iter().next().unwrap());
            }
        }
        let mut exact_skeleton: HashMap<String, Vec<usize>> = HashMap::new();
        let mut deletion_skeleton: HashMap<String, Vec<usize>> = HashMap::new();

        for (index, (word, _)) in entries.iter().enumerate() {
            let skeleton = base_skeleton(word);
            exact_skeleton
                .entry(skeleton.clone())
                .or_default()
                .push(index);
            let characters: Vec<char> = skeleton.chars().collect();
            for removed in 0..characters.len() {
                let signature: String = characters
                    .iter()
                    .enumerate()
                    .filter_map(|(position, character)| (position != removed).then_some(*character))
                    .collect();
                deletion_skeleton.entry(signature).or_default().push(index);
            }
        }

        let max_exact_typo_chars = reviewed_typos
            .keys()
            .map(|word| word.chars().count())
            .max()
            .unwrap_or(0);
        let mut visual_words = words.clone();
        for word in &words {
            visual_words.extend(coeng_da_ta_variants(word));
        }
        Self {
            words,
            visual_words,
            autocomplete_words,
            entries,
            exact_skeleton,
            deletion_skeleton,
            reviewed_typos,
            approved_typos,
            default_cost,
            max_exact_typo_chars,
            composition_parts: OnceLock::new(),
        }
    }

    /// Return internal byte offsets where a retained word may wrap.
    ///
    /// The whole word must split into at least two accepted spellings, each
    /// with two or more orthographic clusters, so a bare letter or a
    /// single-cluster syllable is never isolated. The pack stores costs rather
    /// than raw frequencies, so no lexicality weighting is applied here.
    pub(crate) fn composition_break_offsets(&self, text: &str) -> Vec<usize> {
        let parts = self.composition_parts.get_or_init(|| {
            let mut words = HashSet::new();
            let mut costs = HashMap::new();
            let mut max_len = 0;
            for (word, cost) in &self.entries {
                if orthographic_cluster_count(word) >= 2 {
                    max_len = max_len.max(word.chars().count());
                    words.insert(word.clone());
                    costs.insert(word.clone(), *cost);
                }
            }
            CompositionParts {
                words,
                costs,
                max_len,
            }
        });
        let characters: Vec<char> = text.chars().collect();
        let length = characters.len();
        if parts.max_len < 2 || length < 4 {
            return Vec::new();
        }
        let byte_index: Vec<usize> = text
            .char_indices()
            .map(|(index, _)| index)
            .chain(std::iter::once(text.len()))
            .collect();
        // Minimum-piece decomposition of every suffix, tracking the first split.
        let mut min_pieces = vec![usize::MAX; length + 1];
        let mut next_split: Vec<Option<usize>> = vec![None; length + 1];
        min_pieces[length] = 0;
        for start in (0..length).rev() {
            let limit = (start + parts.max_len).min(length);
            for end in (start + 1)..=limit {
                if min_pieces[end] == usize::MAX {
                    continue;
                }
                let piece = &text[byte_index[start]..byte_index[end]];
                if parts.words.contains(piece) {
                    let candidate = min_pieces[end] + 1;
                    if candidate < min_pieces[start] {
                        min_pieces[start] = candidate;
                        next_split[start] = Some(end);
                    }
                }
            }
        }
        // Force at least one split so the whole word cannot match itself.
        let mut first_end = None;
        let mut best_total = usize::MAX;
        for end in 1..length {
            if min_pieces[end] == usize::MAX {
                continue;
            }
            let piece = &text[byte_index[0]..byte_index[end]];
            if parts.words.contains(piece) {
                let total = min_pieces[end] + 1;
                if total < best_total {
                    best_total = total;
                    first_end = Some(end);
                }
            }
        }
        let Some(first) = first_end else {
            return Vec::new();
        };
        let mut boundaries = Vec::new();
        let mut pieces: Vec<&str> = Vec::new();
        let mut start = 0usize;
        let mut end = first;
        loop {
            pieces.push(&text[byte_index[start]..byte_index[end]]);
            if end >= length {
                break;
            }
            boundaries.push(byte_index[end]);
            let Some(next) = next_split[end] else {
                break;
            };
            start = end;
            end = next;
        }
        if pieces.len() < 2 {
            return Vec::new();
        }
        // Map the Python "whole word is not dominant" rule onto KDIC costs: a
        // lower cost means a higher frequency, so the whole word must not be
        // cheaper than its most frequent part.
        if let Some(whole_cost) = parts.costs.get(text) {
            let mut min_part_cost = f32::INFINITY;
            for piece in &pieces {
                if let Some(part_cost) = parts.costs.get(*piece) {
                    if *part_cost < min_part_cost {
                        min_part_cost = *part_cost;
                    }
                }
            }
            if min_part_cost.is_finite() && *whole_cost < min_part_cost {
                return Vec::new();
            }
        }
        boundaries
    }

    pub fn is_word(&self, word: &str) -> bool {
        self.words.contains(word)
    }

    pub fn is_word_with_accuracy(&self, word: &str, accuracy: SpellingAccuracy) -> bool {
        match accuracy {
            SpellingAccuracy::Lexical => self.words.contains(word),
            SpellingAccuracy::Visual => self.visual_words.contains(word),
        }
    }

    /// Return frequent dictionary words that begin with `prefix`.
    pub fn complete_prefix(&self, prefix: &str, limit: usize) -> Vec<SpellingSuggestion> {
        if prefix.is_empty() || limit == 0 {
            return Vec::new();
        }

        let mut matches: Vec<_> = self
            .entries
            .iter()
            .filter(|(word, _)| word.starts_with(prefix) && self.autocomplete_words.contains(word))
            .map(|(word, lexical_cost)| SpellingSuggestion {
                text: word.clone(),
                edit_cost: 0.0,
                lexical_cost: *lexical_cost,
            })
            .collect();
        matches.sort_by(|left, right| {
            (right.text == prefix)
                .cmp(&(left.text == prefix))
                .then_with(|| left.lexical_cost.total_cmp(&right.lexical_cost))
                .then_with(|| left.text.chars().count().cmp(&right.text.chars().count()))
                .then_with(|| left.text.cmp(&right.text))
        });
        matches.truncate(limit);
        matches
    }

    pub fn suggest_word(
        &self,
        text: &str,
        max_edit_cost: f32,
        limit: usize,
    ) -> Vec<SpellingSuggestion> {
        if text.is_empty()
            || (self.words.contains(text) && !self.reviewed_typos.contains_key(text))
            || limit == 0
        {
            return Vec::new();
        }

        let mut ranked = Vec::new();
        for index in self.candidate_indices(text, max_edit_cost) {
            let (word, lexical_cost) = &self.entries[index];
            if word == text || word.chars().count().abs_diff(text.chars().count()) > 2 {
                continue;
            }
            if word.chars().count() == 1 && text.chars().count() > 1 {
                continue;
            }
            let edit_cost = weighted_edit_cost(text, word);
            if edit_cost <= max_edit_cost {
                ranked.push(SpellingSuggestion {
                    text: word.clone(),
                    edit_cost,
                    lexical_cost: *lexical_cost,
                });
            }
        }
        ranked.sort_by(|left, right| {
            left.edit_cost
                .total_cmp(&right.edit_cost)
                .then_with(|| left.lexical_cost.total_cmp(&right.lexical_cost))
                .then_with(|| left.text.cmp(&right.text))
        });
        if let Some(intended) = self.reviewed_typos.get(text) {
            ranked.retain(|suggestion| suggestion.text != *intended);
            ranked.insert(
                0,
                SpellingSuggestion {
                    text: intended.clone(),
                    edit_cost: weighted_edit_cost(text, intended),
                    lexical_cost: self
                        .entries
                        .iter()
                        .find_map(|(word, cost)| (word == intended).then_some(*cost))
                        .unwrap_or(f32::MAX),
                },
            );
        }
        ranked.truncate(limit);
        ranked
    }

    pub fn suggest_word_with_accuracy(
        &self,
        text: &str,
        max_edit_cost: f32,
        limit: usize,
        accuracy: SpellingAccuracy,
    ) -> Vec<SpellingSuggestion> {
        if self.is_word_with_accuracy(text, accuracy) {
            return Vec::new();
        }
        self.suggest_word(text, max_edit_cost, limit)
    }

    pub fn detect(
        &self,
        segmentation: &Segmentation,
        max_edit_cost: f32,
        max_suggestions: usize,
        context_tokens: usize,
        include_valid_fragments: bool,
        accuracy: SpellingAccuracy,
        min_confidence: f32,
    ) -> Vec<SpellingDiagnostic> {
        let ranges = segmentation.ranges();
        let text = segmentation.normalized();
        let tokens: Vec<&str> = segmentation.tokens().collect();
        let mut suspicious = Vec::new();

        for (index, token) in tokens.iter().enumerate() {
            if is_lexical_khmer(token)
                && (!self.is_word_with_accuracy(token, accuracy) || include_valid_fragments)
            {
                suspicious.push(index);
            }
        }

        let mut proposals = Vec::new();
        let mut seen = HashSet::new();

        // Exact aliases recover errors made entirely of valid fragments. Scan
        // only token-aligned text up to the longest alias, which supports long
        // dictionary-derived forms without enabling general fuzzy matching.
        for start_token in 0..tokens.len() {
            for end_token in start_token..tokens.len() {
                if !(start_token..=end_token).all(|index| is_lexical_khmer(tokens[index])) {
                    break;
                }
                if !(start_token..end_token)
                    .all(|index| ranges[index].end == ranges[index + 1].start)
                {
                    break;
                }
                let range = ranges[start_token].start..ranges[end_token].end;
                let candidate_text = &text[range.clone()];
                if self.is_word_with_accuracy(candidate_text, accuracy) {
                    continue;
                }
                if candidate_text.chars().count() > self.max_exact_typo_chars {
                    break;
                }
                let Some(intended) = self.reviewed_typos.get(candidate_text) else {
                    continue;
                };
                if !self.approved_typos.contains(candidate_text)
                    && !self.is_word(tokens[start_token])
                {
                    let mut run_start = start_token;
                    while run_start > 0 && is_lexical_khmer(tokens[run_start - 1]) {
                        run_start -= 1;
                    }
                    let mut run_end = end_token;
                    while run_end + 1 < tokens.len() && is_lexical_khmer(tokens[run_end + 1]) {
                        run_end += 1;
                    }
                    if start_token > run_start || end_token < run_end {
                        // A generated alias over an out-of-vocabulary fragment
                        // inside a longer unbroken run is an unknown word.
                        continue;
                    }
                }
                let mut suggestions = vec![SpellingSuggestion {
                    text: intended.clone(),
                    edit_cost: weighted_edit_cost(candidate_text, intended),
                    lexical_cost: self
                        .entries
                        .iter()
                        .find_map(|(word, cost)| (word == intended).then_some(*cost))
                        .unwrap_or(f32::MAX),
                }];
                suggestions.extend(
                    self.suggest_word(candidate_text, 1.5, max_suggestions.max(5))
                        .into_iter()
                        .filter(|suggestion| suggestion.text != *intended),
                );
                suggestions.truncate(max_suggestions);
                seen.insert((range.start, range.end));
                proposals.push(Proposal {
                    diagnostic: SpellingDiagnostic {
                        text: candidate_text.to_owned(),
                        source_range: range.clone(),
                        range,
                        kind: diagnostic_kind(candidate_text, intended),
                        confidence: 0.99,
                        suggestions,
                    },
                    start_token,
                    end_token,
                });
            }
        }

        for center in suspicious {
            let first = center.saturating_sub(context_tokens);
            let last = center
                .saturating_add(context_tokens)
                .min(tokens.len().saturating_sub(1));
            for start_token in first..=center {
                for end_token in center..=last {
                    if end_token - start_token + 1 > context_tokens.saturating_mul(2) + 1 {
                        continue;
                    }
                    if !(start_token..=end_token).all(|index| is_lexical_khmer(tokens[index])) {
                        continue;
                    }
                    if !(start_token..end_token)
                        .all(|index| ranges[index].end == ranges[index + 1].start)
                    {
                        continue;
                    }
                    let range = ranges[start_token].start..ranges[end_token].end;
                    // Maximal lexical run containing the candidate span.
                    let mut run_start = start_token;
                    while run_start > 0 && is_lexical_khmer(tokens[run_start - 1]) {
                        run_start -= 1;
                    }
                    let mut run_end = end_token;
                    while run_end + 1 < tokens.len() && is_lexical_khmer(tokens[run_end + 1]) {
                        run_end += 1;
                    }
                    let embedded = start_token > run_start || end_token < run_end;
                    if embedded && !self.is_word(tokens[start_token]) {
                        // The span opens with an out-of-vocabulary fragment
                        // inside a longer unbroken run: report the whole
                        // unknown run as an unknown word, without a correction.
                        let mut last = start_token;
                        while last + 1 < tokens.len()
                            && is_lexical_khmer(tokens[last + 1])
                            && !self.is_word(tokens[last + 1])
                        {
                            last += 1;
                        }
                        let oov_range = ranges[start_token].start..ranges[last].end;
                        if seen.insert((oov_range.start, oov_range.end)) {
                            proposals.push(Proposal {
                                diagnostic: SpellingDiagnostic {
                                    text: text[oov_range.clone()].to_owned(),
                                    source_range: oov_range.clone(),
                                    range: oov_range,
                                    kind: DiagnosticKind::UnknownWord,
                                    confidence: 0.0,
                                    suggestions: Vec::new(),
                                },
                                start_token,
                                end_token: last,
                            });
                        }
                        continue;
                    }
                    if !seen.insert((range.start, range.end)) {
                        continue;
                    }
                    let candidate_text = &text[range.clone()];
                    let suggestions =
                        self.suggest_word(candidate_text, max_edit_cost, max_suggestions);
                    if suggestions.is_empty() {
                        continue;
                    }
                    let contains_unknown =
                        (start_token..=end_token).any(|index| !self.is_word(tokens[index]));
                    if embedded
                        && contains_unknown
                        && suggestions[0].lexical_cost > self.default_cost - OOV_CORRECTION_COST
                    {
                        // The span contains an out-of-vocabulary fragment and
                        // the best correction is not a well-attested word.
                        let mut first_unknown = start_token;
                        while first_unknown <= end_token && self.is_word(tokens[first_unknown]) {
                            first_unknown += 1;
                        }
                        if first_unknown > end_token {
                            continue;
                        }
                        let mut last = first_unknown;
                        while last + 1 < tokens.len()
                            && is_lexical_khmer(tokens[last + 1])
                            && !self.is_word(tokens[last + 1])
                        {
                            last += 1;
                        }
                        let oov_range = ranges[first_unknown].start..ranges[last].end;
                        if seen.insert((oov_range.start, oov_range.end)) {
                            proposals.push(Proposal {
                                diagnostic: SpellingDiagnostic {
                                    text: text[oov_range.clone()].to_owned(),
                                    source_range: oov_range.clone(),
                                    range: oov_range,
                                    kind: DiagnosticKind::UnknownWord,
                                    confidence: 0.0,
                                    suggestions: Vec::new(),
                                },
                                start_token: first_unknown,
                                end_token: last,
                            });
                        }
                        continue;
                    }
                    if !contains_unknown && suggestions[0].edit_cost > 0.75 {
                        // High-recall inspection of valid fragments must not
                        // erase a legitimate adjacent base-word merely because
                        // a shorter compound exists in the dictionary.
                        continue;
                    }
                    let confidence = confidence(&suggestions, max_edit_cost);
                    if confidence < min_confidence {
                        continue;
                    }
                    proposals.push(Proposal {
                        diagnostic: SpellingDiagnostic {
                            text: candidate_text.to_owned(),
                            source_range: range.clone(),
                            range,
                            kind: diagnostic_kind(candidate_text, &suggestions[0].text),
                            confidence,
                            suggestions,
                        },
                        start_token,
                        end_token,
                    });
                }
            }
        }

        proposals.sort_by(|left, right| {
            right
                .score()
                .partial_cmp(&left.score())
                .unwrap_or(Ordering::Equal)
                .then_with(|| {
                    left.diagnostic
                        .range
                        .start
                        .cmp(&right.diagnostic.range.start)
                })
        });
        let mut selected: Vec<Proposal> = Vec::new();
        for proposal in proposals {
            if selected.iter().any(|current| {
                proposal.start_token <= current.end_token
                    && current.start_token <= proposal.end_token
            }) {
                continue;
            }
            selected.push(proposal);
        }
        selected.sort_by_key(|proposal| proposal.diagnostic.range.start);
        selected
            .into_iter()
            .map(|proposal| proposal.diagnostic)
            .collect()
    }

    fn candidate_indices(&self, text: &str, max_edit_cost: f32) -> HashSet<usize> {
        let skeleton = base_skeleton(text);
        let mut candidates = HashSet::new();
        if let Some(indices) = self.exact_skeleton.get(&skeleton) {
            candidates.extend(indices.iter().copied());
        }

        for rewritten in [
            text.replace("\u{1798}\u{17d2}", "\u{17c6}"),
            text.replace("\u{17c6}", "\u{1798}\u{17d2}"),
        ] {
            if rewritten != text {
                if let Some(indices) = self.exact_skeleton.get(&base_skeleton(&rewritten)) {
                    candidates.extend(indices.iter().copied());
                }
            }
        }

        let skeleton_chars: Vec<char> = skeleton.chars().collect();
        for index in 0..skeleton_chars.len().saturating_sub(1) {
            if skeleton_chars[index] == skeleton_chars[index + 1] {
                let mut expanded = skeleton_chars.clone();
                expanded.insert(index + 1, RO);
                let expanded: String = expanded.into_iter().collect();
                if let Some(indices) = self.exact_skeleton.get(&expanded) {
                    candidates.extend(indices.iter().copied());
                }
            }
        }

        if max_edit_cost >= 1.0 {
            if let Some(indices) = self.deletion_skeleton.get(&skeleton) {
                candidates.extend(indices.iter().copied());
            }
            for removed in 0..skeleton_chars.len() {
                let signature: String = skeleton_chars
                    .iter()
                    .enumerate()
                    .filter_map(|(position, character)| (position != removed).then_some(*character))
                    .collect();
                if let Some(indices) = self.exact_skeleton.get(&signature) {
                    candidates.extend(indices.iter().copied());
                }
                if !signature.is_empty() {
                    if let Some(indices) = self.deletion_skeleton.get(&signature) {
                        candidates.extend(indices.iter().copied());
                    }
                }
            }
        }
        candidates
    }
}

fn is_base(character: char) -> bool {
    ('\u{1780}'..='\u{17b3}').contains(&character)
}

fn is_dependent_vowel(character: char) -> bool {
    ('\u{17b6}'..='\u{17c5}').contains(&character)
}

fn is_register_or_sign(character: char) -> bool {
    ('\u{17c6}'..='\u{17d1}').contains(&character) || matches!(character, '\u{17d3}' | '\u{17dd}')
}

fn is_lexical_khmer(text: &str) -> bool {
    !text.is_empty()
        && !text.contains('\u{17d7}')
        && text.chars().all(|character| {
            ('\u{1780}'..='\u{17d3}').contains(&character) || character == '\u{17dd}'
        })
}

fn base_skeleton(text: &str) -> String {
    let mut skeleton = String::new();
    let mut previous = None;
    for character in text.chars() {
        if is_base(character) {
            if previous == Some(COENG) && matches!(character, '\u{178a}' | '\u{178f}') {
                skeleton.push('\u{178f}');
            } else {
                skeleton.push(character);
            }
        }
        previous = Some(character);
    }
    skeleton
}

fn edit_weight(character: char) -> f32 {
    if character == RO {
        0.45
    } else if is_dependent_vowel(character) {
        0.25
    } else if is_register_or_sign(character) {
        0.35
    } else if character == COENG {
        0.60
    } else {
        1.0
    }
}

fn substitution_weight(
    source: char,
    target: char,
    source_previous: Option<char>,
    target_previous: Option<char>,
) -> f32 {
    if source == target {
        0.0
    } else if source == '\u{17bb}' && target == '\u{17bc}' {
        0.25
    } else if is_dependent_vowel(source) && is_dependent_vowel(target) {
        0.35
    } else if is_register_or_sign(source) && is_register_or_sign(target) {
        0.40
    } else if source_previous == Some(COENG)
        && target_previous == Some(COENG)
        && ((source == '\u{178a}' && target == '\u{178f}')
            || (source == '\u{178f}' && target == '\u{178a}'))
    {
        // RAC entries contain both encodings; treat them as spelling aliases
        // so lexical frequency can prefer the canonical dictionary form.
        0.0
    } else {
        1.0_f32.min(edit_weight(source) + edit_weight(target))
    }
}

pub fn weighted_edit_cost(source: &str, target: &str) -> f32 {
    let source: Vec<char> = source.chars().collect();
    let target: Vec<char> = target.chars().collect();
    let mut table = vec![vec![f32::INFINITY; target.len() + 1]; source.len() + 1];
    table[0][0] = 0.0;
    for index in 1..=source.len() {
        table[index][0] = table[index - 1][0] + edit_weight(source[index - 1]);
    }
    for index in 1..=target.len() {
        table[0][index] = table[0][index - 1] + edit_weight(target[index - 1]);
    }

    for i in 1..=source.len() {
        for j in 1..=target.len() {
            let mut best = table[i - 1][j - 1]
                + substitution_weight(
                    source[i - 1],
                    target[j - 1],
                    i.checked_sub(2).map(|index| source[index]),
                    j.checked_sub(2).map(|index| target[index]),
                );
            best = best.min(table[i - 1][j] + edit_weight(source[i - 1]));
            best = best.min(table[i][j - 1] + edit_weight(target[j - 1]));

            if i >= 2 && source[i - 2..i] == ['\u{1798}', COENG] && target[j - 1] == NIKAHIT {
                best = best.min(table[i - 2][j - 1] + 0.35);
            }
            if i >= 1
                && j >= 2
                && source[i - 1] == NIKAHIT
                && target[j - 2..j] == ['\u{1798}', COENG]
            {
                best = best.min(table[i - 1][j - 2] + 0.35);
            }
            if i >= 2
                && j >= 2
                && source[i - 2..i] == ['\u{17bb}', '\u{17b7}']
                && target[j - 2..j] == ['\u{17ca}', '\u{17b8}']
            {
                best = best.min(table[i - 2][j - 2] + 0.25);
            }
            if i >= 2
                && j >= 3
                && source[i - 2] == source[i - 1]
                && target[j - 3] == source[i - 2]
                && target[j - 2] == RO
                && target[j - 1] == source[i - 1]
            {
                best = best.min(table[i - 2][j - 3] + 0.25);
            }
            table[i][j] = best;
        }
    }
    table[source.len()][target.len()]
}

fn confidence(suggestions: &[SpellingSuggestion], max_edit_cost: f32) -> f32 {
    let best = suggestions[0].edit_cost;
    let mut value = 1.0 - 0.45 * (best / max_edit_cost.max(0.001));
    if suggestions.len() > 1 {
        value += 0.15 * (suggestions[1].edit_cost - best).min(1.0);
    }
    value.clamp(0.0, 1.0)
}

fn diagnostic_kind(source: &str, target: &str) -> DiagnosticKind {
    let source_chars: Vec<char> = source.chars().collect();
    let target_chars: Vec<char> = target.chars().collect();
    let inserted = single_inserted_character(&source_chars, &target_chars);
    if inserted.is_some_and(is_dependent_vowel) {
        DiagnosticKind::MissingDependentVowel
    } else if single_inserted_character(&target_chars, &source_chars).is_some() {
        DiagnosticKind::ExtraCharacter
    } else {
        DiagnosticKind::ProbableMisspelling
    }
}

fn single_inserted_character(shorter: &[char], longer: &[char]) -> Option<char> {
    if longer.len() != shorter.len() + 1 {
        return None;
    }
    for index in 0..longer.len() {
        if shorter[..index.min(shorter.len())] == longer[..index]
            && shorter[index.min(shorter.len())..] == longer[index + 1..]
        {
            return Some(longer[index]);
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn diagnostic_kinds_require_a_single_matching_edit() {
        assert_eq!(
            diagnostic_kind("\u{1780}", "\u{1780}\u{17b7}"),
            DiagnosticKind::MissingDependentVowel
        );
        assert_eq!(diagnostic_kind("ab", "a"), DiagnosticKind::ExtraCharacter);
        assert_eq!(
            diagnostic_kind("abc", "ad"),
            DiagnosticKind::ProbableMisspelling
        );
    }

    #[test]
    fn weights_informal_khmer_sign_sequences() {
        assert!((weighted_edit_cost("សុិ", "ស៊ី") - 0.25).abs() < f32::EPSILON);
        assert!((weighted_edit_cost("សុម", "សូម") - 0.25).abs() < f32::EPSILON);
        assert!((weighted_edit_cost("ជម្រុញ", "ជំរុញ") - 0.35).abs() < f32::EPSILON);
        assert!((weighted_edit_cost("សសេរ", "សរសេរ") - 0.25).abs() < f32::EPSILON);
        assert!((weighted_edit_cost("សសើ", "សរសើរ") - 0.70).abs() < f32::EPSILON);
        assert!((weighted_edit_cost("ច្រអ", "ច្រអរ") - 0.45).abs() < f32::EPSILON);
    }
}
