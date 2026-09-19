# Spelling Authority

Khmer has long-lived variants that a single authority may not list. `ឱ្យ` is the
RAC 2022 spelling, while `អោយ` and `ឲ្យ` are widely used in real text. Rather
than force one answer, the segmenter selects a **spelling authority**.

| Authority | Accepted spellings |
| --- | --- |
| `official` (default) | RAC 2022 and reviewed official layers only |
| `community` | the above plus reviewed community spellings |

Community spellings never enter segmentation or completion unless the community
authority is selected. They are reviewed and tracked, not taken from raw corpus
frequency.

## Python

```python
from khmer_segmenter import KhmerSegmenter, SpellingAuthority

official = KhmerSegmenter()
official.is_spelling_valid("ឲ្យ")  # False

community = KhmerSegmenter(spelling_authority=SpellingAuthority.COMMUNITY)
community.is_spelling_valid("អោយ")  # True
community.is_spelling_valid("ឲ្យ")  # True
```

The value is also accepted as a string (`spelling_authority="community"`) and on
the classmethod constructors (`from_data_dir`, `from_kdict`,
`from_kdict_layers`).

## CLI

```bash
khmer-segment --spelling-authority community spellcheck "អោយ ឲ្យ ឱ្យ"
khmer-segment --spelling-authority community segment "ខ្ញុំឲ្យអ្នក"
```

## Data and review

- `khmer_dictionary_community_spellings.txt` lists the accepted community
  spellings.
- `khmer_dictionary_community_spellings_review.tsv` records the review status,
  source, category, and rationale for each entry.

It is built from reviewed sources and tagged per entry:

- reviewed legacy variants (`អោយ`, `ឲ្យ`),
- Chuon Nath 1967 headwords and SBBIC wordlist entries accepted as legacy
  words, tagged with their source so they can be verified or dropped later.

The list is compiled from the review tables in `build/` with
`python scripts/compile_practical_policy.py`. A community spelling makes the
form valid, keeps it as a single segmentation token, and offers it in
completion; it does not change existing segmentation costs or the canonical
spelling shown by correction suggestions.

## Relationship to lexicon layers

[Lexicon layers](LEXICON_LAYERS.md) decide which **packs** participate in
segmentation; every supplied pack always loads, with community evidence last.
Spelling authority decides whether reviewed community **spellings** are
accepted. The two are independent: community packs improve segmentation, and
community spellings become valid only under community authority.

## Native ports

Rust and WebAssembly expose the same selection through
`SegmenterConfig::spelling_authority` and
`WasmKhmerSegmenter.newWithAuthority`, with `--spelling-authority` on the native
CLI. The reviewed community spellings are embedded in the Rust language pack, so
under community authority they participate in segmentation, spelling validity,
and completion exactly as in Python. The C port reads KDIC flags and does not yet
expose the runtime toggle.
