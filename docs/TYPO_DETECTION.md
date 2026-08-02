# Typo Detection

`KhmerSegmenter.detect_typos()` adds editor-oriented spelling diagnostics
without changing the stable Viterbi segmentation path.

## Why diagnostics use separate spans

A misspelled word may be segmented into valid fragments surrounding an unknown
token. Token-level spelling flags would underline only the unknown fragment.
The detector examines a small window around each invalid Khmer token and may
return one diagnostic covering the complete probable word.

For example, `សម្បត្ត` is internally segmented as `ស | ម្បត្ត`, but the
diagnostic covers `[0, 7)` and suggests `សម្បត្តិ`.

## Python API

```python
from khmer_segmenter import KhmerSegmenter, SpellcheckProfile

segmenter = KhmerSegmenter()
diagnostics = segmenter.detect_typos(
    "សម្បត្ត",
    max_edit_cost=0.75,
    max_suggestions=3,
    context_tokens=1,
)

# Preferred integration API for a live editor or word processor.
diagnostics = segmenter.check_text(text, profile=SpellcheckProfile.TYPING)

# Explicit lookup: do not segment the input word first.
suggestions = segmenter.suggest_spelling("សសេរ")

for diagnostic in diagnostics:
    print(diagnostic.to_dict())
```

Each `SpellingDiagnostic` contains:

- `text`, `start`, and `end`: the complete suspected input span;
- `kind`: a useful classification such as `missing_dependent_vowel`;
- `confidence`: a deterministic ranking indicator, not a calibrated
  probability;
- `suggestions`: ranked RAC spellcheck words;
- `edits`: absolute normalized-text insertion, deletion, or replacement
  operations suitable for an editor quick fix.

When normalization is enabled, offsets refer to the normalized text, matching
`analyze()`. An editor that needs offsets into the original unnormalized buffer
should normalize before calling and retain its own source mapping, or call with
`normalize=False` after normalization.

## Integration profiles

Python, native Rust, Rust/WASM, and both CLIs use the same profile names and
defaults:

| Profile | Edit cost | Suggestions | Valid fragments | Confidence | Intended use |
| --- | ---: | ---: | --- | ---: | --- |
| `typing` | 0.75 | 3 | no | 0.80 | live editor diagnostics |
| `document` | 1.00 | 5 | no | 0.75 | explicit full-document review |
| `high-recall` | 1.50 | 5 | yes | 0.00 | corpus research and dictionary curation |

Use `typing` by default in Typsastra and word processors. Run `document` only
when the user requests a full check. `high-recall` can recover errors that split
entirely into valid words, but it can also flag legitimate adjacent words:

```python
diagnostics = segmenter.detect_typos(
    "រស់ជាតិ",
    profile="high-recall",
)
```

This mode can recover `រស់ជាតិ` → `រសជាតិ` and `សសេរ` → `សរសេរ`, but it can
also flag legitimate adjacent words. It is best suited to interactive review,
not unattended replacement. `suggest_spelling()` is the preferred API when
the caller already knows the complete word span.

## Candidate generation and ranking

### Reviewed correction pairs

Exact common corrections are maintained in
`src/khmer_segmenter/dictionary_data/khmer_typo_corrections.tsv`. A row affects
Python, Rust, and WASM only when its status is `approved`; `pending` rows are a
review queue and `rejected` rows preserve decisions without enabling them.

After reviewing changes, synchronize and validate the Rust copy:

```bash
python scripts/sync_typo_corrections.py
python scripts/sync_typo_corrections.py --check
```

Keep acceptance counts and user feedback statistics outside this file. They
are evidence for review, not segmentation frequency and not automatic proof
that a correction is valid.

Common small-screen visual confusions are derived from the active dictionary
for `ះ`/`ៈ`, `ូ`/`ួ`, `៏`/`៍`, and the subscript forms `្ច`/`្ជ`. The visual
rules operate in both directions and change one character at a time. A separate
directional rule detects an extra final `រ` after a dependent vowel, limited to
frequent intended words. Generated forms receive exact-alias confidence only
when they are neither valid dictionary words nor ambiguous between two intended
words. Explicit approved correction pairs take precedence.

The detector runs after normal segmentation and considers small windows around
suspicious tokens. It does not scan every possible substring. Candidate
retrieval uses Khmer base-character skeleton indexes, then ranks the reduced
candidate set with code-point edits weighted as follows:

| Operation | Cost |
| --- | ---: |
| Insert/delete dependent vowel | 0.25 |
| Insert/delete register shifter or sign | 0.35 |
| Insert/delete COENG | 0.60 |
| Base-character substitution | 1.00 |

Additional narrow rules cover RAC subscript DA/TA equivalence, the common
`ម + COENG`/NIKAHIT confusion, an omitted medial `រ` between repeated
consonants, the close `ុ`/`ូ` vowel pair, and the malformed informal
`ុិ`/`៊ី` sign sequence. Overlapping candidates are selected jointly so a
coherent full-word correction can beat several cheaper fragment-level
corrections.

Unicode normalization handles equivalent combining-mark order before matching.
Frequency breaks ties between candidates at the same edit cost. These rules
were checked against the sourced diagnostic observations described in
[`benchmarks/typos/`](../benchmarks/typos/README.md); that small set is not a
general accuracy benchmark.

## CLI

```bash
khmer-segment diagnose "សម្បត្ត" --format json
khmer-segment diagnose --profile document --input input.txt --output diagnostics.json
khmer-segment diagnose "រស់ជាតិ" --profile high-recall --format json
```

Use `--max-edit-cost` to change the accepted weighted distance and
`--max-suggestions` to limit candidates. Higher edit thresholds increase recall
but can produce unsuitable suggestions for names and uncommon vocabulary. The
conservative default is `0.75`; a threshold of `1.0` also enables missing,
extra, and substituted base-character candidates.

## Current scope

The implementation supplies whole-span diagnostics, weighted fuzzy lookup,
ranked candidates, confidence, and edit scripts. It deliberately leaves the
original segmentation unchanged. Typo-aware Viterbi arcs and local rescoring
remain future work after a curated typo benchmark is available.
