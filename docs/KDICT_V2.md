# Unified KDIC v2 Language Packs

KDIC v2 stores segmentation costs, spelling policy, autocomplete eligibility,
and approved exact typo corrections in one binary file. Python, Rust, and WASM
consume the same records.

Each lexical record contains a UTF-8 word, a cost, and independent flags:

| Flag | Meaning |
| --- | --- |
| `SEGMENT` | The form may be selected as one segmentation token. |
| `SPELLCHECK` | The form is an accepted spelling. |
| `AUTOCOMPLETE` | The form may be offered as a completion. |
| `TYPO_SURFACE` | The form is the typed side of an approved correction. |
| `SUPPLEMENTAL` | The form is segmentation evidence, not lexical authority. |

For example, `ដេល` may carry `SEGMENT | TYPO_SURFACE`, while `ដែល` carries
`SEGMENT | SPELLCHECK | AUTOCOMPLETE`. This preserves the typo as one useful
diagnostic span without accepting it as correct spelling.

## COENG DA/TA aliases and spelling accuracy

When a source word contains COENG DA or COENG TA, the compiler writes its
counterpart into the segmentation table with the same cost. Generated aliases
have only `SEGMENT` (and, when applicable, `SUPPLEMENTAL`) metadata: they are
never automatically assigned `SPELLCHECK` or `AUTOCOMPLETE`.

This keeps segmentation tolerant of the two visual encodings without changing
the curated word shown to users. Spellcheck integrations choose their policy
at runtime: `lexical` (default) accepts only the exact curated spelling, while
`visual` also accepts its COENG DA/TA counterpart. Completion remains
canonical in both modes.

For example, if a pack stores `ស្ដាប់`, segmentation recognizes both `ស្ដាប់`
and `ស្តាប់`; lexical spellcheck accepts only the former, while visual
spellcheck accepts both.

## Create a single editable source

```json
{
  "version": 1,
  "entries": [
    {
      "word": "ដែល",
      "uses": ["segmentation", "spelling", "autocomplete"],
      "frequency": 100
    },
    {
      "word": "ដេល",
      "uses": ["segmentation", "supplemental", "typo"],
      "correction": "ដែល"
    }
  ]
}
```

Compile that one source file into the one-file runtime pack:

```bash
khmer-segment data compile custom.klex.json --output custom.kdict
```

The standalone Rust CLI provides the same compiler:

```bash
khmer_segmenter data compile custom.klex.json --output custom.kdict
```

To keep the official pack unchanged while adding application vocabulary, compile
the KLEX file as an overlay on a KDIC v2 base:

```bash
khmer-segment data compile local.klex.json \
  --base official.kdict --output application.kdict

khmer_segmenter data compile local.klex.json \
  --base official.kdict --output application.kdict
```

The output is a standalone pack; applications load only `application.kdict`.
Base costs and corrections are preserved. Overlay uses are additive, and an
overlay correction for the same typo replaces the base correction. An overlay
cannot remove a base word or revoke one of its uses; rebuild the base source for
that policy change. Python and Rust produce byte-identical packs from the same
base and KLEX input.

A copyable source is available at [`examples/custom.klex.json`](../examples/custom.klex.json).

## Compile the repository's existing data

The maintainer workflow can still combine the existing reviewed source files:

```bash
python scripts/build_dictionary_kdict.py \
  --dict dictionary_words.txt \
  --freq word_frequencies.json \
  --supplemental segmentation_only_words.txt \
  --spellcheck accepted_spellings.txt \
  --typo-corrections typo_corrections.tsv \
  --output custom.kdict
```

Only rows whose `status` is `approved` are compiled from the correction TSV.
The source files remain convenient for review; applications deploy only the
resulting `.kdict` file.

## Load the pack

Python:

```python
from khmer_segmenter import KhmerSegmenter

segmenter = KhmerSegmenter.from_kdict("custom.kdict")
```

Rust:

```rust
use khmer_segmenter::{KhmerSegmenter, SegmenterConfig};

let segmenter = KhmerSegmenter::from_path(
    "custom.kdict",
    SegmenterConfig::default(),
)?;

let analysis = segmenter.analyze_text(
    "...",
    khmer_segmenter::SpellcheckProfile::Typing,
)?;
// Segments and diagnostics include normalized and original-source ranges.

let visual_valid = segmenter.is_spelling_valid_with_accuracy(
    "ស្តាប់",
    khmer_segmenter::SpellingAccuracy::Visual,
);
```

CLI:

```bash
khmer-segment data compile custom.klex.json --output custom.kdict
khmer-segment --kdict custom.kdict diagnose "ដេល"
khmer_segmenter data compile custom.klex.json --output custom.kdict
khmer_segmenter --dictionary custom.kdict "ដេល"
```

## Compatibility

The v2 file begins with the original KDIC hash table, so existing segmentation
lookup remains compact. Updated readers use the appended `KDX2` metadata.
Rust continues to read KDIC v1 with its bundled spelling fallback. Python's
`from_kdict()` intentionally requires v2 because v1 does not contain enough
information to distinguish segmentation vocabulary from accepted spelling.

Both readers reject truncated tables, invalid extension offsets, malformed
string references, and inconsistent entry counts before exposing the pack to a
runtime.
