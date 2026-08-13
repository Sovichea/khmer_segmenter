# Migrating from 0.1.1 to 0.2

Version 0.2 replaces the mixed 0.1 runtime lexicon and corpus-derived weights
with a strict RAC 2022 model. Segmentation output can therefore change even
when the Python call is unchanged. The new model has separate segmentation and
spellcheck lexicons, RAC-only frequency evidence, much broader lexical POS
coverage, accepted lexical forms ending in `ៗ`, and a provenance manifest.

## COENG DA/TA alias policy

RC3 separates segmentation tolerance from spelling authority. COENG DA/TA
variants are available to segmentation so either visual form can remain one
token. Spellcheck stays exact by default; applications can opt into
`accuracy="visual"` when they want to accept the two forms as visually
equivalent.

## Recommended adoption

1. Install `0.2.0rc3` in a test environment.
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

Hyphenation is unchanged, remains experimental, and is not part of the RAC
segmentation model claim. The Rust port can now consume the rebuilt KDIC in
native and WebAssembly applications and includes experimental typo suggestions.
The C port remains on its current release-validation path until the Python
release candidate is accepted.
