use serde::Serialize;
use wasm_bindgen::prelude::*;

use crate::{
    KhmerSegmenter, SegmenterConfig, SpellcheckProfile, SpellingAccuracy, SpellingDiagnostic,
    SpellingSuggestion,
};

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BrowserAnalysis {
    normalized: String,
    segments: Vec<BrowserSegment>,
    diagnostics: Vec<BrowserDiagnostic>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BrowserSegment {
    word: String,
    start: usize,
    end: usize,
    source_start: usize,
    source_end: usize,
    is_unknown: bool,
    spelling_valid: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BrowserDiagnostic {
    text: String,
    start: usize,
    end: usize,
    source_start: usize,
    source_end: usize,
    kind: String,
    confidence: f32,
    suggestions: Vec<BrowserSuggestion>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BrowserSuggestion {
    text: String,
    edit_cost: f32,
}

#[wasm_bindgen]
pub struct WasmKhmerSegmenter {
    inner: KhmerSegmenter,
}

#[wasm_bindgen]
impl WasmKhmerSegmenter {
    #[wasm_bindgen(constructor)]
    pub fn new(dictionary_bytes: &[u8]) -> Result<WasmKhmerSegmenter, JsValue> {
        let inner =
            KhmerSegmenter::from_bytes(dictionary_bytes.to_vec(), SegmenterConfig::default())
                .map_err(|error| JsValue::from_str(&error.to_string()))?;
        Ok(Self { inner })
    }

    pub fn analyze(&self, text: &str, include_valid_fragments: bool) -> Result<JsValue, JsValue> {
        let profile = if include_valid_fragments {
            SpellcheckProfile::HighRecall
        } else {
            SpellcheckProfile::Typing
        };
        self.analysis(text, profile, SpellingAccuracy::Lexical)
    }

    /// Analyze text with the same named profile exposed by Python and Rust.
    #[wasm_bindgen(js_name = analyzeWithProfile)]
    pub fn analyze_with_profile(&self, text: &str, profile: &str) -> Result<JsValue, JsValue> {
        let profile = profile
            .parse::<SpellcheckProfile>()
            .map_err(|error| JsValue::from_str(&error))?;
        self.analysis(text, profile, SpellingAccuracy::Lexical)
    }

    /// Analyze with an independent spelling-accuracy policy.
    #[wasm_bindgen(js_name = analyzeWithOptions)]
    pub fn analyze_with_options(
        &self,
        text: &str,
        profile: &str,
        accuracy: &str,
    ) -> Result<JsValue, JsValue> {
        let profile = profile
            .parse::<SpellcheckProfile>()
            .map_err(|error| JsValue::from_str(&error))?;
        let accuracy = accuracy
            .parse::<SpellingAccuracy>()
            .map_err(|error| JsValue::from_str(&error))?;
        self.analysis(text, profile, accuracy)
    }

    fn analysis(
        &self,
        text: &str,
        profile: SpellcheckProfile,
        accuracy: SpellingAccuracy,
    ) -> Result<JsValue, JsValue> {
        let analysis = self
            .inner
            .analyze_text_with_accuracy(text, profile, accuracy)
            .map_err(|error| JsValue::from_str(&error.to_string()))?;
        let segmentation = &analysis.segmentation;
        let normalized = segmentation.normalized();
        let segments = segmentation
            .ranges()
            .iter()
            .zip(segmentation.mapped_segments())
            .map(|(range, mapped)| {
                let word = normalized[range.clone()].to_owned();
                BrowserSegment {
                    is_unknown: is_lexical_khmer(&word) && !self.inner.is_known_word(&word),
                    spelling_valid: !is_lexical_khmer(&word)
                        || self.inner.is_spelling_valid_with_accuracy(&word, accuracy),
                    word,
                    start: utf16_offset(normalized, range.start),
                    end: utf16_offset(normalized, range.end),
                    source_start: utf16_offset(text, mapped.source_range.start),
                    source_end: utf16_offset(text, mapped.source_range.end),
                }
            })
            .collect();
        let diagnostics = analysis
            .diagnostics
            .into_iter()
            .map(|diagnostic| browser_diagnostic(normalized, text, diagnostic))
            .collect();
        serde_wasm_bindgen::to_value(&BrowserAnalysis {
            normalized: normalized.to_owned(),
            segments,
            diagnostics,
        })
        .map_err(|error| JsValue::from_str(&error.to_string()))
    }

    pub fn suggest(&self, word: &str, max_suggestions: usize) -> Result<JsValue, JsValue> {
        let suggestions: Vec<_> = self
            .inner
            .suggest_spelling(word, 1.5, max_suggestions)
            .into_iter()
            .map(browser_suggestion)
            .collect();
        serde_wasm_bindgen::to_value(&suggestions)
            .map_err(|error| JsValue::from_str(&error.to_string()))
    }

    #[wasm_bindgen(js_name = suggestWithAccuracy)]
    pub fn suggest_with_accuracy(
        &self,
        word: &str,
        max_suggestions: usize,
        accuracy: &str,
    ) -> Result<JsValue, JsValue> {
        let accuracy = accuracy
            .parse::<SpellingAccuracy>()
            .map_err(|error| JsValue::from_str(&error))?;
        let suggestions: Vec<_> = self
            .inner
            .suggest_spelling_with_accuracy(word, 1.5, max_suggestions, accuracy)
            .into_iter()
            .map(browser_suggestion)
            .collect();
        serde_wasm_bindgen::to_value(&suggestions)
            .map_err(|error| JsValue::from_str(&error.to_string()))
    }

    /// Return frequency-ranked dictionary completions for a Khmer prefix.
    pub fn complete(&self, prefix: &str, max_suggestions: usize) -> Result<JsValue, JsValue> {
        let suggestions: Vec<_> = self
            .inner
            .complete_word(prefix, max_suggestions)
            .into_iter()
            .map(browser_suggestion)
            .collect();
        serde_wasm_bindgen::to_value(&suggestions)
            .map_err(|error| JsValue::from_str(&error.to_string()))
    }
}

fn browser_diagnostic(
    normalized: &str,
    source: &str,
    diagnostic: SpellingDiagnostic,
) -> BrowserDiagnostic {
    BrowserDiagnostic {
        text: diagnostic.text,
        start: utf16_offset(normalized, diagnostic.range.start),
        end: utf16_offset(normalized, diagnostic.range.end),
        source_start: utf16_offset(source, diagnostic.source_range.start),
        source_end: utf16_offset(source, diagnostic.source_range.end),
        kind: diagnostic.kind.as_str().to_owned(),
        confidence: diagnostic.confidence,
        suggestions: diagnostic
            .suggestions
            .into_iter()
            .map(browser_suggestion)
            .collect(),
    }
}

fn browser_suggestion(suggestion: SpellingSuggestion) -> BrowserSuggestion {
    BrowserSuggestion {
        text: suggestion.text,
        edit_cost: suggestion.edit_cost,
    }
}

fn utf16_offset(text: &str, byte_offset: usize) -> usize {
    text[..byte_offset].encode_utf16().count()
}

fn is_lexical_khmer(text: &str) -> bool {
    !text.is_empty()
        && text.chars().all(|character| {
            ('\u{1780}'..='\u{17d3}').contains(&character) || character == '\u{17dd}'
        })
}
