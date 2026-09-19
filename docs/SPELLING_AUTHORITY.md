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
form valid and offers it in completion; it does not change segmentation costs
or the canonical spelling shown by correction suggestions.

## Relationship to lexicon modes

[Lexicon modes](LEXICON_LAYERS.md) decide which **packs** load (`strict` vs
`inclusive`). Spelling authority decides whether reviewed community **spellings**
are accepted. The two are independent: an inclusive pack can still be used with
`official` spelling authority, and vice versa.

## Native ports

Rust, WASM, and C read KDIC flags. Community spellings become accepted in the
native ports only when they are compiled into a pack with the `spelling` and
`autocomplete` uses (for example, an inclusive community pack). Until that pack
exists, the toggle is Python-only.
