//! Deterministic Khmer spelling suggestions backed by the compiled KDIC.

use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};
use std::ops::Range;
use std::str::FromStr;

use crate::kdict::KDict;
use crate::khmer_segmenter::Segmentation;

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

#[derive(Debug, Clone, PartialEq)]
pub struct SpellingDiagnostic {
    pub text: String,
    pub range: Range<usize>,
    pub kind: String,
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
        token_count - 0.5 * self.diagnostic.suggestions[0].edit_cost - 0.25
    }
}

pub struct TypoDetector {
    words: HashSet<String>,
    entries: Vec<(String, f32)>,
    exact_skeleton: HashMap<String, Vec<usize>>,
    deletion_skeleton: HashMap<String, Vec<usize>>,
    reviewed_typos: HashMap<String, String>,
    max_exact_typo_chars: usize,
}

impl TypoDetector {
    pub fn from_kdict(dictionary: &KDict) -> Self {
        // KDIC is the broad segmentation lexicon and may contain supplemental
        // words or known typo surfaces. Spelling and completion intentionally
        // use only the separately curated spelling vocabulary.
        let mut entries: Vec<_> = SPELLCHECK_WORDS
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
        if !entries.iter().any(|(word, _)| word == "ឲ្យ") {
            if let Some((_, cost)) = entries.iter().find(|(word, _)| word == "ឱ្យ") {
                entries.push(("ឲ្យ".to_owned(), *cost + 0.001));
            }
        }
        let words: HashSet<String> = entries.iter().map(|(word, _)| word.clone()).collect();
        let mut reviewed_typos: HashMap<String, String> = TYPO_CORRECTIONS_TSV
            .lines()
            .skip(1)
            .filter_map(|line| {
                let columns: Vec<_> = line.split('\t').collect();
                (columns.len() >= 4 && columns[1] == "approved")
                    .then(|| (columns[2].to_owned(), columns[3].to_owned()))
            })
            // Approved corrections are authoritative and may be multiword
            // expressions rather than single spellcheck headwords.
            .collect();
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
        for (typed, candidates) in generated_candidates {
            if candidates.len() == 1 {
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
        Self {
            words,
            entries,
            exact_skeleton,
            deletion_skeleton,
            reviewed_typos,
            max_exact_typo_chars,
        }
    }

    pub fn is_word(&self, word: &str) -> bool {
        self.words.contains(word)
    }

    /// Return frequent dictionary words that begin with `prefix`.
    pub fn complete_prefix(&self, prefix: &str, limit: usize) -> Vec<SpellingSuggestion> {
        if prefix.is_empty() || limit == 0 {
            return Vec::new();
        }

        let mut matches: Vec<_> = self
            .entries
            .iter()
            .filter(|(word, _)| word.starts_with(prefix))
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

    pub fn detect(
        &self,
        segmentation: &Segmentation,
        max_edit_cost: f32,
        max_suggestions: usize,
        context_tokens: usize,
        include_valid_fragments: bool,
    ) -> Vec<SpellingDiagnostic> {
        let ranges = segmentation.ranges();
        let text = segmentation.normalized();
        let tokens: Vec<&str> = segmentation.tokens().collect();
        let mut suspicious = Vec::new();

        for (index, token) in tokens.iter().enumerate() {
            if is_lexical_khmer(token) && (!self.words.contains(*token) || include_valid_fragments)
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
                if candidate_text.chars().count() > self.max_exact_typo_chars {
                    break;
                }
                let Some(intended) = self.reviewed_typos.get(candidate_text) else {
                    continue;
                };
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
                        (start_token..=end_token).any(|index| !self.words.contains(tokens[index]));
                    if !contains_unknown && suggestions[0].edit_cost > 0.75 {
                        // High-recall inspection of valid fragments must not
                        // erase a legitimate adjacent base-word merely because
                        // a shorter compound exists in the dictionary.
                        continue;
                    }
                    let confidence = confidence(&suggestions, max_edit_cost);
                    proposals.push(Proposal {
                        diagnostic: SpellingDiagnostic {
                            text: candidate_text.to_owned(),
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
    if is_dependent_vowel(character) {
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

fn diagnostic_kind(source: &str, target: &str) -> String {
    let source_chars: Vec<char> = source.chars().collect();
    let target_chars: Vec<char> = target.chars().collect();
    if target_chars.len() == source_chars.len() + 1
        && target_chars
            .iter()
            .any(|character| is_dependent_vowel(*character))
    {
        "missing_dependent_vowel".to_owned()
    } else {
        "probable_misspelling".to_owned()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn weights_informal_khmer_sign_sequences() {
        assert!((weighted_edit_cost("សុិ", "ស៊ី") - 0.25).abs() < f32::EPSILON);
        assert!((weighted_edit_cost("សុម", "សូម") - 0.25).abs() < f32::EPSILON);
        assert!((weighted_edit_cost("ជម្រុញ", "ជំរុញ") - 0.35).abs() < f32::EPSILON);
        assert!((weighted_edit_cost("សសេរ", "សរសេរ") - 0.25).abs() < f32::EPSILON);
    }
}
