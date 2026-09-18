# Safe Word Breaks (ZWSP)

`KhmerSegmenter.word_break_opportunities` and `insert_word_breaks` return legal
zero-width-space (U+200B) positions for Khmer text layout. Breaks are offered
between adjacent known words and, optionally, inside a long known word that is
a composition of smaller accepted words. Offsets always refer to the original
source string.

```python
offsets = segmenter.word_break_opportunities("របាយការណ៍នេះ")
text_with_breaks = segmenter.insert_word_breaks("របាយការណ៍នេះ")
```

The composition axis is controlled by `allow_composition_breaks`, which defaults
to `True`:

```python
segmenter.insert_word_breaks("របាយការណ៍")  # "របាយ\u200bការណ៍"
segmenter.insert_word_breaks("របាយការណ៍", allow_composition_breaks=False)  # unchanged
```

## Break rules

An internal break inside a known word is emitted only when **all** of the
following hold:

1. The word decomposes into **≥2 parts**, each an accepted spelling with
   **≥2 orthographic clusters**.
2. The whole word is **not dominant**: `freq(whole) <= max(freq(part))`. This
   keeps lexicalized units whole.

A between-word break is suppressed when either neighbour is a **single Khmer
consonant** code point (U+1780–U+17A2), so a bare letter is never isolated.

### Why the dominance test matters

Pure cluster counting cannot separate compositions from lexicalized units:

| Word | Parts | Frequency (whole / parts) | Result |
|---|---|---|---|
| `សាលា` | `សា` + `លា` | 152 / 169, 158 | blocked — parts are 1 cluster |
| `កំសាក` | `កំ` + `សាក` | 4 / 0, 38 | blocked — part is 1 cluster |
| `សរសេរ` | `សរ` + `សេរ` | 553 / 20, 1 | blocked — whole is dominant |
| `ត្រូវការ` | `ត្រូវ` + `ការ` | 169 / 3286, 8906 | allowed |
| `ខូចខាត` | `ខូច` + `ខាត` | 35 / 368, 81 | allowed |
| `របាយការណ៍` | `របាយ` + `ការណ៍` | 14 / 14, 253 | allowed |

## Behaviour

```
Bad breaks must NOT appear
  កសាង            -> កសាង                (no break)
  សាលា            -> សាលា                (no break)
  កំសាក           -> កំសាក               (no break)
  សរសេរ           -> សរសេរ               (no break)
  ការកសាង         -> ការ|កសាង            (only between words)

Acceptable composition breaks
  ត្រូវការ         -> ត្រូវ|ការ
  ខូចខាត          -> ខូច|ខាត
  របាយការណ៍       -> របាយ|ការណ៍
  គោលការណ៍        -> គោល|ការណ៍
  ជាក់លាក់        -> ជាក់|លាក់
  ប្រៀបធៀប       -> ប្រៀប|ធៀប

Unchanged normal text
  ខ្មែរស្រឡាញ់ខ្មែរ -> ខ្មែរ|ស្រឡាញ់|ខ្មែរ  (5, 12)
  ខ្ញុំសរសេរសំបុត្រ -> ខ្ញុំ|សរសេរ|សំបុត្រ (5, 10)
```

### Edge cases

| Case | Input | Output |
|---|---|---|
| `normalize=False` | `របាយការណ៍` | `របាយ\|ការណ៍` |
| existing ZWSP | `របាយ\u200bការណ៍` | `របាយ\|ការណ៍` (no duplicate) |
| ZWNJ | `របាយ\u200cការណ៍` | break before ZWNJ, ZWNJ preserved |
| mixed Latin | `របាយabcការណ៍` | no break (unknown span) |
| `disable_post_processing=True` | `របាយការណ៍` | `របាយ\|ការណ៍` |
| idempotent | `របាយការណ៍ត្រូវការ` | re-running yields identical output |

## CLI

```bash
khmer-segment word-breaks "របាយការណ៍នេះ"
khmer-segment word-breaks "របាយការណ៍នេះ" --format json
```

```
$ khmer-segment word-breaks "របាយការណ៍នេះបានបង្ហាញថាត្រូវការខូចខាត"
របាយ​ការណ៍​នេះ​បាន​បង្ហាញ​ថា​ត្រូវ​ការ​ខូច​ខាត
```

## Verification

Regression suite: `110` tests passed before the composition axis was added and
`115` passed after (`python -m pytest -q`). Five tests cover the new behaviour
in `tests/test_word_breaks.py`. Lint is unchanged (17 `ruff` findings on both
`HEAD` and the change).

Measured on 300 lines of `dataset/community/.../all_text.txt`:

| Metric | Before | After |
|---|---|---|
| Between-word breaks | 5,440 | 5,409 |
| Breaks adjacent to a single consonant | 29 | **0** |
| Composition (internal) breaks | 0 | 606 |
| Total breaks | 5,440 | 6,015 |

The 29 unsafe between-word breaks are removed and 606 internal breaks are added;
no unsafe break remains.

## Porting status

The Rust/WASM port implements token-level word breaks at
`port/rust/src/khmer_segmenter.rs`. It does not carry raw RAC frequencies (a
KDIC pack stores derived costs), so the dominance rule cannot be ported 1:1.
Porting options are to map dominance onto KDIC costs, add a frequency
side-table to the pack, or apply the cluster rule only in Rust.
