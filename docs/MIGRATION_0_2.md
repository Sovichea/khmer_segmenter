# Migrating from 0.1.1 to 0.2

Version 0.2 replaces the mixed 0.1 runtime lexicon and corpus-derived weights
with a strict RAC 2022 model. Segmentation output can therefore change even
when the Python call is unchanged. The new model has separate segmentation and
spellcheck lexicons, RAC-only frequency evidence, much broader lexical POS
coverage, accepted lexical forms ending in `ៗ`, and a provenance manifest.

## COENG DA/TA alias policy

Version 0.2 separates segmentation tolerance from spelling authority. COENG DA/TA
variants are available to segmentation so either visual form can remain one
token. Spellcheck stays exact by default; applications can opt into
`accuracy="visual"` when they want to accept the two forms as visually
equivalent.

## Recommended adoption

1. Install `0.2.0` in a test environment.
2. Compare application samples and the curated development benchmark with
   `0.1.1`; treat khPOS and Khmer ALT only as compatibility diagnostics.
3. Review category regressions larger than two percentage points.
4. Update integrations that consume token dictionaries to accept the new
   `spelling_valid` field.
5. Use `lexical` spelling accuracy for formal dictionaries and published text,
   or `visual` accuracy for an editor that should tolerate COENG DA/TA display
   variants.
6. Promote 0.2 only after the 300-sentence human-curated benchmark is complete
   and the frozen test gate passes.

Applications that require unchanged behavior can pin:

```text
khmer-viterbi-segmenter==0.1.1
```

Alternatively, pass an existing 0.1 data directory through `data_dir=` or
`--data-dir`. If that directory has no `khmer_spellcheck_words.txt`, spelling
checks use its segmentation dictionary for backward compatibility.

The experimental hyphenation API and KHYP data were removed. Khmer text does
not need Latin-style internal-word hyphenation. Layout engines should use
`word_break_opportunities()` to obtain legal source offsets, or
`insert_word_breaks()` to insert U+200B between adjacent known Khmer words.
Python offsets use code points, Rust offsets use UTF-8 bytes, and WASM offsets
use UTF-16 code units.

The Rust port can consume the rebuilt KDIC in native and WebAssembly
applications and provides the same analysis, spelling, completion, and
word-breaking behavior. Rust no longer permits a dictionary-less segmenter:
replace `KhmerSegmenter::new(Some(path), config)` with `from_path(path, config)`,
use `from_bytes(bytes, config)` for embedded or WASM data, or use
`from_kdict(dictionary, config)` when the caller already owns a loaded `KDict`.
The CLI accepts `--dictionary` and `--kdict` before or after its structured
commands and exits with an error when it cannot load lexical data. The C port
remains segmentation-only.
