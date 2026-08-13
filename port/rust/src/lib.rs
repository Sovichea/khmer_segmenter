pub mod kdict;
pub mod khmer_segmenter;
pub mod normalization;
pub mod rule_engine;
pub mod spelling;
pub mod utils;

pub use khmer_segmenter::{
    KhmerSegmenter, MappedSegment, Segmentation, SegmentationError, SegmentationLength,
    SegmenterConfig, TextAnalysis,
};
pub use normalization::{khmer_normalize_mapped, MappedNormalization, NormalizedUnit};
pub use spelling::{
    DiagnosticKind, SpellcheckConfig, SpellcheckProfile, SpellingAccuracy, SpellingDiagnostic, SpellingSuggestion,
    TypoDetector,
};

#[cfg(feature = "wasm")]
mod wasm;
