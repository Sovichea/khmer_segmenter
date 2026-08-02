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
