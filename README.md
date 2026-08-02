# Khmer Segmenter

A deterministic, dictionary-based Khmer word segmenter for NLP preprocessing,
search, formal documents, and embedded applications. It combines Khmer Unicode
normalization, frequency-weighted Viterbi decoding, linguistic rules, and
unknown-word recovery without a runtime machine-learning model.

[Documentation](docs/README.md) ·
[Data preparation](docs/EMBEDDED_DICTIONARY.md) ·
[C port](port/c/README.md) ·
[Rust port](port/rust/README.md) ·
[Live demo](https://sovichea.github.io/khmer_segment_webui_demo/)

> [!IMPORTANT]
> The package includes an attributed Khmer dictionary and derived runtime data
> for noncommercial use. Project code is MIT licensed; the bundled linguistic
> data has separate terms in [DATA_LICENSE.md](DATA_LICENSE.md).

> [!WARNING]
> **Hyphenation is experimental.** Its dictionary and rules are still being
> refined, and many words do not yet receive correct internal break positions.
> Do not rely on hyphenation output for production typography without review.

## Features

- Deterministic segmentation for the same code and local data
- Khmer Unicode normalization
- Frequency-weighted dictionary decisions
- Layered curated and supplemental segmentation lexicons
- RAC-curated spelling correction and autocomplete vocabulary
- Word spelling checks through Python and the CLI
- Whole-span typo diagnostics with Khmer-aware ranked suggestions
- Unknown-span preservation
- Typed token metadata with offsets and lexical POS candidates
- Experimental Khmer hyphenation
- Python API and `khmer-segment` CLI
- Shared KDIC/KHYP formats for C and Rust applications
- Rust/WASM segmentation and experimental spelling APIs for browser applications

This is a lexical segmenter, not a semantic parser or contextual POS tagger.
`pos_candidates` are possibilities found in optional local lexical data.

## Install for development

Python 3.10 or newer is required.

```bash
git clone https://github.com/Sovichea/khmer_segmenter.git
cd khmer_segmenter
python -m venv .venv
```

Activate the environment and install the src-layout package:

```bash
# Linux/macOS
source .venv/bin/activate
python -m pip install -e .
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install -e .
```

After its first release, the distribution will install with:

```bash
pip install khmer-viterbi-segmenter
```

The import package remains `khmer_segmenter`.
The bundled runtime data works immediately; no separate download is required.

## Dictionary source and optional replacement

The original dictionary is published by Seanghay Hay (`seanghay`) on Hugging
Face and was extracted from the Khmer Dictionary 2022 of the National Council
of Khmer Language, Royal Academy of Cambodia:

<https://huggingface.co/datasets/seanghay/khmer-dictionary-44k>

The dataset may be redistributed for noncommercial use with attribution. The
bundled normalized lexicons, RAC-only frequencies, lexical POS candidates, and
experimental hyphenation pairs retain that credit and restriction. See
[the linguistic data notice](DATA_LICENSE.md).

For an exact model rebuild, download the structured RAC CSV directly from the
original publisher:

```bash
mkdir -p dataset
curl -L \
  "https://huggingface.co/datasets/seanghay/khmer-dictionary-44k/resolve/525c0171894465cba920a9181387a032c11610d3/RAC-Khmer-Dict-2022.csv?download=true" \
  -o dataset/RAC-Khmer-Dict-2022.csv
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force dataset | Out-Null
Invoke-WebRequest `
  -Uri "https://huggingface.co/datasets/seanghay/khmer-dictionary-44k/resolve/525c0171894465cba920a9181387a032c11610d3/RAC-Khmer-Dict-2022.csv?download=true" `
  -OutFile "dataset/RAC-Khmer-Dict-2022.csv"
```

Rebuild the authoritative RAC runtime artifacts deterministically:

```bash
python scripts/rebuild_rac_model.py \
  --rac-csv dataset/RAC-Khmer-Dict-2022.csv \
  --output-dir build/rac
```

`khmer-segment data prepare --rac-tsv PATH` remains available for simple custom
0.1-style dictionary overrides; it does not reproduce the strict RAC model.

The installed layered model additionally contains conservative supplemental
segmentation chunks. Supplemental entries can preserve names, newer vocabulary,
and known typo spans as single tokens, but they never become valid spellings or
autocomplete candidates. Curated words keep their normal costs; supplemental
words receive a cost penalty. Recreate that layer from a reviewed legacy list:

```bash
python scripts/prepare_supplemental_lexicon.py path/to/legacy_words.txt \
  --audit build/supplemental_audit.tsv
python scripts/build_dictionary_kdict.py
```

The audit records every curated match, retained chunk, and rejected fragment.

```bash
python scripts/validate_findings.py \
  --rac-csv dataset/RAC-Khmer-Dict-2022.csv
```

The Python resolver checks these locations in order:

1. `data_dir=` or CLI `--data-dir`
2. `KHMER_SEGMENTER_DATA_DIR`
3. The user data directory for the operating system
4. The data bundled with the installed package
5. `khmer_segmenter/dictionary_data/` in a development checkout

Check the resolved files:

```bash
khmer-segment data status
khmer-segment data sources
khmer-segment data prepare --rac-tsv dataset/rac_dictionary_2022_pairs.tsv
```

See [Prepare Dictionaries for Python, C, and Rust](docs/EMBEDDED_DICTIONARY.md)
for frequency generation and KDIC/KHYP compilation.

## Python API

```python
from khmer_segmenter import KhmerSegmenter

segmenter = KhmerSegmenter()

tokens = segmenter.segment("ខ្ញុំស្រឡាញ់ប្រទេសកម្ពុជា")
print(tokens)
```

To use a replacement dictionary, set `KHMER_SEGMENTER_DATA_DIR` or pass
`data_dir=` explicitly:

```python
segmenter = KhmerSegmenter(data_dir="/path/to/replacement-data")
```

Typed analysis results include normalized offsets and optional lexical data:

```python
for token in segmenter.analyze("ខ្ញុំសរសេរឯកសារ"):
    print(token.text, token.start, token.end, token.known)
    print(token.frequency, token.pos_candidates)
    print(token.spelling_valid)
```

Check whole words independently of segmentation:

```python
segmenter.is_spelling_valid("នីមួយៗ")
segmenter.check_spelling(["នីមួយៗ", "ពាក្យមិនស្គាល់"])
```

Detect probable typos in continuous text:

```python
diagnostics = segmenter.detect_typos("សម្បត្ត")

for diagnostic in diagnostics:
    print(diagnostic.text, diagnostic.start, diagnostic.end)
    for suggestion in diagnostic.suggestions:
        print(suggestion.text, suggestion.edit_cost, suggestion.edits)
```

For an explicit editor lookup, treat the complete input as one word rather
than relying on its initial segmentation:

```python
suggestions = segmenter.suggest_spelling("សសេរ")
print(suggestions[0].text)  # សរសេរ
```

This reports the whole input span `សម្បត្ត`, suggests `សម្បត្តិ`, and records
an insertion of `ិ` at offset 7. Diagnostics are separate from segmentation
tokens, so typo recovery does not silently alter `segment()` output. Offsets
refer to normalized text by default; use `normalize=False` when the caller has
already normalized the input.

Typo detection searches only near invalid Khmer tokens and uses weighted edits:
dependent vowels and signs cost less than consonant substitutions. Results are
probable corrections, not automatic replacements. Proper names, dialectal
forms, and historical spellings still require application-level review.

Use a named spellcheck profile for application integration:

```python
from khmer_segmenter import SpellcheckProfile

# Live editor underlines: strict confidence filtering and low latency.
diagnostics = segmenter.check_text(text, profile=SpellcheckProfile.TYPING)

# Explicit "Check document": broader OOV correction search.
diagnostics = segmenter.check_text(text, profile="document")
```

`typing` is the production default. `document` allows a wider edit distance
but still avoids scanning every valid dictionary fragment. `high-recall`
examines valid fragments and is intentionally experimental because it can
produce many false positives. The old `include_valid_fragments` option remains
as a low-level compatibility override.

Reviewed exact typo pairs live in
`dictionary_data/khmer_typo_corrections.tsv`. Only `approved` rows affect
spellcheck; proposed additions remain `pending` until reviewed. Run
`python scripts/sync_typo_corrections.py` after editing the canonical Python
copy so Rust and WASM consume the same list.

The legacy dictionary result remains available as
`segment_with_metadata(text)`.

Experimental hyphenation uses the bundled pairs by default. Many words are not
yet separated correctly, so applications should treat its output as a
suggestion and review it before display or publication:

```python
from khmer_segmenter import KhmerHyphenator

hyphenator = KhmerHyphenator.from_data_dir()
result = hyphenator.hyphenate(
    "សហប្រតិបត្តិការ",
    segmenter=segmenter,
    separator="-",  # use "\u200b" for invisible break opportunities
)
```

## CLI

Segment positional text, a file, or standard input:

```bash
khmer-segment segment "ខ្ញុំស្រឡាញ់ប្រទេសកម្ពុជា"
khmer-segment segment --input input.txt --output segmented.txt
cat input.txt | khmer-segment segment
```

Machine-readable output:

```bash
khmer-segment segment "ខ្ញុំសរសេរឯកសារ" --format json
khmer-segment analyze "ខ្ញុំសរសេរឯកសារ" --format json
khmer-segment spellcheck "នីមួយៗ ពាក្យមិនស្គាល់"
khmer-segment diagnose "សម្បត្ត" --format json
khmer-segment diagnose --profile document --input manuscript.txt --format json
khmer-segment diagnose "រស់ជាតិ" --profile high-recall --format json
```

`analyze` reports lexical candidates; it does not claim contextual POS tagging.

Experimental hyphenation and benchmarking:

```bash
khmer-segment hyphenate "សហប្រតិបត្តិការ" --visible-hyphen
khmer-segment benchmark --input dataset/my_corpus.txt --limit 1000
```

The `hyphenate` command is not production-ready: many words may contain
incorrect or missing break positions.

Use a non-default local data directory with the global option before the
subcommand:

```bash
khmer-segment --data-dir /path/to/local/data segment "អត្ថបទខ្មែរ"
```

## Build the Python distribution

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

The wheel contains code plus the attributed runtime data and its reproducibility
manifest. Tests audit
the archive to reject corpora, backups, provenance payloads, and unapproved
linguistic artifacts.

## Documentation

- [Documentation index](docs/README.md)
- [Data sources, attribution, and provenance](docs/DATA.md)
- [Dictionary and embedded-data preparation](docs/EMBEDDED_DICTIONARY.md)
- [Development workflows](docs/DEVELOPMENT.md)
- [Evaluation](docs/EVALUATION.md)
- [Migration from 0.1.1](docs/MIGRATION_0_2.md)
- [Benchmarks](docs/BENCHMARKS.md)
- [Algorithm and porting reference](port/README.md)

## Data policy

The four runtime files listed in [DATA_LICENSE.md](DATA_LICENSE.md) are
redistributed with attribution for noncommercial use. Source downloads,
evaluation corpora, backups, provenance payloads, intermediate tables, and
native build artifacts remain ignored and local.

Removing files from the current Git tree does not remove copies from old Git
history. See [the data policy](docs/DATA.md) before publishing or rewriting
repository history.

## License and acknowledgements

Project code is licensed under the [MIT License](LICENSE). Bundled linguistic
data is subject to the separate [attribution and noncommercial notice](DATA_LICENSE.md).

Original data authors, authorities, corpus creators, and annotators are listed
in [Data Sources, Attribution, and Provenance](docs/DATA.md).
